"""Snapshot redaction for sharing (bug reports, forums, support tickets).

Identifying values are replaced by short stable hashes so that two snapshots
redacted with the same salt still compare correctly (same host -> same token).
Diagnostic signal (domain IDs, RMW, QoS, namespaces, interface flags) is kept.
"""
from __future__ import annotations
import copy
import hashlib
import ipaddress
import re

_IPV4 = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_IPV6 = re.compile(r'\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{0,4}\b', re.I)
_PATH = re.compile(r'(?<![\w.])/(?:home|Users|root)/[^\s"\';,]+')


def _token(kind: str, value: str, salt: str) -> str:
    return f'{kind}-' + hashlib.sha256((salt + value).encode()).hexdigest()[:8]


def _ip(match: re.Match, salt: str) -> str:
    text = match.group(0)
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return text
    # Loopback/unspecified addresses carry diagnostic meaning and identify no one.
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        return text
    return _token('ip', text, salt)


def redact_text(text: str, salt: str = '', host: str | None = None) -> str:
    # Very short hostnames would mangle unrelated text, so they are only replaced in identity.
    if host and len(host) >= 3:
        text = text.replace(host, _token('host', host, salt))
    text = _IPV4.sub(lambda m: _ip(m, salt), text)
    text = _IPV6.sub(lambda m: _ip(m, salt), text)
    return _PATH.sub(lambda m: _token('path', m.group(0), salt), text)


def redact_snapshot(snapshot: dict, salt: str = '') -> dict:
    """Return a redacted deep copy; the input is not modified."""
    out = copy.deepcopy(snapshot)
    host = (out.get('identity') or {}).get('host')

    def walk(value):
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            return redact_text(value, salt, host)
        return value

    out = walk(out)
    if isinstance(out.get('identity'), dict):
        if host:
            out['identity']['host'] = _token('host', host, salt)
    out['redacted'] = True
    return out


def mask_for_cloud(value, node_labels: dict | None = None):
    """Copy of findings/prompt text that is safe to send to a cloud AI provider.

    Node names become neutral labels (``publisher 1``), and this machine's hostname,
    IP addresses and home-directory paths are replaced with tokens. QoS, topic names,
    message types and rule codes are kept: the diagnosis needs them.
    """
    import socket
    names = sorted((node_labels or {}).items(), key=lambda kv: -len(kv[0]))
    patterns = [(re.compile(r'(?<![\w/])' + re.escape(name) + r'(?!\w)'), label) for name, label in names if name]
    host = socket.gethostname()

    def text(s: str) -> str:
        for pattern, label in patterns:
            s = pattern.sub(label, s)
        return redact_text(s, '', host)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return text(v) if isinstance(v, str) else v

    return walk(value)


def node_labels(endpoints: list) -> dict:
    """{node name: 'publisher 1' | 'subscriber 1' ...} in discovery order."""
    labels, counts = {}, {}
    for e in endpoints:
        name, kind = e.get('node'), e.get('kind') or 'node'
        if name and name not in labels:
            counts[kind] = counts.get(kind, 0) + 1
            labels[name] = f'{kind} {counts[kind]}'
    return labels
