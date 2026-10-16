"""Guards for claims the documentation makes: rule coverage, the generated rules page, and cloud privacy."""
import json
import re
import socket
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from autodiag import cli, rules_doc, validation
from autodiag.redact import mask_for_cloud
from autodiag.server import app

ROOT = Path(__file__).resolve().parent.parent
SECRET_NODE = 'acme_secret_gripper_controller'


def rule_codes_in_source() -> set:
    codes = set(re.findall(r"_issue\('([A-Z_]+)'", (ROOT / 'autodiag/transport.py').read_text()))
    live = (ROOT / 'autodiag/live.py').read_text()
    codes |= set(re.findall(r"'code':'([A-Z_]+)'", live))
    codes |= {p.upper() + '_MISMATCH' for p in re.findall(r"\('(reliability|durability)','", live)}
    return codes


class RuleCoverageTests(unittest.TestCase):
    def test_every_rule_has_a_passing_fixture(self):
        expected = {case['expected'] for case in validation.FIXTURES.values() if case['expected']}
        self.assertEqual(expected, rule_codes_in_source())
        result = validation.run_all()
        self.assertTrue(result['ok'], [r['fixture'] for r in result['results'] if not r['passed']])

    def test_rules_page_lists_every_rule(self):
        self.assertEqual({code for code, *_ in rules_doc.RULES}, rule_codes_in_source())

    def test_rules_page_is_up_to_date(self):
        page = (ROOT / 'docs/reference/rules.md').read_text()
        self.assertEqual(page, rules_doc.render(), 'Run: python -m autodiag.rules_doc > docs/reference/rules.md')

    def test_rule_documentation_links_have_readable_titles(self):
        for code, _, _, fixtures in rules_doc.RULES:
            for name in fixtures:
                for doc in rules_doc.finding(name, code)['documentation']:
                    self.assertRegex(doc['label'], r'[A-Z ]', f'{code}: raw key {doc["label"]!r}')


class CloudPrivacyTests(unittest.TestCase):
    report = {'state': 'ok', 'publisher_count': 1, 'subscriber_count': 1,
              'endpoints': [{'kind': 'publisher', 'node': SECRET_NODE, 'type': 'sensor_msgs/msg/LaserScan',
                             'qos': {'reliability': 'BEST_EFFORT', 'durability': 'VOLATILE'}},
                            {'kind': 'subscriber', 'node': 'rviz', 'type': 'sensor_msgs/msg/LaserScan',
                             'qos': {'reliability': 'RELIABLE', 'durability': 'VOLATILE'}}],
              'findings': [{'code': 'RELIABILITY_MISMATCH', 'severity': 'error',
                            'summary': f'Incompatible reliability: {SECRET_NODE} → rviz',
                            'evidence': {'publisher': SECRET_NODE, 'subscriber': 'rviz'}}]}

    def ask(self, provider):
        sent = {}

        def fake_events(provider, findings, question, sources, model=None, history=None):
            sent['findings'] = findings
            yield {'type': 'done', 'seconds': 0}

        host = {'identity': {'host': socket.gethostname()}, 'environment': {'CYCLONEDDS_URI': 'file:///home/alice/c.xml'},
                'network': {'interfaces': [{'name': 'eth0', 'addresses': ['192.168.7.42']}]}}
        with patch('autodiag.server.inspect_topic', return_value=self.report), \
             patch('autodiag.server.llm.explain_events', side_effect=fake_events):
            r = TestClient(app).post('/api/assistant/stream', json={
                'question': 'why?', 'provider': provider, 'topic': '/scan', 'host_a': host})
        self.assertEqual(r.status_code, 200)
        context = json.loads(r.text.splitlines()[0])
        return json.dumps(sent['findings']), json.dumps(context)

    def test_cloud_provider_never_receives_node_names(self):
        model_text, ui_text = self.ask('anthropic')
        self.assertNotIn(SECRET_NODE, model_text)
        self.assertNotIn('"rviz', model_text)
        self.assertIn('publisher 1', model_text)
        self.assertIn('RELIABILITY_MISMATCH', model_text)
        self.assertIn('BEST_EFFORT', model_text)
        self.assertIn(SECRET_NODE, ui_text)  # the user still sees the real names

    def test_local_model_keeps_real_names(self):
        model_text, _ = self.ask('ollama')
        self.assertIn(SECRET_NODE, model_text)

    def test_mask_removes_host_ip_and_home_paths(self):
        text = mask_for_cloud(f'{socket.gethostname()} at 10.1.2.3 reads /home/alice/robot.xml')
        for leak in ('10.1.2.3', '/home/alice', 'alice'):
            self.assertNotIn(leak, text)
        if len(socket.gethostname()) >= 3:
            self.assertNotIn(socket.gethostname(), text)

    def test_rviz_plan_prompt_is_masked_for_cloud(self):
        from autodiag import rviz_agent
        seen = {}

        def fake_json(provider, system, prompt, schema, model=None):
            seen['prompt'] = prompt
            return {'summary': '', 'actions': [], 'notes': []}

        state = {'displays': [], 'frames': [], 'fixed_frame': 'map'}
        request = f'show the cloud from {socket.gethostname()} 10.9.8.7'
        with patch.object(rviz_agent, '_live_topics', return_value={}), \
             patch.object(rviz_agent.llm, 'complete_json', side_effect=fake_json):
            rviz_agent.plan(request, state, provider='openai')
        self.assertNotIn('10.9.8.7', seen['prompt'])


class CliAccuracyTests(unittest.TestCase):
    def test_redaction_is_salted_by_default(self):
        snapshot = {'identity': {'host': 'robot-one'}, 'environment': {}, 'transport': {},
                    'network': {'interfaces': [{'addresses': ['192.168.1.20']}]}}
        outs = []
        for _ in range(2):
            out, err = StringIO(), StringIO()
            with patch('autodiag.collector.collect', return_value=json.loads(json.dumps(snapshot))), \
                 redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(cli.main(['collect', '--redact']), 0)
            self.assertIn('--salt', err.getvalue())
            outs.append(json.loads(out.getvalue())['identity']['host'])
        self.assertNotEqual(outs[0], outs[1])

    def test_doctor_hint_suggests_the_fast_model(self):
        self.assertNotIn("'qwen3:4b')", (ROOT / 'autodiag/cli.py').read_text())


if __name__ == '__main__':
    unittest.main()
