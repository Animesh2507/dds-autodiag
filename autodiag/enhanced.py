"""Read-only UX probes. The evidence level is explicit; none of these prove DDS transport selection."""
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .collector import run, _ns


_RMW_CACHE={'at':0.0,'key':None,'value':None}
RMW_CACHE_SECONDS=60


def detect_rmw():
    # ros2 doctor takes seconds; the answer only depends on this process's environment.
    key=(os.getenv('RMW_IMPLEMENTATION'),os.getenv('ROS_DISTRO'),os.getenv('PATH'))
    if _RMW_CACHE['key']==key and time.monotonic()-_RMW_CACHE['at']<RMW_CACHE_SECONDS:
        return dict(_RMW_CACHE['value'])
    value=_detect_rmw()
    _RMW_CACHE.update(at=time.monotonic(),key=key,value=value)
    return dict(value)


def _detect_rmw():
    configured=os.getenv('RMW_IMPLEMENTATION')
    data={'configured':configured, 'effective':None,'method':'unavailable','scope':'AutoDiag server environment','state':'unknown'}
    # ros2 doctor executes with the middleware available to the collector; not a per-node diagnosis.
    result=run(['ros2','doctor','--report'],timeout=15,max_output=500_000) if shutil.which('ros2') else {'state':'unavailable'}
    if result.get('state')=='ok':
        m=re.search(r'^\s*middleware name\s*:\s*(rmw_[\w]+)',result.get('stdout',''),re.M|re.I)
        if m:
            data.update(effective=m.group(1),method='ros2 doctor --report',scope='CLI diagnostic process (not all ROS processes)',state='detected')
    if not data['effective'] and configured:
        data.update(effective=configured,method='RMW_IMPLEMENTATION (configuration only)',state='configured_not_verified')
    return data


def inspect_shm(snapshot=None, rmw=None):
    """Check available local SHM prerequisites; cannot prove live SHM selection."""
    p=Path('/dev/shm')
    observations=[]
    if p.exists():
        observations.append({'name':'/dev/shm exists','result':'pass','detail':'Shared-memory mount path exists'})
        observations.append({'name':'/dev/shm accessible','result':'pass' if os.access(p,os.R_OK|os.W_OK|os.X_OK) else 'warning', 'detail':'Current process permissions; not proof that DDS transport works'})
        try:
            st=os.statvfs(str(p)); observations.append({'name':'Available shared-memory space','result':'info','detail':f'{st.f_bavail*st.f_frsize//(1024*1024)} MiB available'})
        except OSError:pass
    else:
        observations.append({'name':'/dev/shm exists','result':'warning','detail':'Shared-memory path not present'})
    observations.append({'name':'IPC namespace','result':'info','detail':_ns('ipc') or 'Unavailable'})
    rmw=rmw or detect_rmw()
    observations.append({'name':'RMW detected by local diagnostic','result':'info','detail':rmw.get('effective') or 'Unknown'})
    return {'state':'prerequisites_inspected','observations':observations,'actual_transport':'NOT_VERIFIED',
            'summary':'Local shared-memory prerequisites checked. This does not establish that DDS has selected SHM or that cross-process messages are delivered.',
            'recommended_next_test':'Use a controlled publisher/subscriber test plus vendor instrumentation to distinguish shared-memory transport from UDP fallback.',
            'documentation':[{'label':'Fast DDS shared memory transport','url':'https://fast-dds.docs.eprosima.com/en/stable/fastdds/transport/shared_memory/shared_memory.html'},
                             {'label':'Fast DDS in Docker','url':'https://fast-dds.docs.eprosima.com/en/stable/docker/shm_docker.html'}]}


def _unique(values):
    seen, out = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _env_port(info):
    for item in (info.get('Config') or {}).get('Env') or []:
        if item.startswith('AUTODIAG_PORT='):
            return item.split('=', 1)[1].strip()
    return None


def _published_ports(info):
    ports = []
    bindings = (info.get('NetworkSettings') or {}).get('Ports') or {}
    if isinstance(bindings, dict):
        for spec, binds in bindings.items():
            container_port = str(spec).split('/', 1)[0]
            if binds:
                for bind in binds:
                    host = (bind or {}).get('HostPort')
                    if host:
                        ports.append(str(host))
            elif container_port:
                ports.append(container_port)
    env_port = _env_port(info)
    if env_port:
        ports.append(env_port)
    return _unique(ports)


