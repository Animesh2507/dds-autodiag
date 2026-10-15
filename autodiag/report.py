"""Human-readable Markdown diagnostic report (for tickets, chat, pull requests)."""
from __future__ import annotations
from datetime import datetime, timezone
from . import __version__
from .collector import summarize

SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}
ICON = {'error': '❌', 'warning': '⚠️', 'info': 'ℹ️'}


def _cell(value) -> str:
    if isinstance(value, bool):
        value = 'yes' if value else 'no'
    return str('—' if value in (None, '') else value).replace('|', '\\|').replace('\n', ' ')


def sort_issues(issues):
    return sorted(issues, key=lambda i: (SEVERITY_ORDER.get(i.get('severity'), 3), str(i.get('code'))))


def markdown_report(host_a: dict, host_b: dict | None, issues: list, health: dict) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    a, b = summarize(host_a), summarize(host_b) if host_b else None
    out = [f'# DDS AutoDiag report', '',
           f'Generated {now} by DDS AutoDiag {__version__}. Read-only checks; '
           'a clean result does not prove that messages are delivered.', '',
           f'**Status:** {health.get("status", "unknown")} — {health.get("summary", "")}', '',
           '## Environments', '',
           '| | Host A' + (' | Host B |' if b else ' |'),
           '|---|---' + ('|---|' if b else '|')]
    rows = [('Host', 'host'), ('ROS distro', 'ros_distro'), ('Domain ID', 'domain_id'), ('RMW', 'rmw'),
            ('Discovery range', 'discovery_range'), ('Container', 'container'), ('Nodes visible', 'node_count'),
            ('Topics visible', 'topic_count')]
    def value(summary, key):
        # Unset RMW / discovery range means the distribution default, not "unknown".
        return summary.get(key) or 'default' if key in ('rmw', 'discovery_range') else summary.get(key)

    for label, key in rows:
        out.append(f'| {label} | {_cell(value(a, key))}' + (f' | {_cell(value(b, key))} |' if b else ' |'))
    out += ['', f'## Findings ({len(issues)})', '']
    if not issues:
        out.append('No configured rule detected a problem. Verify data delivery with a live sample before concluding the system is healthy.')
    for issue in sort_issues(issues):
        sev = issue.get('severity', 'info')
        out += [f'### {ICON.get(sev, "")} {issue.get("code")} ({sev}, confidence: {issue.get("confidence", "unknown")})', '',
                issue.get('summary', ''), '']
        if issue.get('evidence'):
            out.append('Evidence: ' + ', '.join(f'`{k}={v}`' for k, v in issue['evidence'].items()))
            out.append('')
        if issue.get('recommended_action'):
            out += [f'**Next step:** {issue["recommended_action"]}', '']
        for doc in issue.get('documentation', []):
            out.append(f'- [{doc.get("label")}]({doc.get("url")})')
        out.append('')
    checks = health.get('checks', {})
    if checks:
        out += ['## Evidence coverage', '', '| Check | State |', '|---|---|']
        out += [f'| {k} | {_cell(v)} |' for k, v in checks.items()]
        out.append('')
    return '\n'.join(out)
