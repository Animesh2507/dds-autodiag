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
