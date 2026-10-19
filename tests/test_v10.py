import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from autodiag import __version__
from autodiag import enhanced
from autodiag.cli import main
from autodiag.redact import redact_snapshot
from autodiag.report import markdown_report
from autodiag.server import app
from autodiag.transport import health, transport_diagnose
from autodiag.validation import run_all, live_rule_check


def snap(host='a', **env):
    return {'identity': {'host': host, 'pid': 1}, 'environment': env, 'container': {'detected': False},
            'transport': {'requested_mode': 'auto'}, 'network': {'interfaces': [{'name': 'eth0', 'multicast': True,
                                                                                 'addresses': ['192.168.1.20']}]}}


def codes(a, b=None):
    return [i['code'] for i in transport_diagnose(a, b)]


class RuleTests(unittest.TestCase):
    def test_every_fixture_passes(self):
        result = run_all()
        self.assertTrue(result['ok'], [r for r in result['results'] if not r['passed']])
        self.assertGreaterEqual(result['total'], 14)

    def test_not_sourced(self):
        s = snap(); s['ros'] = {'cli_available': True}
        self.assertIn('ROS_ENV_NOT_SOURCED', codes(s))
        self.assertEqual(health(s, [])['checks']['ros2_cli'], 'not_sourced')
        s['environment']['ROS_DISTRO'] = 'jazzy'
        self.assertNotIn('ROS_ENV_NOT_SOURCED', codes(s))

    def test_valid_domain_is_quiet(self):
        self.assertEqual(codes(snap(ROS_DOMAIN_ID='42')), [])

    def test_rmw_default_vs_zenoh(self):
        self.assertIn('RMW_MISMATCH', codes(snap(), snap('b', RMW_IMPLEMENTATION='rmw_zenoh_cpp')))
        self.assertNotIn('RMW_MISMATCH', codes(snap(), snap('b', RMW_IMPLEMENTATION='rmw_fastrtps_cpp')))

    def test_live_rule_check_marks_fired_and_skipped(self):
        out = live_rule_check(snap(ROS_DOMAIN_ID='0'), snap('b', ROS_DOMAIN_ID='9', RMW_IMPLEMENTATION='rmw_zenoh_cpp'))
        by = {r['code']: r for r in out['rows']}
        self.assertEqual(by['DOMAIN_MISMATCH']['status'], 'fired')
        self.assertEqual(by['RMW_MISMATCH']['status'], 'fired')
        self.assertEqual(by['RELIABILITY_MISMATCH']['status'], 'skipped')
        self.assertGreaterEqual(len(out['rows']), 20)
        solo = live_rule_check(snap(ROS_DOMAIN_ID='0'))
        self.assertEqual(next(r for r in solo['rows'] if r['code'] == 'DOMAIN_MISMATCH')['status'], 'skipped')

    def test_cross_vendor_dds_is_warning(self):
        issues = transport_diagnose(snap(RMW_IMPLEMENTATION='rmw_cyclonedds_cpp'), snap('b', RMW_IMPLEMENTATION='rmw_fastrtps_cpp'))
        self.assertEqual([i['severity'] for i in issues if i['code'] == 'RMW_MISMATCH'], ['warning'])

    def test_discovery_range_same_host_ok(self):
        self.assertNotIn('DISCOVERY_RANGE_RESTRICTED', codes(snap(ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST'), snap()))


class RedactReportTests(unittest.TestCase):
    def test_redaction_hides_identity_and_keeps_signal(self):
        s = snap('robot-alpha', ROS_DOMAIN_ID='3', CYCLONEDDS_URI='file:///home/alice/cyclone.xml')
        s['ros'] = {'graph': {'stdout': 'node on robot-alpha 192.168.1.20 127.0.0.1'}}
        r = redact_snapshot(s, 'salt')
        text = json.dumps(r)
        for secret in ('robot-alpha', '192.168.1.20', '/home/alice'):
            self.assertNotIn(secret, text)
        self.assertIn('127.0.0.1', text)
        self.assertEqual(r['environment']['ROS_DOMAIN_ID'], '3')
        self.assertTrue(r['redacted'])
        self.assertEqual(s['identity']['host'], 'robot-alpha', 'input must not be modified')

    def test_same_salt_keeps_comparisons(self):
        a = redact_snapshot(snap('x'), 's'); b = redact_snapshot(snap('x'), 's')
        self.assertEqual(a['identity']['host'], b['identity']['host'])

    def test_markdown_report(self):
        a, b = snap(ROS_DOMAIN_ID='1'), snap('b', ROS_DOMAIN_ID='2')
        issues = transport_diagnose(a, b)
        text = markdown_report(a, b, issues, health(a, issues))
        self.assertIn('# DDS AutoDiag report', text)
        self.assertIn('DOMAIN_MISMATCH', text)
        self.assertIn('| Domain ID | 1 | 2 |', text)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_foreign_host_header(self):
        self.assertEqual(self.client.get('/api/healthz', headers={'Host': 'attacker.example'}).status_code, 400)

    def test_allowed_hosts(self):
        with patch.dict(os.environ, {'AUTODIAG_ALLOWED_HOSTS': 'robot.lan'}):
            self.assertEqual(self.client.get('/api/healthz', headers={'Host': 'robot.lan:8080'}).status_code, 200)

    def test_rejects_cross_origin_post(self):
        r = self.client.post('/api/compare', json={'host_a': {}}, headers={'Origin': 'http://evil.example'})
        self.assertEqual(r.status_code, 403)
        r = self.client.post('/api/compare', json={'host_a': {}}, headers={'Origin': 'http://testserver'})
        self.assertEqual(r.status_code, 200)

    def test_security_headers(self):
        r = self.client.get('/')
        self.assertIn("script-src 'self'", r.headers['content-security-policy'])
        self.assertNotIn('unsafe-inline', r.headers['content-security-policy'])
        self.assertEqual(r.headers['x-frame-options'], 'DENY')

    def test_ui_has_no_inline_script(self):
        html = self.client.get('/').text
        self.assertNotIn('onclick=', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('style="', html)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)

    def test_ui_fonts_ship_with_the_package(self):
        # The dashboard works offline: every font the stylesheet names is a local file, served same-origin.
        css = self.client.get('/static/app.css').text
        fonts = re.findall(r'url\("(fonts/[^"]+)"\)', css)
        self.assertGreaterEqual(len(fonts), 6)
        for font in fonts:
            r = self.client.get('/static/' + font)
            self.assertEqual(r.status_code, 200, font)
            self.assertEqual(r.content[:4], b'wOF2', font)
        self.assertNotIn('fonts.googleapis', css)
        self.assertEqual(self.client.get('/static/fonts/OFL.txt').status_code, 200)

    def test_token_auth(self):
        with patch.dict(os.environ, {'AUTODIAG_UI_TOKEN': 'secret-token'}):
            self.assertEqual(self.client.get('/api/version').status_code, 401)
            self.assertEqual(self.client.get('/api/healthz').status_code, 200)
            self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/login')
            ok = self.client.get('/api/version', headers={'Authorization': 'Bearer secret-token'})
            self.assertEqual(ok.status_code, 200)
            self.assertNotIn('secret-token', ok.text)
            self.assertEqual(self.client.post('/login', data={'token': 'nope'}).status_code, 401)
            c = TestClient(app)
            r = c.post('/login', data={'token': 'secret-token'}, follow_redirects=False)
            self.assertEqual(r.status_code, 303)
            self.assertEqual(c.get('/api/version').status_code, 200)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_version_and_health(self):
        self.assertEqual(self.client.get('/api/healthz').json()['version'], __version__)
        self.assertEqual(self.client.get('/api/version').json()['version'], __version__)

    def test_selftest(self):
        self.assertTrue(self.client.get('/api/selftest').json()['ok'])

    def test_live_rules(self):
        with patch('autodiag.server.build_graph', return_value={'state': 'ok', 'edges': []}):
            r = self.client.post('/api/live-rules', json={
                'host_a': snap(ROS_DOMAIN_ID='0'),
                'host_b': snap('zenoh', ROS_DOMAIN_ID='0', RMW_IMPLEMENTATION='rmw_zenoh_cpp'),
            }).json()
        self.assertGreaterEqual(r['fired'], 1)
        row = next(x for x in r['rows'] if x['code'] == 'RMW_MISMATCH')
        self.assertEqual(row['status'], 'fired')
        qos = next(x for x in r['rows'] if x['code'] == 'RELIABILITY_MISMATCH')
        self.assertEqual(qos['status'], 'not_seen')

    def test_report_download(self):
        r = self.client.post('/api/report', json={'host_a': snap(ROS_DOMAIN_ID='1'), 'host_b': snap('b', ROS_DOMAIN_ID='2')})
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/markdown', r.headers['content-type'])
        self.assertIn('DOMAIN_MISMATCH', r.text)

    def test_compare_sorted_with_summaries(self):
        r = self.client.post('/api/compare', json={'host_a': snap(ROS_DOMAIN_ID='1', ROS_DISTRO='jazzy'),
                                                   'host_b': snap('b', ROS_DOMAIN_ID='2', ROS_DISTRO='humble')}).json()
        self.assertEqual(r['issues'][0]['severity'], 'error')
        self.assertEqual(r['summary_b']['domain_id'], '2')

    def test_redact_pair(self):
        r = self.client.post('/api/snapshot/redact', json={'host_a': snap('alpha'), 'host_b': snap('alpha')}).json()
        self.assertEqual(r['host_a']['identity']['host'], r['host_b']['identity']['host'])
        self.assertNotIn('alpha', json.dumps(r))

    def test_remote_validation_message(self):
        r = self.client.post('/api/remote-compare', json={'url': 'http://8.8.8.8:8080', 'token': 'x', 'host_a': snap()})
        self.assertEqual(r.status_code, 400)
        self.assertIn('private', r.json()['detail'])

    def test_remote_connection_refused(self):
        r = self.client.post('/api/remote-compare', json={'url': 'http://127.0.0.1:9', 'token': 'x', 'host_a': snap()})
        self.assertEqual(r.status_code, 502)
        self.assertIn('Connection refused', r.json()['detail'])

    def test_endpoint_check_python_fallback(self):
        with patch('autodiag.server.check_endpoint', return_value={'state': 'unavailable'}):
            r = self.client.post('/api/endpoint-check', json={
                'publisher': {'domain': '0', 'reliability': 'best_effort', 'durability': 'volatile'},
                'subscriber': {'domain': '0', 'reliability': 'reliable', 'durability': 'volatile'}}).json()
        self.assertIn('Python', r['engine'])
        self.assertEqual([f['code'] for f in r['findings']], ['RELIABILITY_MISMATCH'])

    def test_legacy_diagnose_validation(self):
        self.assertEqual(self.client.post('/api/diagnose', json={}).status_code, 422)


class ProbeTests(unittest.TestCase):
    def test_rmw_detection_is_cached(self):
        enhanced._RMW_CACHE['key'] = None
        with patch('autodiag.enhanced.shutil.which', return_value='/usr/bin/ros2'), \
             patch('autodiag.enhanced.run', return_value={'state': 'ok', 'stdout': 'middleware name : rmw_cyclonedds_cpp'}) as run:
            self.assertEqual(enhanced.detect_rmw()['effective'], 'rmw_cyclonedds_cpp')
            enhanced.detect_rmw()
        self.assertEqual(run.call_count, 1)
        self.assertGreater(run.call_args.kwargs.get('max_output', 0), 16000, 'doctor report must not be truncated')
        enhanced._RMW_CACHE['key'] = None

    def test_graph_queries_wait_for_discovery(self):
        from autodiag import live
        with patch('autodiag.live._call', return_value={'state': 'ok', 'stdout': '/chatter [std_msgs/msg/String]'}) as call:
            topics = live.topic_list()
        self.assertIn('--spin-time', call.call_args.args[0])
        self.assertEqual(topics['topics'], [{'topic': '/chatter', 'type': 'std_msgs/msg/String'}])


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_selftest(self):
        code, out, _ = self.run_cli('selftest')
        self.assertEqual(code, 0)
        self.assertIn('fixtures passed', out)

    def test_check_saved_snapshots_exit_code_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, report = Path(tmp, 'a.json'), Path(tmp, 'b.json'), Path(tmp, 'r.md')
            a.write_text(json.dumps(snap(ROS_DOMAIN_ID='1')))
            b.write_text(json.dumps(snap('b', ROS_DOMAIN_ID='2')))
            code, out, _ = self.run_cli('check', '--snapshot', str(a), '--peer', str(b), '--report', str(report))
            self.assertEqual(code, 1)
            self.assertIn('DOMAIN_MISMATCH', out)
            self.assertIn('DOMAIN_MISMATCH', report.read_text())
            code, out, _ = self.run_cli('compare', str(a), str(a), '--json')
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)['issues'], [])

    def test_bad_snapshot_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, 'bad.json'); bad.write_text('{not json')
            with self.assertRaises(SystemExit) as ctx, redirect_stderr(io.StringIO()):
                main(['check', '--snapshot', str(bad)])
            self.assertEqual(ctx.exception.code, 2)

    def test_serve_refuses_public_bind_without_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AUTODIAG_UI_TOKEN', None)
            code, _, err = self.run_cli('serve', '--host', '0.0.0.0')
        self.assertEqual(code, 2)
        self.assertIn('Refusing', err)

    def test_collect_redacted_to_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('autodiag.collector.collect', return_value=snap('secret-host')):
            out = Path(tmp, 's.json')
            code, _, _ = self.run_cli('collect', '--redact', '-o', str(out))
            self.assertEqual(code, 0)
            self.assertNotIn('secret-host', out.read_text())


if __name__ == '__main__':
    unittest.main()
