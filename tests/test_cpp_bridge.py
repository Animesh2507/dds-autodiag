import json
import unittest
from autodiag.cpp_bridge import check_endpoint

class TestCppBridge(unittest.TestCase):
    def test_missing_binary_graceful(self):
        result = check_endpoint({}, {})
        if result.get('state') == 'unavailable':
            self.assertIn('Build', result['reason'])
        else:
            self.assertIn('findings', result)
