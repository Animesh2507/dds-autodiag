"""dds-autodiag command line.

Exit codes: 0 = no problem found, 1 = at least one error-severity finding, 2 = usage or input error.
The pre-1.0 flags (--collect, --compare, --health, --transport) are still accepted.
"""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
import shutil
import sys
from pathlib import Path
from . import __version__

MODES = ('auto', 'intra_process', 'dds_shm', 'dds_udp', 'dds_tcp')
EXIT_OK, EXIT_ISSUES, EXIT_USAGE = 0, 1, 2


# ---------- output helpers ----------

def _color_enabled(stream=sys.stdout) -> bool:
    return stream.isatty() and 'NO_COLOR' not in os.environ and os.environ.get('TERM') != 'dumb'


def _c(text, code):
    return f'\033[{code}m{text}\033[0m' if _color_enabled() else str(text)


SEV = {'error': ('✖ problem', '31;1'), 'warning': ('▲ warning', '33;1'), 'info': ('● note', '36')}


def _print_issues(issues):
    from .report import sort_issues
    if not issues:
        print(_c('✔ No configured rule detected a problem.', '32;1'),
              'This does not prove messages are delivered; use `dds-autodiag sample <topic>` to confirm.')
        return
    for issue in sort_issues(issues):
        label, code = SEV.get(issue.get('severity'), ('●', '0'))
        print(f"{_c(label, code)}  {_c(issue.get('code'), '1')}  {issue.get('summary', '')}")
        if issue.get('evidence'):
            print('    evidence: ' + ', '.join(f'{k}={v}' for k, v in issue['evidence'].items()))
        if issue.get('recommended_action'):
            print('    next:     ' + issue['recommended_action'])
        for doc in issue.get('documentation', []):
            print('    docs:     ' + doc['url'])
        print()


def _print_summary(title, summary):
    print(_c(title, '1'))
    rows = [('Host', 'host'), ('ROS distro', 'ros_distro'), ('Domain ID', 'domain_id'), ('RMW', 'rmw'),
            ('Discovery range', 'discovery_range'), ('In container', 'container'),
            ('Nodes visible', 'node_count'), ('Topics visible', 'topic_count')]
    for label, key in rows:
        value = summary.get(key)
        if isinstance(value, bool):
            value = 'yes' if value else 'no'
        elif value in (None, ''):
            value = 'default' if key in ('rmw', 'discovery_range') else '—'
        print(f'  {label:<16} {value}')
    print()


def _load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise SystemExit(_usage_error(f'File not found: {path}'))
    except json.JSONDecodeError as e:
        raise SystemExit(_usage_error(f'{path} is not valid JSON ({e.msg}, line {e.lineno})'))
    if not isinstance(data, dict) or 'environment' not in data:
        raise SystemExit(_usage_error(f'{path} is not an AutoDiag snapshot (missing "environment")'))
    return data


def _usage_error(message):
    print(_c('error: ', '31;1') + message, file=sys.stderr)
    return EXIT_USAGE


def _write_or_print(text, output):
    if output and output != '-':
        Path(output).write_text(text if text.endswith('\n') else text + '\n', encoding='utf-8')
        print(f'Wrote {output}', file=sys.stderr)
    else:
        print(text)


# ---------- commands ----------

def cmd_check(args):
    from .collector import collect, summarize
    from .transport import health, transport_diagnose
    from .report import markdown_report
    local = _load_json(args.snapshot) if args.snapshot else collect()
    local.setdefault('transport', {})['requested_mode'] = args.transport
    peer = _load_json(args.peer) if args.peer else None
    issues = transport_diagnose(local, peer)
    state = health(local, issues)
    if args.report:
        _write_or_print(markdown_report(local, peer, issues, state), args.report)
    if args.json:
        print(json.dumps({'health': state, 'issues': issues, 'remote_snapshot_provided': bool(peer)}, indent=2))
    else:
        _print_summary('This host' if not args.snapshot else f'Snapshot {args.snapshot}', summarize(local))
        if peer:
            _print_summary(f'Peer {args.peer}', summarize(peer))
        _print_issues(issues)
        print(_c('Status: ', '1') + state['summary'])
    return EXIT_ISSUES if state['status'] == 'issue_detected' else EXIT_OK


