"""Read-only local system and ROS 2 probes; no daemon start/stop commands."""
import json, os, platform, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .config import discovery_seconds

def run(cmd, timeout=3, max_output=16000):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False,env={**os.environ,'ROS2CLI_DISABLE_DAEMON':'1'})
        return {'state':'ok' if p.returncode==0 else 'error','exit_code':p.returncode,'stdout':p.stdout[:max_output], 'stderr':p.stderr[:2000]}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {'state':'unavailable','error':str(e)}

def _ns(name):
    try:return os.readlink('/proc/self/ns/'+name)
    except OSError:return None

def _container():
    hints=' '.join([Path('/proc/1/cgroup').read_text(errors='replace') if Path('/proc/1/cgroup').exists() else '', Path('/proc/self/mountinfo').read_text(errors='replace')[:3000] if Path('/proc/self/mountinfo').exists() else ''])
    detected=Path('/.dockerenv').exists() or any(x in hints for x in ('docker','kubepods','containerd','lxc'))
    return {'detected':detected,'type':'container' if detected else 'host_or_unknown', 'ipc_namespace':_ns('ipc'),'net_namespace':_ns('net'),'pid_namespace':_ns('pid'),'ipc_mode':'unknown','network_mode':'unknown'}

def _interfaces():
    if not shutil.which('ip'):return []
    p=run(['ip','-j','addr','show'],3)
    if p['state']!='ok':return []
    try:
        return [{'name':i.get('ifname'),'state':i.get('operstate'),'mtu':i.get('mtu'),'multicast':'MULTICAST' in i.get('flags',[]),'addresses':[a.get('local') for a in i.get('addr_info',[])]} for i in json.loads(p['stdout'])]
    except (ValueError,KeyError):return []

def collect():
    keys=('ROS_DISTRO','ROS_DOMAIN_ID','RMW_IMPLEMENTATION','CYCLONEDDS_URI','FASTDDS_DEFAULT_PROFILES_FILE','FASTRTPS_DEFAULT_PROFILES_FILE','ROS_LOCALHOST_ONLY','ROS_AUTOMATIC_DISCOVERY_RANGE','ROS_STATIC_PEERS','RMW_FASTRTPS_USE_QOS_FROM_XML','ROS_DISCOVERY_SERVER','ROS_SECURITY_ENABLE','ROS_SECURITY_STRATEGY')
    env={k:os.environ.get(k) for k in keys if os.environ.get(k) is not None}
    cfg={}
    for k in ('CYCLONEDDS_URI','FASTDDS_DEFAULT_PROFILES_FILE','FASTRTPS_DEFAULT_PROFILES_FILE'):
        v=env.get(k)
        if v:
            candidate=v[7:] if v.startswith('file://') else v
            cfg[k]={'status':'present' if Path(candidate).is_file() else ('inline_or_uri' if candidate.lstrip().startswith('<') else 'missing')}
    cli=shutil.which('ros2') is not None
    unavailable={'state':'unavailable'}
    if cli:
        # Independent read-only probes; run concurrently to keep the dashboard responsive.
        with ThreadPoolExecutor(max_workers=3) as pool:
            spin=discovery_seconds(); wait=5+float(spin)
            jobs=[pool.submit(run,cmd,t) for cmd,t in ((['ros2','daemon','status'],4),(['ros2','node','list','--no-daemon','--spin-time',spin],wait),(['ros2','topic','list','--no-daemon','-t','--spin-time',spin],wait))]
            daemon,graph,topics=(j.result() for j in jobs)
    else:
        daemon=graph=topics=unavailable
    # daemon status is a diagnostic on its own; it is not the DDS data plane.
    dtext=(daemon.get('stdout','')+' '+daemon.get('stderr','')).lower()
    dstate='running' if ('running' in dtext and 'not running' not in dtext) else ('stopped' if 'not running' in dtext else 'unknown')
    return {'schema_version':2,'tool_version':__version__,'collected_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'identity':{'host':platform.node(),'pid':os.getpid()},'environment':env,'container':_container(),'network':{'interfaces':_interfaces()},'config_files':cfg,
            'transport':{'requested_mode':'auto','observed_mode':'unknown','reason':'Cannot infer intra-process or DDS transport from process environment alone'},
            'ros':{'cli_available':cli,'daemon':{'state':dstate,'diagnostic':daemon},'graph':graph,'topics':topics},
            'limitations':['Snapshot of the collector environment, not every running ROS process','ROS daemon does not carry ROS message traffic','Container network / IPC mode not reliably inferable without host-side Docker API','DDS SHM/UDP actual selection needs vendor instrumentation or packet traces']}


def summarize(snapshot):
    """Small human-oriented view of a snapshot (counts instead of raw CLI output)."""
    ros=snapshot.get('ros',{}); env=snapshot.get('environment',{})
    def lines(probe):
        return [l for l in (probe or {}).get('stdout','').splitlines() if l.strip()] if (probe or {}).get('state')=='ok' else None
    nodes=lines(ros.get('graph')); topics=lines(ros.get('topics'))
    return {'host':snapshot.get('identity',{}).get('host'),'ros_distro':env.get('ROS_DISTRO'),
            'domain_id':env.get('ROS_DOMAIN_ID','0'),'rmw':env.get('RMW_IMPLEMENTATION'),
            'discovery_range':env.get('ROS_AUTOMATIC_DISCOVERY_RANGE') or ('LOCALHOST' if env.get('ROS_LOCALHOST_ONLY')=='1' else None),
            'container':bool(snapshot.get('container',{}).get('detected')),
            'node_count':len(nodes) if nodes is not None else None,
            'topic_count':len(topics) if topics is not None else None,
            'interfaces':[i.get('name') for i in snapshot.get('network',{}).get('interfaces',[])]}
