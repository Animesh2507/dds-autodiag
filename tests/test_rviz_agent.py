import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from autodiag import llm, rviz_agent
from autodiag.server import app

# Claude tests need the optional Anthropic SDK (pip install ".[cloud]").
needs_anthropic = unittest.skipUnless(importlib.util.find_spec('anthropic'), 'anthropic SDK not installed')

TOPICS = {'/lidar/points': 'sensor_msgs/msg/PointCloud2', '/scan': 'sensor_msgs/msg/LaserScan',
          '/map': 'nav_msgs/msg/OccupancyGrid'}
STATE = {'fixed_frame': 'map', 'frames': ['map', 'odom', 'base_link'],
         'displays': [{'name': 'Grid', 'type': 'rviz_default_plugins/Grid', 'enabled': True, 'status': 'Ok',
                       'topic': '', 'properties': {'Cell Size': '1'}},
                      {'name': 'LaserScan', 'type': 'rviz_default_plugins/LaserScan', 'enabled': True,
                       'status': 'Error', 'topic': '/scan',
                       'properties': {'Style': 'Flat Squares', 'Topic/Reliability Policy': 'Reliable'}}]}


def act(action, **fields):
    base = {'action': action, 'display': '', 'display_type': '', 'topic': '', 'property': '', 'value': '', 'frame': ''}
    return {**base, **fields}


class ValidateTests(unittest.TestCase):
    def check(self, *actions):
        return rviz_agent.validate({'summary': 's', 'actions': list(actions), 'notes': []}, STATE, TOPICS)

    def test_add_display_resolves_type_and_class(self):
        r = self.check(act('add_display', display='Cloud', display_type='pointcloud2', topic='/lidar/points'))
        a = r['actions'][0]
        self.assertEqual(a['class_id'], 'rviz_default_plugins/PointCloud2')
        self.assertEqual(a['topic_property'], 'Topic')

    def test_rejects_type_mismatch_unknown_type_and_action(self):
        r = self.check(act('add_display', display_type='Map', topic='/scan'),
                       act('add_display', display_type='Teapot', topic='/scan'),
                       act('format_disk'))
        self.assertEqual(r['actions'], [])
        reasons = ' '.join(x['reason'] for x in r['rejected'])
        self.assertIn('LaserScan', reasons)
        self.assertIn('Unknown display type', reasons)
        self.assertIn('Unknown action', reasons)

    def test_unknown_display_rejected_but_loose_names_match(self):
        r = self.check(act('set_enabled', display='Nope', value='false'),
                       act('set_property', display='laser_scan', property='Topic/Reliability Policy', value='Best Effort'))
        self.assertEqual(len(r['rejected']), 1)
        self.assertEqual(r['actions'][0]['display'], 'LaserScan')

    def test_property_checked_against_display(self):
        r = self.check(act('set_property', display='LaserScan', property='Warp Drive', value='9'),
                       act('set_property', display='LaserScan', property='Decay Time', value='0'))
        self.assertEqual([a['property'] for a in r['actions']], ['Decay Time'])  # known from the catalog

    def test_actions_on_display_added_in_same_plan(self):
        r = self.check(act('add_display', display='Cloud', display_type='PointCloud2', topic='/lidar/points'),
                       act('set_property', display='cloud', property='Style', value='Points'))
        self.assertEqual(r['actions'][1]['display'], 'Cloud')
        self.assertEqual(r['actions'][1]['display_type'], 'PointCloud2')

    def test_topicless_display_and_duplicate_name(self):
        r = self.check(act('add_display', display='Grid', display_type='Grid'))
        self.assertEqual(r['actions'][0]['display'], 'Grid (2)')
        self.assertEqual(r['actions'][0]['topic_property'], '')

    def test_displays_can_be_added_before_data_exists(self):
        r = rviz_agent.validate({'actions': [act('add_display', display_type='LaserScan'),
                                             act('add_display', display_type='Image', topic='front_camera/image'),
                                             act('add_display', display_type='PointCloud2')]}, STATE, {})
        self.assertEqual(r['rejected'], [])
        self.assertEqual([a['topic'] for a in r['actions']], ['/scan', '/front_camera/image', '/points'])
        self.assertTrue(all(a['not_publishing'] for a in r['actions']))
        self.assertIn('(not publishing yet)', r['actions'][0]['description'])
        self.assertTrue(any('not publishing yet' in n for n in r['notes']))

    def test_empty_topic_uses_the_single_live_topic_of_that_type(self):
        r = rviz_agent.validate({'actions': [act('add_display', display_type='PointCloud2')]}, STATE, TOPICS)
        self.assertEqual(r['actions'][0]['topic'], '/lidar/points')
        self.assertFalse(r['actions'][0]['not_publishing'])

    def test_nested_property_path_normalized(self):
        r = rviz_agent.validate({'actions': [act('add_display', display='Cloud', display_type='PointCloud2', topic='/lidar/points'),
                                             act('set_property', display='Cloud', property='Color Transformer/Axis', value='Z')]},
                                STATE, TOPICS)
        self.assertEqual(r['actions'][1]['property'], 'Axis')

    def test_enabled_normalized(self):
        r = self.check(act('set_enabled', display='Grid', value='Disable'))
        self.assertEqual(r['actions'][0]['value'], 'false')