def cmd_collect(args):
    from .collector import collect
    from .redact import redact_snapshot
    snapshot = collect()
    snapshot['transport']['requested_mode'] = args.transport
    if args.redact:
        snapshot = redact_snapshot(snapshot, salt=args.salt or '')
    _write_or_print(json.dumps(snapshot, indent=2), args.output)
    return EXIT_OK


def cmd_compare(args):
    args.snapshot = args.other if args.other else None
    args.peer = args.peer_snapshot
    return cmd_check(args)


def cmd_topics(args):
    from .live import topic_list
    result = topic_list()
    if args.json:
        print(json.dumps(result, indent=2))
    elif result['state'] != 'ok':
        return _usage_error(result.get('error') or result['state'])
    else:
        width = max((len(t['topic']) for t in result['topics']), default=5)
        for t in result['topics']:
            print(f"{t['topic']:<{width}}  {_c(t['type'], '2')}")
        print(f"\n{len(result['topics'])} topic(s)", file=sys.stderr)
    return EXIT_OK if result['state'] == 'ok' else EXIT_USAGE


def cmd_inspect(args):
    from .live import inspect_topic
    result = inspect_topic(args.topic)
    if args.json:
        print(json.dumps(result, indent=2))
        return EXIT_ISSUES if result.get('findings') else (EXIT_OK if result.get('state') == 'ok' else EXIT_USAGE)
    if result.get('state') != 'ok':
        return _usage_error(result.get('error') or result.get('state'))
    print(_c(args.topic, '1'), f"— {result['publisher_count']} publisher(s), {result['subscriber_count']} subscriber(s)\n")
    for e in result['endpoints']:
        q = e.get('qos', {})
        print(f"  {e['kind']:<10} {e['node']:<34} reliability={q.get('reliability', '?'):<12} durability={q.get('durability', '?')}")
    print()
    _print_issues(result['findings'])
    return EXIT_ISSUES if result['findings'] else EXIT_OK


def cmd_sample(args):
    from .live import sample_topic
    result = sample_topic(args.topic, args.timeout, args.reliability)
    if args.json:
        print(json.dumps(result, indent=2))
    elif result['state'] == 'ok':
        print(result['raw'] + ('\n[truncated]' if result['truncated'] else ''))
    elif result['state'] == 'timeout':
        print(f'No message on {args.topic} within {args.timeout} s. The publisher may be idle, or QoS/transport may '
              'block delivery. Try --reliability best_effort.', file=sys.stderr)
    else:
        return _usage_error(result.get('error') or result['state'])
    return EXIT_OK if result['state'] == 'ok' else EXIT_ISSUES


def cmd_selftest(args):
    from .validation import run_all
    result = run_all()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for r in result['results']:
            mark = _c('PASS', '32;1') if r['passed'] else _c('FAIL', '31;1')
            print(f"{mark}  {r['fixture']:<32} {r['description']}")
        print(f"\n{result['passed']}/{result['total']} rules passed")
    return EXIT_OK if result['ok'] else EXIT_ISSUES


