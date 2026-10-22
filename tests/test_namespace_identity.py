"""Preserve CLI endpoint identity through inspection and graph construction."""
import unittest
from unittest.mock import patch

from autodiag.graph import build_graph
from autodiag.live import _parse_verbose


def verbose_pair(pub_ns='/robot1', sub_ns='/robot2', reliability='BEST_EFFORT'):
    return f'''Type: sensor_msgs/msg/LaserScan
Publisher count: 1
Node name: sensor
Node namespace: {pub_ns}
Topic type: sensor_msgs/msg/LaserScan
Endpoint type: PUBLISHER
GID: 01.01
QoS profile:
  Reliability: {reliability}
  Durability: VOLATILE
Subscription count: 1
Node name: sensor
Node namespace: {sub_ns}
Topic type: sensor_msgs/msg/LaserScan
Endpoint type: SUBSCRIPTION
GID: 02.02
QoS profile:
  Reliability: RELIABLE
  Durability: VOLATILE
'''


def cli_graph(stdout):
    with patch('autodiag.graph.discover_all', return_value=None), \
         patch('autodiag.live._call', side_effect=lambda args, **kwargs: {
             'state': 'ok', 'stdout': '/scan [sensor_msgs/msg/LaserScan]\n'
             if args[:2] == ['topic', 'list'] else stdout}):
        return build_graph()


class NamespaceIdentityTests(unittest.TestCase):
    def test_parser_preserves_namespace_and_endpoint_metadata(self):
        for namespace, expected in [('/', 'sensor'), ('/robot1', 'robot1/sensor'),
                                    ('/fleet/robot1', 'fleet/robot1/sensor')]:
            with self.subTest(namespace=namespace):
                endpoints = _parse_verbose(verbose_pair(pub_ns=namespace))
                self.assertEqual(endpoints[0]['node'], expected)
                self.assertEqual(endpoints[0]['gid'], '01.01')
                self.assertEqual(endpoints[0]['kind'], 'publisher')
                self.assertEqual(endpoints[1]['kind'], 'subscriber')

    def test_legacy_output_without_namespace_still_parses(self):
        stdout = '\n'.join(line for line in verbose_pair().splitlines()
                           if not line.startswith('Node namespace:'))
        self.assertEqual([e['node'] for e in _parse_verbose(stdout)], ['sensor', 'sensor'])

    def test_cli_graph_retains_distinct_nodes_and_their_qos_error(self):
        graph = cli_graph(verbose_pair())
        self.assertEqual({n['id'] for n in graph['nodes']}, {'robot1/sensor', 'robot2/sensor'})
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['edges'][0]['status'], 'error')
        self.assertEqual(graph['counts']['error'], 1)
        self.assertEqual([f['code'] for f in graph['edges'][0]['topics'][0]['findings']],
                         ['RELIABILITY_MISMATCH'])

    def test_compatible_connection_is_not_lost(self):
        graph = cli_graph(verbose_pair(reliability='RELIABLE'))
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['edges'][0]['status'], 'ok')
        self.assertEqual(graph['counts']['ok'], 1)

    def test_same_full_node_name_keeps_existing_self_edge_suppression(self):
        graph = cli_graph(verbose_pair(pub_ns='/robot1', sub_ns='/robot1'))
        self.assertEqual([n['id'] for n in graph['nodes']], ['robot1/sensor'])
        self.assertEqual(graph['edges'], [])

    def test_cli_and_native_snapshot_use_the_same_identity(self):
        for pub_ns, sub_ns, names in [
            ('/robot1', '/robot2', ['robot1/sensor', 'robot2/sensor']),
            ('/fleet/a', '/fleet/b', ['fleet/a/sensor', 'fleet/b/sensor']),
            ('/', '/robot2', ['sensor', 'robot2/sensor']),
        ]:
            with self.subTest(names=names):
                stdout = verbose_pair(pub_ns, sub_ns)
                native_endpoints = _parse_verbose(stdout)
                for endpoint, name in zip(native_endpoints, names):
                    endpoint['node'] = name
                with patch('autodiag.graph.discover_all', return_value={'/scan': native_endpoints}):
                    native = build_graph()
                cli = cli_graph(stdout)
                for field in ('nodes', 'edges', 'counts', 'waiting'):
                    self.assertEqual(cli[field], native[field])


if __name__ == '__main__':
    unittest.main()
