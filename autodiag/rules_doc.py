"""Generates docs/reference/rules.md from the rule engine.

Severity, confidence, summary, next step and documentation come from running each
rule's self-test fixtures, so the page cannot drift from the code. Only the
symptom and the grouping are written here. Regenerate with:

    python -m autodiag.rules_doc > docs/reference/rules.md
"""
import re

from .validation import FIXTURES
from .live import _qos_findings
from .transport import transport_diagnose

ICONS = {
    'error': ':material-close-circle:{ style="color:#c2304a" } problem',
    'warning': ':material-alert:{ style="color:#a86400" } warning',
    'info': ':material-information:{ style="color:#2f6fd0" } note',
}

# (code, symptom, runs with, fixtures); the first fixture is the rule's main case.
SECTIONS = [
    ('Environment', [
        ('ROS_ENV_NOT_SOURCED', "Everything shows as unknown; `ros2` works in one terminal but not in the one running AutoDiag.",
         'this host', ['ros_env_not_sourced']),
        ('INVALID_DOMAIN_ID', 'Nodes fail to start or join an unexpected domain.', 'this host', ['invalid_domain']),
        ('DOMAIN_ID_OUTSIDE_SAFE_RANGE', 'Intermittent discovery failures or port conflicts on Linux.', 'this host',
         ['domain_above_safe_range']),
        ('NO_NETWORK_INTERFACES', 'Network-related checks are skipped.', 'this host', ['no_network_interfaces']),
    ]),
    ('Discovery', [
        ('DOMAIN_MISMATCH', "Two machines or containers never see each other's nodes or topics.", 'two snapshots',
         ['domain_mismatch']),
        ('LOCALHOST_ONLY', 'Everything works on one machine, nothing across machines.', 'two snapshots',
         ['localhost_only_cross_host']),
        ('DISCOVERY_RANGE_RESTRICTED', 'Everything works on one machine, nothing across machines (Jazzy and newer).',
         'two snapshots', ['discovery_range_localhost']),
        ('DISCOVERY_DISABLED', 'No other node is ever discovered.', 'this host', ['discovery_off']),
        ('ROS_LOCALHOST_ONLY_DEPRECATED', 'A legacy variable is still set; behaviour may differ from what you expect.',
         'this host', ['localhost_only_deprecated']),
        ('MULTICAST_CAPABILITY_ABSENT', 'Discovery across hosts fails on networks or VPNs without multicast.',
         'two snapshots', ['multicast_absent']),
    ]),
    ('Middleware & versions', [
        ('RMW_MISMATCH', "Peers don't see each other at all (Zenoh vs DDS), or behave inconsistently across DDS vendors.",
         'two snapshots', ['rmw_zenoh_vs_dds', 'rmw_dds_vs_dds']),
        ('DISTRO_MISMATCH', 'Some topics or services fail between machines, often with type or QoS-default differences.',
         'two snapshots', ['distro_mismatch']),
        ('DDS_CONFIG_FILE_MISSING', "Your DDS tuning (interfaces, peers, SHM) silently doesn't apply.", 'this host',
         ['dds_config_missing', 'fastdds_config_missing']),
        ('CYCLONE_CONFIG_RMW_MISMATCH', 'Cyclone DDS settings have no effect because another RMW is active.', 'this host',
         ['cyclone_config_wrong_rmw']),
    ]),
    ('QoS & types (live topics)', [
        ('RELIABILITY_MISMATCH', 'The topic is listed and both endpoints exist, but no message arrives.',
         'topic inspection', ['reliability_mismatch']),
        ('DURABILITY_MISMATCH', 'The subscriber never receives anything: it requests Transient Local, but the publisher '
         'only offers Volatile.', 'topic inspection', ['durability_mismatch']),
        ('LATCHED_DATA_VOLATILE_SUBSCRIBER', 'Data published before the subscriber started never arrives; the classic '
         'empty map in RViz. The QoS is compatible, so ROS reports no error.', 'topic inspection',
         ['latched_data_volatile_subscriber']),
        ('TYPE_MISMATCH', 'Endpoints never match, or tools report type errors on the topic.', 'topic inspection',
         ['type_mismatch']),
    ]),
    ('Transport', [
        ('SHM_IPC_NAMESPACE_DIFFERENCE', 'Containers on one host discover each other but large messages never arrive.',
         'two snapshots, `--transport dds_shm`', ['shm_ipc_namespace_difference']),
        ('SHM_NAMESPACE_UNVERIFIED', 'Shared memory may silently fall back to UDP, or fail inside containers.',
         'in a container, `--transport dds_shm`', ['shm_namespace_unverified']),
        ('INTRA_PROCESS_SEPARATE_PROCESSES', 'Zero-copy intra-process delivery is expected but the nodes run in '
         'different processes.', 'two snapshots, `--transport intra_process`', ['intra_process_across_processes']),
        ('INTRA_PROCESS_NOT_AUTODETECTABLE', "You expect intra-process communication; this can't be confirmed from "
         'outside.', '`--transport intra_process`', ['intra_process_note']),
        ('UNKNOWN_TRANSPORT_MODE', 'The requested transport mode is not recognised.', 'this host',
         ['unknown_transport_mode']),
    ]),
]

