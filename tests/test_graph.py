import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from autodiag.graph import build_graph
from autodiag.server import app


def ep(kind, node, reliability='RELIABLE', durability='VOLATILE', type_='sensor_msgs/msg/LaserScan'):
    return {'kind': kind, 'node': node, 'type': type_, 'qos': {'reliability': reliability, 'durability': durability}}


GRAPH = {
    '/scan': [ep('publisher', 'lidar', reliability='BEST_EFFORT'), ep('subscriber', 'rviz'), ep('subscriber', 'slam',
              reliability='BEST_EFFORT')],
    '/map': [ep('publisher', 'map_server', durability='TRANSIENT_LOCAL', type_='nav_msgs/msg/OccupancyGrid'),
             ep('subscriber', 'rviz', type_='nav_msgs/msg/OccupancyGrid')],
    '/cmd_vel': [ep('subscriber', 'base_driver', type_='geometry_msgs/msg/Twist')],
    '/rosout': [ep('publisher', 'lidar'), ep('subscriber', '_ros2cli_123')],
}


def lister():
    return {'state': 'ok', 'topics': [{'topic': t, 'type': ''} for t in GRAPH]}


def inspector(topic):
    return {'state': 'ok', 'endpoints': GRAPH[topic]}


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.g = build_graph(lister=lister, inspector=inspector)
        self.edges = {e['id']: e for e in self.g['edges']}

    def test_each_connection_is_coloured_by_its_own_rules(self):
        self.assertEqual(self.edges['lidar->rviz']['status'], 'error')
        self.assertEqual(self.edges['lidar->rviz']['topics'][0]['findings'][0]['code'], 'RELIABILITY_MISMATCH')
        self.assertEqual(self.edges['lidar->slam']['status'], 'ok')
        self.assertEqual(self.edges['map_server->rviz']['topics'][0]['findings'][0]['code'],
                         'LATCHED_DATA_VOLATILE_SUBSCRIBER')
        self.assertEqual(self.g['edges'][0]['status'], 'error')  # worst first
        self.assertEqual(self.g['counts'], {'ok': 1, 'warning': 1, 'error': 1, 'waiting': 1})

    def test_subscriber_without_publisher_is_waiting(self):
        self.assertEqual(self.g['waiting'], [{'topic': '/cmd_vel', 'subscribers': ['base_driver'],
                                              'type': 'geometry_msgs/msg/Twist'}])

    def test_infrastructure_topics_and_cli_probes_hidden(self):
        ids = {n['id'] for n in self.g['nodes']}
        self.assertNotIn('_ros2cli_123', ids)  # only on /rosout, which is hidden
        self.assertNotIn('/rosout', {t['topic'] for e in self.g['edges'] for t in e['topics']})
        shown = build_graph(include_hidden=True, lister=lister, inspector=inspector)
        self.assertEqual(shown['topics_total'], 4)

    def test_topic_limit(self):
        g = build_graph(max_topics=1, lister=lister, inspector=inspector)
        self.assertTrue(g['truncated'])
        self.assertEqual(g['topics_inspected'], 1)

    def test_discovery_failure_is_reported(self):
        g = build_graph(lister=lambda: {'state': 'unavailable', 'error': 'ros2 CLI is not on PATH.', 'topics': []})
        self.assertEqual(g['state'], 'unavailable')
        self.assertEqual(g['edges'], [])

    def test_api(self):
        with patch('autodiag.server.build_graph', return_value={'state': 'ok', 'nodes': [], 'edges': []}) as built:
            r = TestClient(app).get('/api/graph?max_topics=5')
        self.assertEqual(r.status_code, 200)
        built.assert_called_once_with(5, False)


if __name__ == '__main__':
    unittest.main()
