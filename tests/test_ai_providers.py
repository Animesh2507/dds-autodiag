import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from fastapi.testclient import TestClient
from autodiag import llm, rag
from autodiag.server import app

KEY = 'sk-test-abcdefghijklmnop1234'


class _TempConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {'AUTODIAG_CONFIG_DIR': self.tmp.name}
        self.env = patch.dict(os.environ, env)
        self.env.start()
        for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'AUTODIAG_COMPAT_API_KEY',
                     'AUTODIAG_OLLAMA_MODEL'):
            os.environ.pop(name, None)
        # Keep tests independent of whatever Ollama models this machine has.
        self.stubs = [patch('autodiag.llm.installed_ollama_models', return_value=[]),
                      patch('autodiag.llm.thinking_only', return_value=False)]
        for stub in self.stubs:
            stub.start()
        llm._cache.clear()
        self.client = TestClient(app)

    def tearDown(self):
        for stub in self.stubs:
            stub.stop()
        self.env.stop()
        self.tmp.cleanup()


class KeyStorageTests(_TempConfig):
    def test_key_saved_privately_and_never_returned(self):
        r = self.client.put('/api/ai/providers/openai', json={'api_key': KEY, 'model': 'gpt-5-mini'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(KEY, r.text)
        self.assertEqual(r.json()['key_hint'], '…1234')
        self.assertTrue(r.json()['ready'])
        listing = self.client.get('/api/ai/providers')
        self.assertNotIn(KEY, listing.text)
        mode = stat.S_IMODE(os.stat(llm.config_path()).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertIn(KEY, llm.config_path().read_text())

    def test_empty_key_keeps_existing_and_remove_deletes(self):
        llm.update_provider('gemini', api_key=KEY)
        llm.update_provider('gemini', model='gemini-2.5-flash')
        self.assertTrue(llm.provider_status('gemini')['key_configured'])
        r = self.client.delete('/api/ai/providers/gemini/key')
        self.assertFalse(r.json()['key_configured'])

    def test_env_var_takes_precedence(self):
        llm.update_provider('openai', api_key=KEY)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-from-env-zzzzzzzz9999'}):
            status = llm.provider_status('openai')
        self.assertEqual(status['key_source'], 'env:OPENAI_API_KEY')
        self.assertEqual(status['key_hint'], '…9999')

    def test_validation(self):
        self.assertEqual(self.client.put('/api/ai/providers/openai', json={'model': 'bad model; rm'}).status_code, 400)
        self.assertEqual(self.client.put('/api/ai/providers/openai', json={'api_key': 'has space'}).status_code, 400)
        self.assertEqual(self.client.put('/api/ai/providers/nope', json={}).status_code, 400)
        self.assertEqual(self.client.put('/api/ai/providers/openai_compatible',
                                         json={'base_url': 'http://example.com/v1'}).status_code, 400)
        ok = self.client.put('/api/ai/providers/openai_compatible', json={'base_url': 'https://api.groq.com/openai/v1/'})
        self.assertEqual(ok.json()['base_url'], 'https://api.groq.com/openai/v1')

    def test_default_falls_back_to_ollama_when_not_ready(self):
        llm.update_provider('anthropic', make_default=True)  # no key linked
        self.assertEqual(llm.default_provider(), 'ollama')
        llm.update_provider('anthropic', api_key=KEY)
        self.assertEqual(llm.default_provider(), 'anthropic')

    def test_missing_key_is_clear_error(self):
        events = list(llm.explain_events('openai', [], 'why', []))
        self.assertEqual(events[-1]['type'], 'error')
        self.assertIn('No API key', events[-1]['message'])


def _lines(*items):
    return iter([(json.dumps(i) if not isinstance(i, str) else i).encode() + b'\n' for i in items])


class OllamaTests(_TempConfig):
    def test_fast_request_and_think_filter(self):
        captured = {}

        def fake(url, body, headers, timeout):
            captured.update(body)
            return _lines({'message': {'content': '<think>secret'}}, {'message': {'content': ' plan</think>Check '}},
                          {'message': {'content': 'ROS_DOMAIN_ID'}}, {'done': True})
        with patch('autodiag.llm._post_stream', side_effect=fake):
            text = ''.join(llm.stream_answer('ollama', 'q'))
        self.assertEqual(text, 'Check ROS_DOMAIN_ID')
        self.assertIs(captured['think'], False)
        self.assertTrue(captured['stream'])
        self.assertEqual(captured['keep_alive'], '30m')
        self.assertLessEqual(captured['options']['num_predict'], 600)

    def test_thinking_model_reasons_in_hidden_channel(self):
        captured = {}

        def fake(url, body, headers, timeout):
            captured.update(body)
            return _lines({'message': {'thinking': 'x' * 200}}, {'message': {'thinking': 'y' * 200}},
                          {'message': {'content': 'Align domains'}}, {'done': True})
        with patch('autodiag.llm.thinking_only', return_value=True), patch('autodiag.llm._post_stream', side_effect=fake):
            events = list(llm.explain_events('ollama', [], 'q', []))
        self.assertIs(captured['think'], True)
        self.assertGreater(captured['options']['num_predict'], 1000)
        types = [e['type'] for e in events]
        self.assertIn('thinking', types)
        self.assertEqual(''.join(e['text'] for e in events if e['type'] == 'token'), 'Align domains')

    def test_prefers_instruct_model_when_installed(self):
        with patch('autodiag.llm.installed_ollama_models', return_value=['qwen3:4b', 'qwen3:4b-instruct']):
            self.assertEqual(llm.model_for('ollama'), 'qwen3:4b-instruct')
        with patch('autodiag.llm.installed_ollama_models', return_value=['qwen3:4b']):
            self.assertEqual(llm.model_for('ollama'), 'qwen3:4b')
        llm.update_provider('ollama', model='llama3.2:3b')
        self.assertEqual(llm.model_for('ollama'), 'llama3.2:3b')

    def test_retries_without_think_for_models_without_thinking(self):
        calls = []

        def fake(url, body, headers, timeout):
            calls.append(dict(body))
            if 'think' in body:
                raise HTTPError(url, 400, 'bad', {}, io.BytesIO(b'{"error":"model does not support thinking"}'))
            return _lines({'message': {'content': 'ok'}}, {'done': True})
        with patch('autodiag.llm._post_stream', side_effect=fake):
            self.assertEqual(''.join(llm.stream_answer('ollama', 'q', model='qwen2.5:3b')), 'ok')
        self.assertEqual(len(calls), 2)
        self.assertNotIn('think', calls[1])

    def test_missing_model_message(self):
        def fake(url, body, headers, timeout):
            raise HTTPError(url, 404, 'nf', {}, io.BytesIO(b'{"error":"model \\"x\\" not found"}'))
        with patch('autodiag.llm._post_stream', side_effect=fake):
            with self.assertRaises(llm.ProviderError) as ctx:
                list(llm.stream_answer('ollama', 'q', model='x'))
        self.assertIn('ollama pull x', str(ctx.exception))

    def test_think_filter_split_tags(self):
        f = llm._ThinkFilter()
        out = ''.join(f.feed(c) for c in ['Hi <th', 'ink>hidden</th', 'ink> there'])
        self.assertEqual(out, 'Hi  there')

    def test_legacy_rag_path_disables_thinking(self):
        with patch('autodiag.rag._ollama_post', return_value={'message': {'content': '<think>x</think>Answer'}}) as post:
            result = rag.answer([], 'q', use_ai=True)
        self.assertIs(post.call_args.args[1]['think'], False)
        self.assertEqual(result['ai']['text'], 'Answer')


class CloudProviderTests(_TempConfig):
    def test_openai_stream(self):
        llm.update_provider('openai', api_key=KEY)
        seen = {}

        def fake(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            return iter([b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n', b'\n',
                         b'data: {"choices":[{"delta":{"content":"lo"}}]}\n', b'data: [DONE]\n'])
        with patch('autodiag.llm._post_stream', side_effect=fake):
            self.assertEqual(''.join(llm.stream_answer('openai', 'q')), 'Hello')
        self.assertEqual(seen['url'], 'https://api.openai.com/v1/chat/completions')
        self.assertEqual(seen['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertEqual(seen['body']['reasoning_effort'], 'minimal')

    def test_gemini_stream(self):
        llm.update_provider('gemini', api_key=KEY)
        seen = {}

        def fake(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            return iter([b'data: {"candidates":[{"content":{"parts":[{"text":"A"},{"text":"x","thought":true}]}}]}\n',
                         b'data: {"candidates":[{"content":{"parts":[{"text":"B"}]}}]}\n'])
        with patch('autodiag.llm._post_stream', side_effect=fake):
            self.assertEqual(''.join(llm.stream_answer('gemini', 'q')), 'AB')
        self.assertIn('gemini-2.5-flash:streamGenerateContent', seen['url'])
        self.assertEqual(seen['headers']['x-goog-api-key'], KEY)
        self.assertEqual(seen['body']['generationConfig']['thinkingConfig']['thinkingBudget'], 0)

    def test_http_error_is_friendly_and_keyless(self):
        llm.update_provider('openai', api_key=KEY)

        def fake(url, body, headers, timeout):
            raise HTTPError(url, 401, 'unauth', {}, io.BytesIO(b'{"error":{"message":"Incorrect API key provided"}}'))
        with patch('autodiag.llm._post_stream', side_effect=fake):
            events = list(llm.explain_events('openai', [], 'q', []))
        self.assertIn('rejected', events[-1]['message'])
        self.assertNotIn(KEY, json.dumps(events))

    def _fake_anthropic(self, stop_reason='end_turn'):
        stream = MagicMock()
        stream.text_stream = iter(['Likely ', 'cause'])
        stream.get_final_message.return_value = MagicMock(stop_reason=stop_reason)

        @contextmanager
        def manager(**kwargs):
            self.anthropic_kwargs = kwargs
            yield stream
        client = MagicMock()
        client.messages.stream.side_effect = manager
        client.beta.messages.stream.side_effect = manager
        return client

    def test_claude_opus_uses_fallbacks_and_low_effort(self):
        llm.update_provider('anthropic', api_key=KEY)
        client = self._fake_anthropic()
        with patch('anthropic.Anthropic', return_value=client) as ctor:
            text = ''.join(llm.stream_answer('anthropic', 'q'))
        self.assertEqual(text, 'Likely cause')
        self.assertEqual(ctor.call_args.kwargs['api_key'], KEY)
        self.assertEqual(self.anthropic_kwargs['model'], 'claude-opus-5-5')
        self.assertEqual(self.anthropic_kwargs['fallbacks'], 'default')
        self.assertEqual(self.anthropic_kwargs['betas'], ['server-side-fallback-2026-07-01'])
        self.assertEqual(self.anthropic_kwargs['output_config'], {'effort': 'low'})
        self.assertNotIn('thinking', self.anthropic_kwargs)

    def test_claude_client_avoids_brotli(self):
        llm.update_provider('anthropic', api_key=KEY)
        client = self._fake_anthropic()
        with patch('anthropic.Anthropic', return_value=client) as ctor:
            ''.join(llm.stream_answer('anthropic', 'q'))
        self.assertEqual(ctor.call_args.kwargs['default_headers'], {'Accept-Encoding': 'gzip, deflate'})

    def test_claude_connection_errors_are_specific(self):
        import anthropic
        request = MagicMock()
        timeout = anthropic.APITimeoutError(request=request)
        self.assertIn('timed out', str(llm._anthropic_connection_error(anthropic, timeout)))
        local = anthropic.APIConnectionError(request=request)
        local.__cause__ = TypeError('process() takes no keyword arguments')
        self.assertIn('TypeError', str(llm._anthropic_connection_error(anthropic, local)))
        network = anthropic.APIConnectionError(request=request)
        network.__cause__ = ConnectionRefusedError()
        self.assertIn('cannot reach', str(llm._anthropic_connection_error(anthropic, network)))

    def test_claude_haiku_has_no_fallbacks(self):
        llm.update_provider('anthropic', api_key=KEY, model='claude-haiku-5-5')
        client = self._fake_anthropic()
        with patch('anthropic.Anthropic', return_value=client):
            ''.join(llm.stream_answer('anthropic', 'q'))
        self.assertNotIn('fallbacks', self.anthropic_kwargs)
        client.messages.stream.assert_called_once()

    def test_claude_refusal(self):
        llm.update_provider('anthropic', api_key=KEY)
        with patch('anthropic.Anthropic', return_value=self._fake_anthropic('refusal')):
            events = list(llm.explain_events('anthropic', [], 'q', []))
        self.assertEqual(events[-1]['type'], 'error')
        self.assertIn('declined', events[-1]['message'])

    def test_prompt_contains_only_sanitized_data(self):
        prompt = llm.build_prompt([{'code': 'DOMAIN_MISMATCH', 'severity': 'error', 'summary': 'Different domains',
                                    'evidence': {'host_a': 'secret-host', 'ip': '10.1.2.3'}}], 'why?', [])
        self.assertIn('DOMAIN_MISMATCH', prompt)
        self.assertNotIn('secret-host', prompt)
        self.assertNotIn('10.1.2.3', prompt)
        with_doc = llm.build_prompt([], 'q', [{'id': 'ros-domain', 'title': 'Domain', 'url': 'https://docs.ros.org/x', 'excerpt': 'e'}])
        self.assertIn('[ros-domain]', with_doc)
        self.assertNotIn('https://', with_doc)


class ModelListTests(_TempConfig):
    def test_suggestions_without_key(self):
        r = self.client.get('/api/ai/providers/openai/models').json()
        self.assertEqual(r['source'], 'suggested')
        self.assertIn('gpt-5-mini', r['models'])
        self.assertIn('API key', r['message'])

    def test_openai_live_list_filters_non_chat_models(self):
        llm.update_provider('openai', api_key=KEY)
        data = {'data': [{'id': 'gpt-5-mini'}, {'id': 'gpt-5.1'}, {'id': 'text-embedding-3-small'},
                         {'id': 'whisper-1'}, {'id': 'gpt-4o-mini-tts'}, {'id': 'o3'}]}
        with patch('autodiag.llm._get_json', return_value=data) as get:
            r = self.client.get('/api/ai/providers/openai/models').json()
        self.assertEqual(r['source'], 'live')
        self.assertEqual(r['models'][0], 'gpt-5-mini')  # suggested first
        self.assertEqual(set(r['models']), {'gpt-5-mini', 'gpt-5.1', 'o3'})
        self.assertEqual(get.call_args.args[1]['Authorization'], 'Bearer ' + KEY)

    def test_gemini_live_list(self):
        llm.update_provider('gemini', api_key=KEY)
        data = {'models': [{'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']},
                           {'name': 'models/text-embedding-004', 'supportedGenerationMethods': ['embedContent']}]}
        with patch('autodiag.llm._get_json', return_value=data):
            self.assertEqual(llm.list_models('gemini')['models'], ['gemini-2.5-flash'])

    def test_claude_live_list(self):
        llm.update_provider('anthropic', api_key=KEY)
        client = MagicMock()
        client.models.list.return_value = [MagicMock(id='claude-opus-5-5'), MagicMock(id='claude-haiku-5-5')]
        with patch('anthropic.Anthropic', return_value=client):
            self.assertEqual(llm.list_models('anthropic')['models'], ['claude-opus-5-5', 'claude-haiku-5-5'])

    def test_ollama_lists_installed_without_embedding_models(self):
        with patch('autodiag.llm.installed_ollama_models', return_value=['qwen3:4b', 'nomic-embed-text:latest']):
            self.assertEqual(llm.list_models('ollama', refresh=True)['models'], ['qwen3:4b'])

    def test_rejected_key_falls_back_with_message(self):
        llm.update_provider('openai', api_key=KEY)
        def fail(url, headers, timeout=8):
            raise HTTPError(url, 401, 'unauth', {}, io.BytesIO(b'{"error":{"message":"bad key"}}'))
        with patch('autodiag.llm._get_json', side_effect=fail):
            r = llm.list_models('openai')
        self.assertEqual(r['source'], 'suggested')
        self.assertIn('rejected', r['message'])


class StreamEndpointTests(_TempConfig):
    def test_model_override_per_question(self):
        with patch('autodiag.llm.stream_answer', return_value=iter(['ok'])) as stream:
            r = self.client.post('/api/assistant/stream', json={'host_a': {'environment': {}}, 'provider': 'ollama',
                                                                'model': 'qwen2.5:3b'})
        events = [json.loads(line) for line in r.text.splitlines() if line]
        self.assertEqual(events[1]['model'], 'qwen2.5:3b')
        self.assertEqual(stream.call_args.args[2], 'qwen2.5:3b')

    def test_ndjson_stream(self):
        with patch('autodiag.llm.stream_answer', return_value=iter(['Check ', 'domains'])):
            r = self.client.post('/api/assistant/stream', json={
                'host_a': {'environment': {'ROS_DOMAIN_ID': '1'}, 'identity': {'host': 'a'}},
                'host_b': {'environment': {'ROS_DOMAIN_ID': '2'}, 'identity': {'host': 'b'}},
                'question': 'no data', 'provider': 'ollama'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/x-ndjson', r.headers['content-type'])
        events = [json.loads(line) for line in r.text.splitlines() if line]
        self.assertEqual([e['type'] for e in events], ['context', 'meta', 'token', 'token', 'done'])
        self.assertIn('DOMAIN_MISMATCH', [i['code'] for i in events[0]['issues']])
        self.assertTrue(events[0]['sources'])

    def test_topic_context_and_default_snapshot(self):
        report = {'state': 'ok', 'publisher_count': 1, 'subscriber_count': 1, 'findings': [
            {'code': 'RELIABILITY_MISMATCH', 'severity': 'error', 'summary': 'Incompatible reliability: lidar -> rviz'}],
            'endpoints': [{'kind': 'publisher', 'node': 'lidar', 'type': 'sensor_msgs/msg/LaserScan',
                           'qos': {'reliability': 'BEST_EFFORT', 'durability': 'VOLATILE'}}]}
        with patch('autodiag.server.inspect_topic', return_value=report) as inspect, \
             patch('autodiag.server.collect', return_value={'environment': {'ROS_DISTRO': 'jazzy'}}) as collect, \
             patch('autodiag.llm.stream_answer', return_value=iter(['ok'])) as stream:
            r = self.client.post('/api/assistant/stream', json={'topic': '/scan', 'question': 'empty display'})
        inspect.assert_called_once_with('/scan')
        collect.assert_called_once()
        context = json.loads(r.text.splitlines()[0])
        self.assertEqual(context['issues'][0]['code'], 'RELIABILITY_MISMATCH')
        self.assertIn('TOPIC_CONTEXT', [i['code'] for i in context['issues']])
        prompt = stream.call_args.args[1]
        self.assertIn('RELIABILITY_MISMATCH', prompt)
        self.assertIn('sensor_msgs/msg/LaserScan', prompt)

    def test_warmup_returns_immediately(self):
        with patch('autodiag.llm.warm_up_ollama'):
            self.assertEqual(self.client.post('/api/ai/warmup').json()['state'], 'warming')


if __name__ == '__main__':
    unittest.main()


class ConversationTests(_TempConfig):
    def test_turns_are_alternating_bounded_and_end_with_prompt(self):
        history = [{'role': 'assistant', 'content': 'orphan'}, {'role': 'user', 'content': 'q1'},
                   {'role': 'assistant', 'content': 'a1'}, {'role': 'assistant', 'content': 'a1b'},
                   {'role': 'system', 'content': 'ignore me'}, {'role': 'user', 'content': 'x' * 9000}]
        turns = llm.conversation('PROMPT', history)
        self.assertEqual([t['role'] for t in turns], ['user', 'assistant', 'user'])
        self.assertEqual(turns[1]['content'], 'a1\n\na1b')
        self.assertTrue(turns[-1]['content'].endswith('PROMPT'))
        self.assertLess(len(turns[-1]['content']), 3000)

    def test_history_reaches_every_provider_shape(self):
        history = [{'role': 'user', 'content': 'What is a domain?'}, {'role': 'assistant', 'content': 'An ID.'}]
        seen = {}

        def fake(url, body, headers, timeout):
            seen[url] = body
            return iter([b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
                         b'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}\n'])
        llm.update_provider('openai', api_key=KEY)
        llm.update_provider('gemini', api_key=KEY)
        with patch('autodiag.llm._post_stream', side_effect=fake):
            ''.join(llm.stream_answer('openai', 'follow-up', history=history))
            ''.join(llm.stream_answer('gemini', 'follow-up', history=history))
        openai_body = next(b for u, b in seen.items() if 'openai' in u)
        self.assertEqual([m['role'] for m in openai_body['messages']], ['system', 'user', 'assistant', 'user'])
        gemini_body = next(b for u, b in seen.items() if 'googleapis' in u)
        self.assertEqual([c['role'] for c in gemini_body['contents']], ['user', 'model', 'user'])

    def test_stream_endpoint_passes_history(self):
        with patch('autodiag.llm.stream_answer', return_value=iter(['ok'])) as stream:
            self.client.post('/api/assistant/stream', json={'host_a': {'environment': {}}, 'provider': 'ollama',
                                                            'history': [{'role': 'user', 'content': 'earlier'}]})
        self.assertEqual(stream.call_args.args[3], [{'role': 'user', 'content': 'earlier'}])
