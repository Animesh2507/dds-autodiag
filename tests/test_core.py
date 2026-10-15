import unittest
from autodiag.core import diagnose
class Tests(unittest.TestCase):
    def test_domain(self):
        self.assertIn('DOMAIN_MISMATCH',[f['code'] for f in diagnose({'domain_id':2},{'domain_id':3})])
    def test_reliability(self):
        self.assertIn('RELIABILITY_MISMATCH',[f['code'] for f in diagnose({'qos':{'reliability':'best_effort'}},{'qos':{'reliability':'reliable'}})])
    def test_durability(self):
        self.assertIn('DURABILITY_MISMATCH',[f['code'] for f in diagnose({'qos':{'durability':'volatile'}},{'qos':{'durability':'transient_local'}})])
    def test_no_false_success(self):
        self.assertEqual(diagnose({}, {})[0]['code'],'NO_STATIC_MISMATCH')
    def test_type(self):
        self.assertIn('TYPE_MISMATCH',[f['code'] for f in diagnose({'type':'A'},{'type':'B'})])
if __name__=='__main__':unittest.main()
