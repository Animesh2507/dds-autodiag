"""Read-only live ROS 2 graph inspection. Requires a sourced ROS 2 environment.

This introspects discovered endpoints, not the actual data plane. The external ros2
CLI is called with bounded timeouts to avoid indefinite waits.
"""
import json
import os
import re
import shutil
import subprocess
from .knowledge import DOCS
from .config import discovery_seconds

def _call(args, timeout=8):
    if not shutil.which('ros2'):
        return {'state':'unavailable','error':'ros2 CLI is not on PATH. Source ROS 2 before launching AutoDiag.'}
    try:
        p=subprocess.run(['ros2',*args],capture_output=True,text=True,timeout=timeout,
            env={**os.environ,'ROS2CLI_DISABLE_DAEMON':'1'}, check=False)
        return {'state':'ok' if p.returncode==0 else 'error','stdout':p.stdout[:60000],
                'stderr':p.stderr[:5000],'exit_code':p.returncode}
    except subprocess.TimeoutExpired:
        return {'state':'timeout','error':f'ROS graph inspection exceeded {timeout}s'}
    except OSError as exc:
        return {'state':'unavailable','error':str(exc)}

def topic_list():
    result=_call(['topic','list','-t','--no-daemon','--spin-time',discovery_seconds()],timeout=8+int(float(discovery_seconds())))
    topics=[]
    if result['state']=='ok':
        for line in result['stdout'].splitlines():
            m=re.match(r'^(/\S+)\s+\[([^]]+)\]$',line.strip())
            if m: topics.append({'topic':m.group(1),'type':m.group(2)})
    return {'state':result['state'],'topics':topics,'error':result.get('error') or result.get('stderr','')}

def _parse_verbose(text):
    endpoints=[]; kind=None; current=None
    for ln in text.splitlines():
        s=ln.strip()
        if s.startswith('Publisher count:'): kind='publisher';current=None
        elif s.startswith('Subscription count:'): kind='subscriber';current=None
        elif s.startswith('Node name:'):
            current={'kind':kind,'node':s.split(':',1)[1].strip(),'qos':{}}
            endpoints.append(current)
        elif current is not None:
                        if s.startswith('Node namespace:'):
                namespace = s.split(':', 1)[1].strip().strip('/')
                current['node'] = (namespace + '/' if namespace else '') + current['node']
for key,field in [('Topic type:','type'),('Endpoint type:','endpoint_type'),('GID:','gid')]:
                if s.startswith(key):current[field]=s.split(':',1)[1].strip()
            for key,field in [('Reliability:','reliability'),('Durability:','durability'),('History (Depth):','history'),('Deadline:','deadline'),('Lifespan:','lifespan'),('Liveliness:','liveliness')]:
                if s.startswith(key): current['qos'][field]=s.split(':',1)[1].strip()
    return endpoints

def _qos_findings(endpoints):
    pub=[x for x in endpoints if x['kind']=='publisher']
    sub=[x for x in endpoints if x['kind']=='subscriber']
    findings=[]
    for p in pub:
      for s in sub:
        for policy,offered,requested in [('reliability','BEST_EFFORT','RELIABLE'),('durability','VOLATILE','TRANSIENT_LOCAL')]:
          a=p['qos'].get(policy,'').upper().replace(' ','_')
          b=s['qos'].get(policy,'').upper().replace(' ','_')
          if offered in a and requested in b:
            findings.append({'code':policy.upper()+'_MISMATCH','severity':'error',
               'summary':f'Incompatible {policy}: {p["node"]} → {s["node"]}',
               'evidence':{'publisher':p['node'],'subscriber':s['node'],'offered':a,'requested':b},
               'recommended_action':'Review requested/offered QoS policies. Do not change semantics blindly.',
               'confidence':'high','documentation':[{'label':'ROS 2 QoS','url':DOCS['qos']}]})
        # Compatible, but a subscriber that starts after the publisher never gets latched data (e.g. /map).
        pd=p['qos'].get('durability','').upper().replace(' ','_')
        sd=s['qos'].get('durability','').upper().replace(' ','_')
        if 'TRANSIENT_LOCAL' in pd and 'VOLATILE' in sd:
            findings.append({'code':'LATCHED_DATA_VOLATILE_SUBSCRIBER','severity':'warning',
               'summary':f'{s["node"]} requests Volatile from latched (Transient Local) publisher {p["node"]}',
               'evidence':{'publisher':p['node'],'subscriber':s['node'],'offered':pd,'requested':sd},
               'recommended_action':'Request Transient Local durability on the subscriber (e.g. RViz Map display: '
                                    'Topic → Durability Policy) so it receives the last message even when it starts later.',
               'confidence':'high','documentation':[{'label':'ROS 2 QoS','url':DOCS['qos']}]})
        if p.get('type') and s.get('type') and p['type']!=s['type']:
            findings.append({'code':'TYPE_MISMATCH','severity':'error','summary':'Different message types on this topic',
             'evidence':{'publisher':p.get('type'),'subscriber':s.get('type')},
             'recommended_action':'Use matching interface types and type definitions.', 'confidence':'high',
             'documentation':[{'label':'ROS 2 interfaces','url':DOCS['interfaces']}]})
    return findings

def inspect_topic(topic):
    if not isinstance(topic,str) or not re.fullmatch(r'/[a-zA-Z0-9_~/]+',topic) or len(topic)>200:
        return {'state':'invalid','error':'Use a ROS topic name beginning with / (letters, digits, _, /, ~).'}
    result=_call(['topic','info',topic,'--verbose','--no-daemon','--spin-time',discovery_seconds()],timeout=8+int(float(discovery_seconds())))
    if result['state']!='ok':return {'topic':topic,'state':result['state'],'error':result.get('error') or result.get('stderr')}
    eps=_parse_verbose(result['stdout']); findings=_qos_findings(eps)
    return {'topic':topic,'state':'ok','endpoints':eps,'findings':findings,
      'publisher_count':len([e for e in eps if e['kind']=='publisher']),
      'subscriber_count':len([e for e in eps if e['kind']=='subscriber']),
      'delivery':'not_verified','limitations':['Graph discovery is not evidence of actual message delivery.',
       'Cross-host discovery failures can hide endpoints from this view.']}


def sample_topic(topic: str, timeout: int = 8, reliability: str = 'auto'):
    """Read one live message using the ROS 2 CLI, with bounded runtime/output.

    Read-only and on demand. Does not modify publishers or QoS settings.
    Large sensor messages are truncated; timeout is not proof of failure.
    """
    if not isinstance(topic, str) or not re.fullmatch(r'/[a-zA-Z0-9_~/]+', topic) or len(topic)>200:
        return {'state':'invalid','error':'Invalid topic name'}
    if reliability not in ('auto','best_effort','reliable'):
        return {'state':'invalid','error':'Unsupported reliability selection'}
    if not isinstance(timeout,int) or not 1 <= timeout <= 15:
        return {'state':'invalid','error':'Timeout must be 1–15 seconds'}
    args=['topic','echo',topic,'--once']
    if reliability != 'auto': args += ['--qos-reliability',reliability]
    result=_call(args,timeout=timeout)
    out=result.get('stdout','')
    # The CLI output is capped in _call; trim further for browser rendering.
    limit=16000
    return {'topic':topic,'state':result['state'],
            'raw':out[:limit], 'truncated':len(out)>limit,
            'error':result.get('error') or result.get('stderr',''),
            'reliability':reliability,'timeout_seconds':timeout,
            'note':'A received sample demonstrates delivery to this probe, not which transport carried it.'}