def cmd_doctor(args):
    """Is this machine ready to run AutoDiag? Prints what is missing and how to fix it."""
    from .collector import run
    from .enhanced import discover_local_containers, ollama_status
    from .cpp_bridge import binary_path
    from .bt_visualizer import _binary
    checks = []

    def add(name, ok, detail, fix='', required=False):
        checks.append({'name': name, 'ok': ok, 'detail': detail, 'fix': fix, 'required': required})

    add('Python', sys.version_info >= (3, 10), sys.version.split()[0], 'Use Python 3.10 or newer.', True)
    ros2 = shutil.which('ros2')
    distro = os.environ.get('ROS_DISTRO')
    add('ros2 CLI on PATH', bool(ros2), ros2 or 'not found', 'Install ROS 2 and source /opt/ros/<distro>/setup.bash.', True)
    add('ROS 2 environment sourced', bool(distro), f'ROS_DISTRO={distro}' if distro else 'ROS_DISTRO not set',
        'Run: source /opt/ros/<distro>/setup.bash (in the same shell that starts AutoDiag).', True)
    if ros2 and distro:
        probe = run(['ros2', 'topic', 'list', '--no-daemon'], 10)
        add('ROS graph query', probe['state'] == 'ok',
            f"{len(probe.get('stdout', '').split())} topic(s) visible" if probe['state'] == 'ok' else (probe.get('stderr') or probe.get('error') or probe['state']).strip()[-200:],
            'Check that the ROS 2 installation works: ros2 topic list', True)
    docker = discover_local_containers()
    add('Docker (optional)', docker['state'] == 'ok',
        f"{len(docker['environments'])} running container(s)" if docker['state'] == 'ok' else docker['reason'],
        'Install Docker and add your user to the "docker" group to list containers.')
    ollama = ollama_status()
    add('Local AI via Ollama (optional)', ollama['state'] == 'ready', ollama['message'],
        f"ollama serve && ollama pull {ollama.get('expected_model', 'qwen3:4b')}")
    add('Native C++ core (optional)', binary_path().is_file(), str(binary_path()),
        'cmake -S cpp -B cpp/build && cmake --build cpp/build')
    add('BehaviorTree.CPP runner (optional)', _binary() is not None, 'built' if _binary() else 'not built',
        'Install BehaviorTree.CPP v4 (ros-$ROS_DISTRO-behaviortree-cpp) and rebuild the C++ core.')
    if args.json:
        print(json.dumps({'checks': checks, 'ready': all(c['ok'] for c in checks if c['required'])}, indent=2))
    else:
        for c in checks:
            mark = _c('✔', '32;1') if c['ok'] else (_c('✖', '31;1') if c['required'] else _c('–', '33'))
            print(f"{mark} {c['name']:<34} {c['detail']}")
            if not c['ok'] and c['fix']:
                print(f"    fix: {c['fix']}")
        ready = all(c['ok'] for c in checks if c['required'])
        print('\n' + (_c('Ready.', '32;1') + ' Start the dashboard with: dds-autodiag serve' if ready
                      else _c('Not ready:', '31;1') + ' fix the required items above.'))
    return EXIT_OK if all(c['ok'] for c in checks if c['required']) else EXIT_ISSUES


def _is_loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def cmd_serve(args):
    try:
        import uvicorn
    except ImportError:
        return _usage_error('uvicorn is not installed: pip install "ros2-dds-autodiag"')
    if not _is_loopback(args.host) and not os.environ.get('AUTODIAG_UI_TOKEN') and not args.insecure_no_auth:
        return _usage_error(
            f'Refusing to listen on {args.host} without authentication. The dashboard runs ROS 2 and Docker '
            'commands on this machine.\n  Set AUTODIAG_UI_TOKEN=<long random secret>, use an SSH tunnel to '
            '127.0.0.1, or pass --insecure-no-auth on an isolated network.')
    if not _is_loopback(args.host):
        hosts = os.environ.get('AUTODIAG_ALLOWED_HOSTS', '')
        if not hosts:
            print(_c('note: ', '33;1') + 'set AUTODIAG_ALLOWED_HOSTS to the hostname/IP clients use '
                  '(e.g. AUTODIAG_ALLOWED_HOSTS=192.168.1.20); other Host headers are rejected.', file=sys.stderr)
    if not os.environ.get('ROS_DISTRO'):
        print(_c('warning: ', '33;1') + 'ROS 2 is not sourced in this shell; live ROS checks will be unavailable. '
              'Run `source /opt/ros/<distro>/setup.bash` first.', file=sys.stderr)
    display = f'[{args.host}]' if ':' in args.host else args.host
    url = f'http://{"127.0.0.1" if args.host in ("0.0.0.0", "::") else display}:{args.port}'
    print(f'DDS AutoDiag {__version__} — dashboard at {_c(url, "1;4")}  (Ctrl+C to stop)', file=sys.stderr)
    if args.open:
        import threading, webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    from .config import settings
    uvicorn.run('autodiag.server:app', host=args.host, port=args.port, log_level=args.log_level or settings().log_level.lower(),
                proxy_headers=False, server_header=False)
    return EXIT_OK


# ---------- argument parsing ----------

