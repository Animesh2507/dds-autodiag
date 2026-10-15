"""Explicit, opt-in remote snapshot collection; never performs remote commands."""
import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler

def fetch_snapshot(url, token, timeout=4):
    u=urlsplit(url)
    if u.scheme not in ('http','https') or u.username or u.password or u.query or u.fragment or u.path not in ('','/','/api/agent/snapshot'):
        raise ValueError('Use a plain http(s) URL to an explicitly configured collector.')
    if not token: raise ValueError('A remote collector token is required.')
    # Private/loopback IPs only: deliberately do not resolve arbitrary external hostnames.
    try: ip=ipaddress.ip_address(u.hostname or '')
    except ValueError as exc: raise ValueError('Use a numeric private/loopback IP, not a hostname.') from exc
    if not (ip.is_private or ip.is_loopback) or ip.is_link_local or ip.is_unspecified:
        raise ValueError('Only private-network or loopback collector IPs are supported.')
    endpoint=f'{u.scheme}://[{ip}]' if ip.version==6 else f'{u.scheme}://{ip}'
    endpoint+=f':{u.port}' if u.port else ''
    req=Request(endpoint+'/api/agent/snapshot',headers={'X-Autodiag-Token':token,'Accept':'application/json'})
    # urllib respects system proxy environment; disable it to avoid sending auth tokens to a proxy.
    from urllib.request import build_opener, ProxyHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise ValueError("Remote collector redirects are not permitted")
    with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=timeout) as r:
        if r.status!=200:raise ValueError('Remote collector rejected request')
        raw=r.read(300_001)
        if len(raw)>300_000:raise ValueError('Remote snapshot exceeds size limit')
    data=json.loads(raw)
    if not isinstance(data,dict) or 'identity' not in data or 'environment' not in data:
        raise ValueError('Remote snapshot schema invalid')
    return data