class CompleteTests(unittest.TestCase):
    def test_color_transformer_added_before_axis(self):
        r = rviz_agent.validate({'actions': [act('add_display', display='Cloud', display_type='PointCloud2', topic='/lidar/points'),
                                             act('set_property', display='Cloud', property='Axis', value='Z')]}, STATE, TOPICS)
        rviz_agent._complete(r, {})
        self.assertEqual([(a['property'], a['value']) for a in r['actions'][1:]],
                         [('Color Transformer', 'AxisColor'), ('Axis', 'Z')])

    def test_qos_fix_added_and_disable_unchecked(self):
        r = rviz_agent.validate({'actions': [act('set_enabled', display='LaserScan', value='false')]}, STATE, TOPICS)
        qos = {'LaserScan': {'fact': 'x', 'fix': [('Topic/Reliability Policy', 'Best Effort')]}}
        rviz_agent._complete(r, qos)
        fix = [a for a in r['actions'] if a.get('auto')]
        self.assertEqual(fix[0]['value'], 'Best Effort')
        self.assertTrue(r['actions'][0]['unchecked'])

    def test_fixed_frame_from_request_and_dedupe(self):
        r = rviz_agent.validate({'actions': [act('set_property', display='LaserScan', property='Style', value='Points'),
                                             act('set_property', display='LaserScan', property='Style', value='Boxes')]},
                                STATE, TOPICS)
        rviz_agent._complete(r, {}, 'show it in the base_link frame', STATE)
        self.assertEqual([a['value'] for a in r['actions'] if a['action'] == 'set_property'], ['Points'])
        self.assertEqual(r['actions'][-1]['frame'], 'base_link')


class QosDiagnosisTests(unittest.TestCase):
    def test_best_effort_publisher_vs_reliable_display(self):
        report = {'state': 'ok', 'endpoints': [{'kind': 'publisher', 'node': 'lidar',
                                                'qos': {'reliability': 'BEST_EFFORT', 'durability': 'VOLATILE'}}]}
        with patch('autodiag.live.inspect_topic', return_value=report):
            out = rviz_agent._topic_qos(STATE)
        self.assertEqual(out['LaserScan']['fix'], [('Topic/Reliability Policy', 'Best Effort')])

    def test_latched_map_vs_volatile_display(self):
        state = {'displays': [{'name': 'Map', 'type': 'rviz_default_plugins/Map', 'topic': '/map',
                               'properties': {'Topic/Durability Policy': 'Volatile'}}]}
        report = {'state': 'ok', 'endpoints': [{'kind': 'publisher', 'node': 'map_server',
                                                'qos': {'reliability': 'RELIABLE', 'durability': 'TRANSIENT_LOCAL'}}]}
        with patch('autodiag.live.inspect_topic', return_value=report):
            out = rviz_agent._topic_qos(state)
        self.assertEqual(out['Map']['fix'], [('Topic/Durability Policy', 'Transient Local')])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_plan_endpoint(self):
        raw = {'summary': 'Show the cloud', 'notes': [],
               'actions': [act('add_display', display='Cloud', display_type='PointCloud2', topic='/lidar/points')]}
        with patch('autodiag.rviz_agent._live_topics', return_value=TOPICS), \
             patch('autodiag.rviz_agent._topic_qos', return_value={}), \
             patch('autodiag.llm.complete_json', return_value=raw) as complete:
            r = self.client.post('/api/rviz/plan', json={'request': 'show lidar', **STATE, 'provider': 'ollama'})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body['actions'][0]['description'], 'Add PointCloud2 display "Cloud" on /lidar/points')
        prompt = complete.call_args.args[2]
        self.assertIn('/lidar/points [PointCloud2]', prompt)
        self.assertIn('"LaserScan" (LaserScan)', prompt)
        self.assertNotIn('Wrench', prompt)  # only relevant display types are listed
        self.assertIn('- Image:', prompt)    # common types are always offered

    def test_empty_request_rejected(self):
        self.assertEqual(self.client.post('/api/rviz/plan', json={'request': ' '}).status_code, 400)

    def test_catalog(self):
        self.assertIn('PointCloud2', self.client.get('/api/rviz/catalog').json()['displays'])


class CompleteJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AUTODIAG_CONFIG_DIR': self.tmp.name})
        self.env.start()
        os.environ.pop('ANTHROPIC_API_KEY', None)
        self.thinking = patch('autodiag.llm.thinking_only', return_value=False)
        self.thinking.start()

    def tearDown(self):
        self.thinking.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_ollama_uses_schema_format(self):
        with patch('autodiag.llm._post_json', return_value={'message': {'content': '{"summary":"x","actions":[],"notes":[]}'}}) as post:
            out = llm.complete_json('ollama', 'sys', 'prompt', rviz_agent.PLAN_SCHEMA, 'qwen3:4b-instruct')
        self.assertEqual(out['summary'], 'x')
        self.assertEqual(post.call_args.args[1]['format'], rviz_agent.PLAN_SCHEMA)
        self.assertIs(post.call_args.args[1]['think'], False)

    @needs_anthropic
    def test_claude_structured_output_with_fallbacks(self):
        llm.update_provider('anthropic', api_key='sk-ant-test-0000000000000000')
        response = MagicMock(stop_reason='end_turn', content=[MagicMock(type='text', text='{"summary":"ok","actions":[],"notes":[]}')])
        client = MagicMock()
        client.beta.messages.create.return_value = response
        with patch('anthropic.Anthropic', return_value=client):
            out = llm.complete_json('anthropic', 'sys', 'prompt', rviz_agent.PLAN_SCHEMA)
        self.assertEqual(out['summary'], 'ok')
        kwargs = client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs['output_config']['format'], {'type': 'json_schema', 'schema': rviz_agent.PLAN_SCHEMA})
        self.assertEqual(kwargs['fallbacks'], 'default')
        self.assertEqual(kwargs['model'], 'claude-opus-5-5')

    def test_tolerant_json_parsing(self):
        self.assertEqual(llm._first_json_object('Sure! ```json\n{"a": {"b": 1}}\n``` done')['a'], {'b': 1})
        with self.assertRaises(llm.ProviderError):
            llm._first_json_object('no json here')


if __name__ == '__main__':
    unittest.main()


class HistoryTests(unittest.TestCase):
    def test_history_text_reports_outcomes(self):
        text = rviz_agent._history_text([{'request': 'add a cloud', 'summary': 'Added PointCloud2',
                                          'actions': [{'description': 'Add PointCloud2 display', 'result': 'applied'},
                                                      {'description': 'Set Size', 'result': 'skipped by the user'}],
                                          'undone': True}])
        self.assertIn('User asked: add a cloud', text)
        self.assertIn('applied: Add PointCloud2 display', text)
        self.assertIn('skipped by the user: Set Size', text)
        self.assertIn('Undo', text)

    def test_plan_prompt_includes_conversation(self):
        with patch('autodiag.rviz_agent._live_topics', return_value=TOPICS), \
             patch('autodiag.rviz_agent._topic_qos', return_value={}), \
             patch('autodiag.llm.complete_json', return_value={'summary': '', 'actions': [], 'notes': []}) as complete:
            rviz_agent.plan('make it bigger', STATE, 'ollama', history=[{'request': 'add a cloud', 'actions': []}])
        prompt = complete.call_args.args[2]
        self.assertIn('EARLIER IN THIS CONVERSATION', prompt)
        self.assertIn('add a cloud', prompt)
        self.assertTrue(prompt.rstrip().endswith('REQUEST: make it bigger'))