def build_parser():
    ap = argparse.ArgumentParser(prog='dds-autodiag', description='Read-only ROS 2 / DDS communication diagnostics.',
                                 epilog='Run "dds-autodiag <command> -h" for command help. Start with "dds-autodiag doctor".')
    ap.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    # Pre-1.0 interface, kept for scripts.
    legacy = ap.add_argument_group('legacy options (pre-1.0)')
    legacy.add_argument('--collect', action='store_true', help=argparse.SUPPRESS)
    legacy.add_argument('--compare', metavar='OTHER_JSON', help=argparse.SUPPRESS)
    legacy.add_argument('--health', action='store_true', help=argparse.SUPPRESS)
    legacy.add_argument('--transport', choices=MODES, default='auto', help=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest='command', metavar='<command>')

    def common(p, json_flag=True):
        if json_flag:
            p.add_argument('--json', action='store_true', help='machine-readable JSON output')
        return p

    p = common(sub.add_parser('check', help='diagnose this host (default command)'))
    p.add_argument('--peer', metavar='SNAPSHOT.json', help='also compare with a snapshot from another PC/container')
    p.add_argument('--snapshot', metavar='SNAPSHOT.json', help='diagnose a saved snapshot instead of this host')
    p.add_argument('--transport', choices=MODES, default='auto', help='transport you expect the nodes to use')
    p.add_argument('--report', metavar='FILE.md', help='also write a Markdown report ("-" for stdout)')
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('collect', help='print or save a snapshot of this host for comparison elsewhere')
    p.add_argument('-o', '--output', metavar='FILE', help='write to FILE instead of stdout')
    p.add_argument('--redact', action='store_true', help='hash hostnames, IPs and home paths before sharing')
    p.add_argument('--salt', help='redaction salt; use the same value on both hosts to keep them comparable')
    p.add_argument('--transport', choices=MODES, default='auto')
    p.set_defaults(func=cmd_collect)

    p = common(sub.add_parser('compare', help='compare this host (or OTHER) with a peer snapshot'))
    p.add_argument('peer_snapshot', metavar='PEER.json')
    p.add_argument('other', nargs='?', metavar='OTHER.json', help='use this snapshot instead of the local host')
    p.add_argument('--transport', choices=MODES, default='auto')
    p.add_argument('--report', metavar='FILE.md', help='also write a Markdown report')
    p.set_defaults(func=cmd_compare)

    p = common(sub.add_parser('topics', help='list topics visible in the ROS graph'))
    p.set_defaults(func=cmd_topics)

    p = common(sub.add_parser('inspect', help='show publishers/subscribers and QoS compatibility for a topic'))
    p.add_argument('topic')
    p.set_defaults(func=cmd_inspect)

    p = common(sub.add_parser('sample', help='read one live message from a topic'))
    p.add_argument('topic')
    p.add_argument('--timeout', type=int, default=8, choices=range(1, 16), metavar='1-15', help='seconds to wait (default 8)')
    p.add_argument('--reliability', choices=('auto', 'best_effort', 'reliable'), default='auto')
    p.set_defaults(func=cmd_sample)

    p = common(sub.add_parser('selftest', help='verify every diagnostic rule against synthetic faults'))
    p.set_defaults(func=cmd_selftest)

    p = common(sub.add_parser('doctor', help='check that this machine is ready to run AutoDiag'))
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser('serve', help='start the web dashboard')
    p.add_argument('--host', default=os.environ.get('AUTODIAG_HOST', '127.0.0.1'), help='bind address (default 127.0.0.1)')
    p.add_argument('--port', type=int, default=int(os.environ.get('AUTODIAG_PORT', '8080')), help='port (default 8080)')
    p.add_argument('--open', action='store_true', help='open the dashboard in a browser')
    p.add_argument('--log-level', choices=('critical', 'error', 'warning', 'info', 'debug'))
    p.add_argument('--insecure-no-auth', action='store_true', help='allow a non-loopback bind without AUTODIAG_UI_TOKEN')
    p.set_defaults(func=cmd_serve)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        if args.command:
            return args.func(args)
        if args.collect:
            args.output, args.redact, args.salt = None, False, None
            return cmd_collect(args)
        # Legacy default (also --health / --compare): diagnose, JSON output.
        args.snapshot, args.peer, args.report, args.json = None, args.compare, None, True
        if not (args.health or args.compare) and sys.stdout.isatty():
            args.json = False
        return cmd_check(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