RULES = [rule for _, rules in SECTIONS for rule in rules]

ENDPOINT_CHECK = """## Endpoint check

**Check endpoint** in the dashboard (`POST /api/endpoint-check`) compares a publisher and a subscriber that you
describe by hand, without a running ROS graph. It uses the native C++ core when it is built, otherwise a Python
fallback, and reports a smaller set of codes:

| Code | Severity | Meaning |
|---|---|---|
| [`DOMAIN_MISMATCH`](#domain_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | The two domain IDs differ. |
| `TOPIC_MISMATCH` | :material-close-circle:{ style="color:#c2304a" } problem | The topic names differ (check namespaces and remapping). |
| [`TYPE_MISMATCH`](#type_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | The message types differ. |
| [`RELIABILITY_MISMATCH`](#reliability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | Best-effort publisher, reliable subscriber. |
| [`DURABILITY_MISMATCH`](#durability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | Volatile publisher, transient-local subscriber. |

These are not counted separately in the rules above: `TOPIC_MISMATCH` only exists here, because a live topic
inspection always looks at one topic name.
"""


def finding(fixture: str, code: str) -> dict:
    case = FIXTURES[fixture]
    issues = _qos_findings(case['endpoints']) if 'endpoints' in case else transport_diagnose(case['a'], case['b'])
    return next(i for i in issues if i['code'] == code)


def _unique(items):
    return list(dict.fromkeys(items))


def _severity(variants) -> str:
    cells = _unique(f"{ICONS[f['severity']]} (confidence: {f['confidence']})" for _, f in variants)
    if len(cells) == 1:
        return cells[0]
    return '<br>'.join(f"{ICONS[f['severity']]} (confidence: {f['confidence']}): {FIXTURES[name]['description']}"
                       for name, f in variants)


def _rule(code, symptom, runs_with, fixtures) -> list[str]:
    variants = [(name, finding(name, code)) for name in fixtures]
    main = variants[0][1]
    steps = _unique(f['recommended_action'] for _, f in variants)
    docs = _unique(f"[{d['label']}]({d['url']})" for _, f in variants for d in f['documentation'])
    return [f'### `{code}` {{#{code.lower()}}}', '', f"**{main['summary']}**", '', '| | |', '|---|---|',
            f'| Severity | {_severity(variants)} |', f'| Symptom | {symptom} |', f'| Runs with | {runs_with} |',
            f"| Next step | {'<br>'.join(steps)} |", f"| Documentation | {' · '.join(docs) or '—'} |", '']


def render() -> str:
    out = ['# Diagnostic rules', '',
           f'DDS AutoDiag has **{len(RULES)} rules**. Each finding includes its evidence, a next step and, where one '
           'applies, official documentation. `dds-autodiag selftest` (dashboard **Tool check**) runs every rule '
           f'against its synthetic faults ({len(FIXTURES)} fixtures) on any installation. That proves the engine, '
           'not your live graph. Dashboard **Live rule check** (`POST /api/live-rules`) runs the same codes on this '
           'host, an optional peer and this host’s graph: **fault**, **pass** or **skipped**.', '',
           '!!! info "Generated from the rule engine"',
           '    Severity, summary, next step and documentation on this page are produced by running each rule\'s '
           'self-test',
           '    fixture (`python -m autodiag.rules_doc`). A test fails if the page and the code disagree.', '',
           '| Code | Severity | Needs |', '|---|---|---|']
    for code, _, runs_with, fixtures in RULES:
        severities = _unique(ICONS[finding(name, code)['severity']] for name in fixtures)
        out.append(f'| [`{code}`](#{code.lower()}) | {" / ".join(severities)} | {runs_with} |')
    for title, rules in SECTIONS:
        out += ['', f'## {title}', '']
        for rule in rules:
            out += _rule(*rule)
    out += ['', ENDPOINT_CHECK]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).rstrip() + '\n'


if __name__ == '__main__':
    print(render(), end='')
