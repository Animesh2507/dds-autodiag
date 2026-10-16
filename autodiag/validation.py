"""Synthetic fault injection: tests diagnosis rules without requiring ROS 2 runtime.

Each fixture is one or two minimal snapshots (host rules) or a list of topic
endpoints (live QoS rules), plus the rule code it must (or must not) trigger.
Every rule has at least one fixture; running them all is the built-in self-test.
"""
from .live import _qos_findings
from .transport import transport_diagnose, health


def _snap(host='host-a', pid=1, container=None, mode='auto', network=None, **env):
    return {'identity': {'host': host, 'pid': pid}, 'environment': env,
            'container': container or {'detected': False},
            'transport': {'requested_mode': mode}, 'network': network or {}}


def _ep(kind, node, reliability='RELIABLE', durability='VOLATILE', type_='std_msgs/msg/String'):
    return {'kind': kind, 'node': node, 'type': type_, 'qos': {'reliability': reliability, 'durability': durability}}


_NO_MULTICAST = {'interfaces': [{'name': 'eth0', 'multicast': False}]}


FIXTURES = {
    'domain_mismatch': {'description': 'Peers on different ROS_DOMAIN_ID values',
                        'a': _snap(ROS_DOMAIN_ID='8'), 'b': _snap('host-b', ROS_DOMAIN_ID='9'), 'expected': 'DOMAIN_MISMATCH'},
    'same_domain': {'description': 'Matching domains must not report a mismatch',
                    'a': _snap(ROS_DOMAIN_ID='8'), 'b': _snap('host-b', ROS_DOMAIN_ID='8'), 'expected': None,
                    'forbidden': 'DOMAIN_MISMATCH'},
    'invalid_domain': {'description': 'Non-numeric ROS_DOMAIN_ID',
                       'a': _snap(ROS_DOMAIN_ID='robot'), 'b': None, 'expected': 'INVALID_DOMAIN_ID'},
    'domain_above_safe_range': {'description': 'Domain ID above 101 on Linux',
                                'a': _snap(ROS_DOMAIN_ID='150'), 'b': None, 'expected': 'DOMAIN_ID_OUTSIDE_SAFE_RANGE'},
    'localhost_only_cross_host': {'description': 'ROS_LOCALHOST_ONLY=1 with a peer on another host',
                                  'a': _snap(ROS_LOCALHOST_ONLY='1'), 'b': _snap('host-b'), 'expected': 'LOCALHOST_ONLY'},
    'discovery_range_localhost': {'description': 'ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST across hosts',
                                  'a': _snap(ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST'), 'b': _snap('host-b'),
                                  'expected': 'DISCOVERY_RANGE_RESTRICTED'},
    'discovery_off': {'description': 'Discovery disabled with no static peers',
                      'a': _snap(ROS_AUTOMATIC_DISCOVERY_RANGE='OFF'), 'b': None, 'expected': 'DISCOVERY_DISABLED'},
    'localhost_only_deprecated': {'description': 'ROS_LOCALHOST_ONLY used on Jazzy',
                                  'a': _snap(ROS_DISTRO='jazzy', ROS_LOCALHOST_ONLY='1'), 'b': None,
                                  'expected': 'ROS_LOCALHOST_ONLY_DEPRECATED'},
    'rmw_zenoh_vs_dds': {'description': 'Zenoh RMW peer talking to a DDS RMW peer',
                         'a': _snap(RMW_IMPLEMENTATION='rmw_zenoh_cpp'), 'b': _snap('host-b', RMW_IMPLEMENTATION='rmw_fastrtps_cpp'),
                         'expected': 'RMW_MISMATCH', 'expected_severity': 'error'},
    'rmw_dds_vs_dds': {'description': 'Two different DDS RMWs (usually interoperable)',
                       'a': _snap(RMW_IMPLEMENTATION='rmw_fastrtps_cpp'), 'b': _snap('host-b', RMW_IMPLEMENTATION='rmw_cyclonedds_cpp'),
                       'expected': 'RMW_MISMATCH', 'expected_severity': 'warning'},
    'distro_mismatch': {'description': 'Humble peer talking to a Jazzy peer',
                        'a': _snap(ROS_DISTRO='jazzy'), 'b': _snap('host-b', ROS_DISTRO='humble'), 'expected': 'DISTRO_MISMATCH'},
    'cyclone_config_wrong_rmw': {'description': 'CYCLONEDDS_URI set while Fast DDS is selected',
                                 'a': _snap(RMW_IMPLEMENTATION='rmw_fastrtps_cpp', CYCLONEDDS_URI='file:///etc/cyclone.xml'), 'b': None,
                                 'expected': 'CYCLONE_CONFIG_RMW_MISMATCH'},
    'dds_config_missing': {'description': 'DDS XML path does not exist',
                           'a': {**_snap(CYCLONEDDS_URI='file:///missing.xml'), 'config_files': {'CYCLONEDDS_URI': {'status': 'missing'}}},
                           'b': None, 'expected': 'DDS_CONFIG_FILE_MISSING'},
    'fastdds_config_missing': {'description': 'Fast DDS XML profile path does not exist',
                               'a': {**_snap(FASTDDS_DEFAULT_PROFILES_FILE='/missing.xml'),
                                     'config_files': {'FASTDDS_DEFAULT_PROFILES_FILE': {'status': 'missing'}}},
                               'b': None, 'expected': 'DDS_CONFIG_FILE_MISSING'},
    'ros_env_not_sourced': {'description': 'ros2 CLI on PATH but no ROS_DISTRO',
                            'a': {**_snap(), 'ros': {'cli_available': True}}, 'b': None, 'expected': 'ROS_ENV_NOT_SOURCED'},
    'no_network_interfaces': {'description': 'Interface listing came back empty',
                              'a': _snap(network={'interfaces': []}), 'b': None, 'expected': 'NO_NETWORK_INTERFACES'},
    'multicast_absent': {'description': 'Neither host has a multicast-capable interface',
                         'a': _snap(network=_NO_MULTICAST), 'b': _snap('host-b', network=_NO_MULTICAST),
                         'expected': 'MULTICAST_CAPABILITY_ABSENT'},
    'unknown_transport_mode': {'description': 'Unsupported --transport value',
                               'a': _snap(mode='carrier_pigeon'), 'b': None, 'expected': 'UNKNOWN_TRANSPORT_MODE'},
    'intra_process_note': {'description': 'Intra-process requested: cannot be confirmed from outside',
                           'a': _snap(mode='intra_process'), 'b': None, 'expected': 'INTRA_PROCESS_NOT_AUTODETECTABLE'},
    'shm_namespace_unverified': {'description': 'Shared memory requested inside a container with unknown IPC mode',
                                 'a': _snap(container={'detected': True}, mode='dds_shm'), 'b': None,
                                 'expected': 'SHM_NAMESPACE_UNVERIFIED'},
    'intra_process_across_processes': {'description': 'Intra-process requested between two processes',
                                       'a': _snap(mode='intra_process'), 'b': _snap(pid=2, mode='intra_process'),
                                       'expected': 'INTRA_PROCESS_SEPARATE_PROCESSES'},
    'shm_ipc_namespace_difference': {'description': 'Two containers on one host with separate IPC namespaces',
                                     'a': _snap(container={'detected': True, 'ipc_namespace': 'ipc:[1]'}, mode='dds_shm'),
                                     'b': _snap(container={'detected': True, 'ipc_namespace': 'ipc:[2]'}),
                                     'expected': 'SHM_IPC_NAMESPACE_DIFFERENCE'},
    # Live topic rules: endpoints as `ros2 topic info --verbose` reports them.
    'reliability_mismatch': {'description': 'Best-effort publisher, reliable subscriber',
                             'endpoints': [_ep('publisher', 'publisher_node', reliability='BEST_EFFORT'), _ep('subscriber', 'subscriber_node')],
                             'expected': 'RELIABILITY_MISMATCH'},
    'durability_mismatch': {'description': 'Volatile publisher, transient-local subscriber',
                            'endpoints': [_ep('publisher', 'publisher_node'), _ep('subscriber', 'subscriber_node', durability='TRANSIENT_LOCAL')],
                            'expected': 'DURABILITY_MISMATCH'},
    'latched_data_volatile_subscriber': {'description': 'Latched publisher, volatile subscriber (e.g. /map)',
                                         'endpoints': [_ep('publisher', 'publisher_node', durability='TRANSIENT_LOCAL'),
                                                       _ep('subscriber', 'subscriber_node')],
                                         'expected': 'LATCHED_DATA_VOLATILE_SUBSCRIBER'},
    'type_mismatch': {'description': 'Publisher and subscriber use different message types',
                      'endpoints': [_ep('publisher', 'publisher_node'), _ep('subscriber', 'subscriber_node', type_='std_msgs/msg/Int32')],
                      'expected': 'TYPE_MISMATCH'},
    'qos_compatible': {'description': 'Matching QoS and types must not report a QoS problem',
                       'endpoints': [_ep('publisher', 'publisher_node'), _ep('subscriber', 'subscriber_node')], 'expected': None,
                       'forbidden': 'RELIABILITY_MISMATCH'},
}


def list_fixtures():
    return sorted(FIXTURES)


def run_fixture(name):
    if name not in FIXTURES:
        raise KeyError(name)
    case = FIXTURES[name]
    issues = _qos_findings(case['endpoints']) if 'endpoints' in case else transport_diagnose(case['a'], case['b'])
    codes = [x['code'] for x in issues]
    expected = case['expected']
    passed = expected in codes if expected else case.get('forbidden') not in codes
    if passed and case.get('expected_severity'):
        passed = any(x['code'] == expected and x['severity'] == case['expected_severity'] for x in issues)
    return {'fixture': name, 'description': case['description'], 'expected_code': expected,
            'observed_codes': codes, 'passed': passed,
            'health': health(case.get('a') or {}, issues), 'synthetic': True,
            'limitation': 'No real ROS middleware, Docker namespace or network connectivity exercised.'}


def run_all():
    results = [run_fixture(name) for name in list_fixtures()]
    return {'passed': sum(r['passed'] for r in results), 'total': len(results),
            'ok': all(r['passed'] for r in results), 'results': results}
