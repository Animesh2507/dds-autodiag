"""Diagnosis graph: who talks to whom, and which connections are broken.

Every publisher -> subscriber pair on every visible topic becomes an edge, coloured by the
same QoS/type rules as `inspect` (live._qos_findings run on just that pair). Subscribers
with no publisher are reported as "waiting", the classic empty display.

Discovery runs once for the whole graph in a short-lived rclpy process (one DDS participant
that only listens), so every topic is seen from the same moment. Without rclpy it falls back
to `ros2 topic list` plus `ros2 topic info --verbose` per topic. Read-only either way.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .config import discovery_seconds
from .live import _qos_findings, inspect_topic, topic_list

_DISCOVER = r"""
import json, sys, time
import rclpy
from rclpy.node import Node


def snapshot(node):
    graph = {}
    for topic, _types in node.get_topic_names_and_types():
        endpoints = []
        for kind, query in (('publisher', node.get_publishers_info_by_topic),
                            ('subscriber', node.get_subscriptions_info_by_topic)):
            for info in query(topic):
                ns = info.node_namespace.strip('/')
                endpoints.append({'kind': kind, 'node': (ns + '/' if ns else '') + info.node_name,
                                  'type': info.topic_type,
                                  'qos': {'reliability': info.qos_profile.reliability.name,
                                          'durability': info.qos_profile.durability.name}})
        graph[topic] = endpoints
    return graph


rclpy.init()
node = Node('_autodiag_graph_probe')
start, minimum, limit = time.monotonic(), float(sys.argv[1]), float(sys.argv[2])
graph, stable_since = {}, None


def complete(graph):
    # Endpoints arrive after their node. Every node publishes /rosout, so once every known node has its
    # /rosout publisher, that node's endpoints have been discovered too.
    names = {(ns.strip('/') + '/' if ns.strip('/') else '') + n for n, ns in node.get_node_names_and_namespaces()}
    return names <= {e['node'] for e in graph.get('/rosout', []) if e['kind'] == 'publisher'}


# Discovery trickles in: wait at least `minimum`, then until every node's endpoints are in and nothing
# changed for 1 s (or `limit`).
while True:
    rclpy.spin_once(node, timeout_sec=0.25)
    current = snapshot(node)
    now = time.monotonic()
    if current != graph:
        graph, stable_since = current, now
    if now - start >= limit or (now - start >= minimum and now - stable_since >= 1.0 and complete(graph)):
        break
