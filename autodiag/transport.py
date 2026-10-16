"""Pure, testable read-only diagnostics. Unsupported inferences are explicitly marked."""
from .knowledge import DOCS, TITLES

DEFAULT_RMW='rmw_fastrtps_cpp'

def _issue(code, severity, summary, evidence, action, doc=None, confidence='medium'):
    return {'code':code,'severity':severity,'summary':summary,'evidence':evidence,
            'recommended_action':action,'confidence':confidence,
            'documentation':([{'label':TITLES.get(doc,doc),'url':DOCS[doc]}] if doc in DOCS else [])}

def transport_diagnose(a, b=None):
    """Evaluate two host/namespace snapshots; no networking or mutation is performed."""
    issues=[]
    env=a.get('environment',{}); net=a.get('network',{}); container=a.get('container',{})
    mode=a.get('transport',{}).get('requested_mode','auto')
    if mode not in ('auto','intra_process','dds_shm','dds_udp','dds_tcp'):
        issues.append(_issue('UNKNOWN_TRANSPORT_MODE','warning','Unknown requested transport mode',{'requested_mode':mode},'Use auto, intra_process, dds_shm, dds_udp or dds_tcp.'))
    if mode=='intra_process':
        issues.append(_issue('INTRA_PROCESS_NOT_AUTODETECTABLE','info','ROS 2 intra-process communication is a per-node/process decision',{'requested_mode':mode},'Confirm publisher/subscriber are in the same process and intra-process communication is enabled in node options; DDS transport cannot prove this.','intraprocess'))
        if b and a.get('identity',{}).get('pid') != b.get('identity',{}).get('pid'):
            issues.append(_issue('INTRA_PROCESS_SEPARATE_PROCESSES','error','Intra-process delivery cannot connect different processes',{'pid_a':a.get('identity',{}).get('pid'),'pid_b':b.get('identity',{}).get('pid')},'Use DDS shared memory or UDP/TCP for cross-process communications.','intraprocess','high'))
    if env.get('CYCLONEDDS_URI') and env.get('RMW_IMPLEMENTATION','').find('cyclonedds')<0 and env.get('RMW_IMPLEMENTATION'):
        issues.append(_issue('CYCLONE_CONFIG_RMW_MISMATCH','warning','CycloneDDS configuration supplied while another RMW is selected',{'rmw':env.get('RMW_IMPLEMENTATION'),'uri':env.get('CYCLONEDDS_URI')},'Check RMW_IMPLEMENTATION and remove or correct unused DDS configuration.','cyclone_interfaces'))
    if container.get('detected') and mode=='dds_shm' and container.get('ipc_mode') not in ('host','container_shared'):
        issues.append(_issue('SHM_NAMESPACE_UNVERIFIED','warning','Container shared-memory namespace compatibility is unverified',{'ipc_mode':container.get('ipc_mode'),'network_mode':container.get('network_mode')},'Check actual IPC namespace sharing between the two containers and vendor SHM settings; do not assume SHM is available.','fastdds_docker'))
    if net.get('interfaces')==[]:
        issues.append(_issue('NO_NETWORK_INTERFACES','warning','No network interface information obtained',{},'Run diagnostics on a Linux host with iproute2 available.','network'))
    for k,v in [('CYCLONEDDS_URI','cyclone_interfaces'),('FASTDDS_DEFAULT_PROFILES_FILE','fastdds_shm')]:
        if env.get(k) and a.get('config_files',{}).get(k,{}).get('status')=='missing':
            issues.append(_issue('DDS_CONFIG_FILE_MISSING','error','DDS configuration file could not be found',{'variable':k,'value':env.get(k)},'Correct the path or ensure the file is mounted inside the container.',v,'high'))
    ros=a.get('ros',{})
    if ros.get('cli_available') and not env.get('ROS_DISTRO'):
        issues.append(_issue('ROS_ENV_NOT_SOURCED','error','ros2 CLI found, but the ROS 2 environment is not sourced',{'ROS_DISTRO':None},'Run "source /opt/ros/<distro>/setup.bash" in the shell that starts AutoDiag (and your nodes), then restart it.','network','high'))
    issues.extend(_environment_rules(env))
    if b:
        ea=b.get('environment',{}); ca=b.get('container',{})
        domain_a=env.get('ROS_DOMAIN_ID','0'); domain_b=ea.get('ROS_DOMAIN_ID','0')
        if domain_a!=domain_b:
            issues.append(_issue('DOMAIN_MISMATCH','error','Different ROS_DOMAIN_ID values',{'host_a':domain_a,'host_b':domain_b},'Use a consistent ROS_DOMAIN_ID across intended peers, then restart managed processes.','domain','high'))
        if env.get('ROS_LOCALHOST_ONLY')=='1' or ea.get('ROS_LOCALHOST_ONLY')=='1':
            if a.get('identity',{}).get('host') != b.get('identity',{}).get('host'):
                issues.append(_issue('LOCALHOST_ONLY','error','A host is configured for localhost-only discovery',{'a':env.get('ROS_LOCALHOST_ONLY'),'b':ea.get('ROS_LOCALHOST_ONLY')},'Review ROS_LOCALHOST_ONLY and ROS_AUTOMATIC_DISCOVERY_RANGE; allow remote discovery when appropriate.','network','high'))
        if mode=='dds_shm' and ca.get('detected') and container.get('detected'):
            if (a.get('identity',{}).get('host') == b.get('identity',{}).get('host') and container.get('ipc_namespace') and ca.get('ipc_namespace') and container['ipc_namespace']!=ca['ipc_namespace']):
                issues.append(_issue('SHM_IPC_NAMESPACE_DIFFERENCE','error','Containers have different IPC namespaces',{'ipc_a':container['ipc_namespace'],'ipc_b':ca['ipc_namespace']},'Use supported shared IPC configuration only if needed and approved; otherwise prefer UDP transport.','fastdds_docker','high'))
        different_hosts=a.get('identity',{}).get('host') != b.get('identity',{}).get('host')
        restricted={k:v for k,v in (('host_a',_discovery_range(env)),('host_b',_discovery_range(ea))) if v in ('LOCALHOST','OFF')}
        if restricted and different_hosts and not (env.get('ROS_LOCALHOST_ONLY')=='1' or ea.get('ROS_LOCALHOST_ONLY')=='1'):
            issues.append(_issue('DISCOVERY_RANGE_RESTRICTED','error','Automatic discovery range prevents discovery between these hosts',restricted,'Set ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET on both peers, or list peers in ROS_STATIC_PEERS.','discovery','high'))
        # Unset means the distribution default (Fast DDS on every current distro).
        rmw_a=env.get('RMW_IMPLEMENTATION') or (DEFAULT_RMW if ea.get('RMW_IMPLEMENTATION') else None)
        rmw_b=ea.get('RMW_IMPLEMENTATION') or (DEFAULT_RMW if env.get('RMW_IMPLEMENTATION') else None)
        if rmw_a and rmw_b and rmw_a!=rmw_b:
            zenoh='zenoh' in (rmw_a+rmw_b).lower()
            issues.append(_issue('RMW_MISMATCH','error' if zenoh else 'warning',
                'Peers use different RMW implementations'+(' (Zenoh cannot talk to DDS-based RMWs)' if zenoh else ''),
                {'host_a':rmw_a,'host_b':rmw_b},
                'Use the same RMW_IMPLEMENTATION on all peers.' if zenoh else 'Cross-vendor DDS interoperability usually works, but use the same RMW_IMPLEMENTATION where possible to rule it out.',
                'rmw','high' if zenoh else 'medium'))
        distro_a=env.get('ROS_DISTRO'); distro_b=ea.get('ROS_DISTRO')
        if distro_a and distro_b and distro_a!=distro_b:
            issues.append(_issue('DISTRO_MISMATCH','warning','Peers run different ROS 2 distributions',{'host_a':distro_a,'host_b':distro_b},'Communication across ROS 2 distributions is not officially supported; message definitions and defaults can differ.','distro'))
        a_ip=net.get('interfaces',[]); b_ip=b.get('network',{}).get('interfaces',[])
        if a_ip and b_ip and not any(x.get('multicast') for x in a_ip) and not any(x.get('multicast') for x in b_ip):
            issues.append(_issue('MULTICAST_CAPABILITY_ABSENT','warning','Neither snapshot reports a multicast-capable interface',{'host_a':len(a_ip),'host_b':len(b_ip)},'Check whether discovery uses static unicast peers or discovery server; multicast flags alone do not prove network delivery.','cyclone_discovery'))
    return issues

