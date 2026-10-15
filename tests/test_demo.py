import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

from autodiag import cli, demo


def report(topic):
    """A live inspection result that contains the problem each scenario is built to show."""
    scenario = next(s for s in demo.SCENARIOS if s.topic == topic)
    return {'state': 'ok', 'publisher_count': 1, 'subscriber_count': 1, 'endpoints': [],
            'findings': [{'code': scenario.expected, 'severity': 'warning', 'summary': 's'}]}


class DemoCommandTests(unittest.TestCase):
    def test_scenarios_use_their_own_namespace_and_conflicting_qos(self):
        for scenario in demo.SCENARIOS:
            self.assertTrue(scenario.topic.startswith('/autodiag_demo/'))
            self.assertNotEqual(scenario.pub_qos, scenario.sub_qos)
            pub, sub = demo.commands(scenario)
            self.assertEqual(pub[:3], ['ros2', 'topic', 'pub'])
            self.assertEqual(sub[:3], ['ros2', 'topic', 'echo'])
            self.assertIn(scenario.pub_qos[0], pub)
            self.assertIn(scenario.sub_qos[1], sub)

    def test_unavailable_without_ros(self):
        with patch('autodiag.demo.shutil.which', return_value=None):
            self.assertIn('ros2 CLI not found', demo.available())
        with patch('autodiag.demo.shutil.which', return_value='/usr/bin/ros2'), patch.dict('os.environ', {}, clear=True):
            self.assertIn('not sourced', demo.available())

    def test_processes_are_stopped_on_exit(self):
        proc = MagicMock(pid=4242)
        proc.poll.return_value = None
        with patch('autodiag.demo.subprocess.Popen', return_value=proc) as popen, \
             patch('autodiag.demo.os.killpg') as killpg:
            with demo.Demo():
                pass
        self.assertEqual(popen.call_count, 2 * len(demo.SCENARIOS))
        self.assertTrue(all(c.kwargs['start_new_session'] for c in popen.call_args_list))
        self.assertTrue(killpg.called)

    def test_cli_demo_reports_found_problems(self):
        running = MagicMock()
        running.alive.return_value = True
        manager = MagicMock()
        manager.__enter__.return_value = running
        out = StringIO()
        with patch('autodiag.demo.available', return_value=None), patch('autodiag.demo.Demo', return_value=manager), \
             patch('autodiag.live.inspect_topic', side_effect=report), redirect_stdout(out):
            code = cli.main(['demo', '--no-wait', '--json'])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])
        self.assertEqual({s['expected'] for s in result['scenarios']}, {s.expected for s in demo.SCENARIOS})

    def test_cli_demo_without_ros_is_a_usage_error(self):
        with patch('autodiag.demo.available', return_value='ROS 2 is not sourced'), redirect_stdout(StringIO()):
            self.assertEqual(cli.main(['demo', '--no-wait']), 2)


if __name__ == '__main__':
    unittest.main()