print(json.dumps(graph))
node.destroy_node()
rclpy.shutdown()
"""

# Present on every ROS 2 system; they would only clutter the picture.
HIDDEN_TOPICS = ('/rosout', '/parameter_events')
# Optional companion topics that RViz always subscribes to; nobody publishing them is normal, not a problem.
OPTIONAL_SUFFIXES = ('_updates',)
MAX_TOPICS = 60
_RANK = {'ok': 0, 'warning': 1, 'error': 2}


def _status(findings: list) -> str:
    severities = {f.get('severity') for f in findings}
    return 'error' if 'error' in severities else 'warning' if 'warning' in severities else 'ok'


def discover_all() -> dict | None:
    """{topic: [endpoint, ...]} from one rclpy discovery pass, or None when rclpy is unavailable."""
    if not os.environ.get('ROS_DISTRO') or not shutil.which('ros2'):
        return None
    wait = max(float(discovery_seconds()), 3.0)
    try:
        p = subprocess.run([sys.executable, '-c', _DISCOVER, str(wait), str(wait + 6)], capture_output=True,
                           text=True, timeout=wait + 20, check=False)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def build_graph(max_topics: int = 40, include_hidden: bool = False, lister=None, inspector=inspect_topic) -> dict:
    started = time.monotonic()
    snapshot = discover_all() if lister is None else None
    if snapshot is not None:
        listing = {'state': 'ok', 'topics': [{'topic': t} for t in snapshot]}
        inspector = lambda topic: {'state': 'ok', 'endpoints': snapshot.get(topic, [])}  # noqa: E731
    else:
        listing = (lister or topic_list)()
    if listing.get('state') != 'ok':
        return {'state': listing.get('state', 'error'), 'error': listing.get('error') or 'Topic discovery failed.',
                'nodes': [], 'edges': [], 'waiting': []}
    names = [t['topic'] for t in listing['topics'] if include_hidden or t['topic'] not in HIDDEN_TOPICS]
    max_topics = max(1, min(int(max_topics), MAX_TOPICS))
    selected = sorted(names)[:max_topics]
    # The CLI fallback starts one process per topic; a few at a time keeps discovery reliable.
    with ThreadPoolExecutor(max_workers=1 if snapshot is not None else 4) as pool:
        reports = list(pool.map(inspector, selected))

    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}
    waiting, failed = [], []

    def node(name, role, topic):
        entry = nodes.setdefault(name, {'id': name, 'publishes': [], 'subscribes': []})
        bucket = entry['publishes' if role == 'publisher' else 'subscribes']
        if topic not in bucket:
            bucket.append(topic)

    for topic, report in zip(selected, reports):
        if report.get('state') != 'ok':
            failed.append({'topic': topic, 'error': report.get('error') or report.get('state')})
            continue
        endpoints = [e for e in report.get('endpoints', []) if e.get('node')]
        pubs = [e for e in endpoints if e['kind'] == 'publisher']
        subs = [e for e in endpoints if e['kind'] == 'subscriber']
        for e in endpoints:
            node(e['node'], e['kind'], topic)
        if subs and not pubs and not topic.endswith(OPTIONAL_SUFFIXES):
            waiting.append({'topic': topic, 'subscribers': sorted({s['node'] for s in subs}),
                            'type': next((s.get('type') for s in subs if s.get('type')), '')})
        for p in pubs:
            for s in subs:
                if p['node'] == s['node']:
                    continue
                findings = _qos_findings([p, s])
                key = (p['node'], s['node'])
                edge = edges.setdefault(key, {'id': f'{p["node"]}->{s["node"]}', 'source': p['node'],
                                              'target': s['node'], 'status': 'ok', 'topics': []})
                link = next((t for t in edge['topics'] if t['topic'] == topic), None)
                if link is None:
                    link = {'topic': topic, 'type': p.get('type') or s.get('type') or '', 'status': 'ok', 'findings': [],
                            'publisher_qos': p.get('qos', {}), 'subscriber_qos': s.get('qos', {})}
                    edge['topics'].append(link)
                # A node can hold several endpoints on one topic (RViz does); report each problem once.
                link['findings'].extend(f for f in findings if f not in link['findings'])
                link['status'] = _status(link['findings'])
                if _RANK[link['status']] > _RANK[edge['status']]:
                    edge['status'] = link['status']

    edge_list = sorted(edges.values(), key=lambda e: (-_RANK[e['status']], e['source'], e['target']))
    counts = {s: sum(1 for e in edge_list for t in e['topics'] if t['status'] == s) for s in ('ok', 'warning', 'error')}
    counts['waiting'] = len(waiting)
    return {'state': 'ok', 'nodes': sorted(nodes.values(), key=lambda n: n['id']), 'edges': edge_list,
            'waiting': waiting, 'failed': failed, 'counts': counts,
            'topics_total': len(names), 'topics_inspected': len(selected), 'truncated': len(names) > len(selected),
            'hidden_topics': [] if include_hidden else list(HIDDEN_TOPICS),
            'seconds': round(time.monotonic() - started, 2),
            'discovery': 'single rclpy pass' if snapshot is not None else 'ros2 CLI per topic',
            'limitations': ['Discovery shows which endpoints exist and whether their QoS is compatible; it does not '
                            'prove that messages are delivered. Read a live sample to confirm.']}