def _discovery_range(env):
    value=(env.get('ROS_AUTOMATIC_DISCOVERY_RANGE') or '').strip().upper()
    return value or ('LOCALHOST' if env.get('ROS_LOCALHOST_ONLY')=='1' else None)


def _environment_rules(env):
    """Checks that need only one environment snapshot."""
    issues=[]
    domain=env.get('ROS_DOMAIN_ID')
    if domain not in (None,''):
        try: value=int(domain)
        except ValueError: value=None
        if value is None or not 0<=value<=232:
            issues.append(_issue('INVALID_DOMAIN_ID','error','ROS_DOMAIN_ID is not a valid domain ID',{'ROS_DOMAIN_ID':domain},'Use an integer from 0 to 101 (safe range on Linux).','domain','high'))
        elif value>101:
            issues.append(_issue('DOMAIN_ID_OUTSIDE_SAFE_RANGE','warning','ROS_DOMAIN_ID is above the range recommended for Linux',{'ROS_DOMAIN_ID':domain},'Domain IDs above 101 may collide with ephemeral ports on Linux; prefer 0 to 101.','domain','high'))
    if _discovery_range(env)=='OFF' and not env.get('ROS_STATIC_PEERS'):
        issues.append(_issue('DISCOVERY_DISABLED','warning','Automatic discovery is disabled and no static peers are configured',{'ROS_AUTOMATIC_DISCOVERY_RANGE':'OFF'},'Set ROS_AUTOMATIC_DISCOVERY_RANGE to LOCALHOST or SUBNET, or configure ROS_STATIC_PEERS.','discovery','high'))
    if env.get('ROS_LOCALHOST_ONLY') is not None and (env.get('ROS_DISTRO') or '').lower() not in ('','foxy','galactic','humble','iron'):
        issues.append(_issue('ROS_LOCALHOST_ONLY_DEPRECATED','info','ROS_LOCALHOST_ONLY is deprecated on this distribution',{'ROS_LOCALHOST_ONLY':env.get('ROS_LOCALHOST_ONLY'),'ROS_DISTRO':env.get('ROS_DISTRO')},'Use ROS_AUTOMATIC_DISCOVERY_RANGE (LOCALHOST, SUBNET or OFF) instead.','discovery','high'))
    return issues


def health(snapshot, issues=()):
    """Health describes collected evidence, not physical truth of full system."""
    ros=snapshot.get('ros',{}); daemon=ros.get('daemon',{});
    checks={
      'host_collector': 'ok',
      'ros2_cli': ('not_sourced' if not snapshot.get('environment',{}).get('ROS_DISTRO') else 'ok') if ros.get('cli_available') else 'unavailable',
      'ros2_daemon': daemon.get('state','unknown'),
      'ros_graph': 'ok' if ros.get('graph',{}).get('state')=='ok' else 'unknown',
      'topic_data_flow': 'not_tested',
      'application_nodes': 'not_tested',
      'dds_transport': 'not_verified',
      'intra_process': 'not_verified',
    }
    errors=[i for i in issues if i.get('severity')=='error']
    unknown=any(v in ('unknown','unavailable','not_sourced','not_tested','not_verified') for v in checks.values())
    state='issue_detected' if errors else ('insufficient_evidence' if unknown else 'healthy')
    return {'status':state,'checks':checks,'issue_count':len(errors),'summary':('Confirmed configuration issue detected' if errors else 'No confirmed critical issue; full-stack health NOT established')}
