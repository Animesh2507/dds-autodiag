import unittest
from unittest.mock import patch
from autodiag.live import sample_topic

class TopicSampleTests(unittest.TestCase):
    def test_reject_shell_metacharacters(self):
        self.assertEqual(sample_topic('/x;echo hacked')['state'], 'invalid')
    def test_reject_invalid_qos(self):
        self.assertEqual(sample_topic('/chatter',reliability='unknown')['state'],'invalid')
    def test_reject_long_timeout(self):
        self.assertEqual(sample_topic('/chatter',timeout=60)['state'],'invalid')
    def test_receives_sample(self):
        with patch('autodiag.live._call',return_value={'state':'ok','stdout':'data: hello\n---\n','stderr':''}) as call:
            result=sample_topic('/chatter',reliability='best_effort')
        self.assertEqual(result['state'],'ok')
        self.assertIn('hello',result['raw'])
        self.assertEqual(call.call_args.args[0],['topic','echo','/chatter','--once','--qos-reliability','best_effort'])
    def test_times_out(self):
        with patch('autodiag.live._call',return_value={'state':'timeout','error':'timed out'}):
            result=sample_topic('/silent')
        self.assertEqual(result['state'],'timeout')