def _container_ips(info):
    ips = []
    networks = (info.get('NetworkSettings') or {}).get('Networks') or {}
    if isinstance(networks, dict):
        for cfg in networks.values():
            ip = (cfg or {}).get('IPAddress')
            if ip:
                ips.append(ip)
    fallback = (info.get('NetworkSettings') or {}).get('IPAddress')
    if fallback:
        ips.append(fallback)
    return _unique(ips)


def _connect_urls(ips, ports, network_mode):
    host_net = (network_mode or '').split(':')[0] == 'host'
    targets = ['127.0.0.1'] if host_net else ips
    return [f'http://{ip}:{port}' for ip in targets for port in ports]


def _annotate_containers(items):
    ids = [c.get('id') for c in items if c.get('id')]
    if not ids:
        return items
    result = run(['docker', 'inspect', *ids], timeout=8, max_output=400_000)
    if result.get('state') != 'ok':
        return items
    try:
        details = json.loads(result.get('stdout') or '[]')
    except ValueError:
        return items
    by_id = {}
    for info in details if isinstance(details, list) else []:
        full = info.get('Id') or ''
        short = full[:12]
        by_id[full] = info
        by_id[short] = info
    for item in items:
        info = by_id.get(item.get('id')) or by_id.get((item.get('id') or '')[:12])
        if not info:
            continue
        mode = (info.get('HostConfig') or {}).get('NetworkMode') or item.get('network') or ''
        ips = _container_ips(info)
        ports = _published_ports(info)
        item.update(ips=ips, ports=ports, network_mode=mode,
                    connect_urls=_connect_urls(ips, ports, mode))
    return items


def discover_local_containers():
    if not shutil.which('docker'):
        return {'state':'unavailable','environments':[],'reason':'Docker CLI not installed or not on PATH. Docker is optional.'}
    result=run(['docker','ps','--format','{{json .}}'],timeout=5)
    if result['state']!='ok':
        return {'state':'permission_or_daemon_unavailable','environments':[], 'reason':'Docker CLI cannot access the engine; check permissions/service. No containers were inspected.'}
    items=[]
    for line in result.get('stdout','').splitlines()[:100]:
        try:
            o=json.loads(line)
            items.append({'id':o.get('ID'),'name':o.get('Names'),'image':o.get('Image'),'status':o.get('Status'),
                          'network':o.get('Networks'),'ips':[],'ports':[],'connect_urls':[],
                          'scope':'container_metadata_only','rmw':'unknown','domain':'unknown'})
        except ValueError: pass
    items = _annotate_containers(items)
    return {'state':'ok','environments':items,'reason':'Host-side Docker metadata only: name, network, IP and published or AUTODIAG_PORT. Cannot infer each container process RMW, ROS domain, or actual DDS transport.'}


def ollama_status():
    """Short loopback-only connectivity check (not an external request)."""
    import urllib.request
    from urllib.error import HTTPError, URLError
    endpoint=os.getenv('AUTODIAG_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    if not re.fullmatch(r'http://(127\.0\.0\.1|localhost|\[::1\]):\d{2,5}',endpoint):
        return {'state':'misconfigured','message':'For safety, the dashboard status check requires a loopback Ollama URL.','models':[]}
    try:
        with urllib.request.urlopen(endpoint+'/api/tags',timeout=2) as response:
            payload=json.load(response)
        models=[m.get('name','') for m in payload.get('models',[]) if isinstance(m,dict)]
        from .llm import model_for, thinking_only
        expected=model_for('ollama')
        has_model=any(m==expected or m==expected+':latest' or m.startswith(expected+':') for m in models)
        slow=has_model and thinking_only(expected)
        message='Local Ollama reachable, using '+expected if has_model else 'Local Ollama reachable; download '+expected
        if slow:
            message+=' (a reasoning model: thorough but slow on CPU; for fast answers run "ollama pull qwen3:4b-instruct")'
        return {'state':'ready' if has_model else 'model_missing','message':message,'models':models,
                'expected_model':expected,'thinking_model':slow}
    except (URLError,HTTPError,ValueError,OSError) as exc:
        return {'state':'unreachable','message':'Ollama service not reachable from AutoDiag. Start Ollama and check port 11434.','models':[]}


def summary(snapshot):
    with ThreadPoolExecutor(max_workers=3) as pool:
        rmw=pool.submit(detect_rmw); docker=pool.submit(discover_local_containers); ollama=pool.submit(ollama_status)
        rmw=rmw.result()
        return {'rmw':rmw,'shm':inspect_shm(snapshot,rmw),'docker':docker.result(),'ollama':ollama.result()}
