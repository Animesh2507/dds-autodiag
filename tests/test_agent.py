import unittest
from autodiag.agent import evidence_report, optional_model_explanation
from autodiag.server import app
from fastapi.testclient import TestClient

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.a={'environment':{'ROS_DOMAIN_ID':'8'},'transport':{},'ros':{},'network':{},'container':{}}
        self.b={'environment':{'ROS_DOMAIN_ID':'9'},'transport':{},'ros':{},'network':{},'container':{}}
    def test_linked_evidence(self):
        r=evidence_report(self.a,[{'code':'DOMAIN_MISMATCH','severity':'error','confidence':'high','summary':'Different domains','evidence':{'a':8,'b':9}}]);
        self.assertEqual(r['hypotheses'][0]['issue_code'],'DOMAIN_MISMATCH');self.assertTrue(r['hypotheses'][0]['documentation'][0]['url'].startswith('https://'))
    def test_no_false_success(self):
        self.assertEqual(evidence_report(self.a,[])['hypotheses'][0]['issue_code'],'NO_CONFIRMED_CAUSE')
    def test_llm_disabled_without_credentials(self):
        self.assertEqual(optional_model_explanation(evidence_report(self.a,[]),api_key='',model='')['state'],'disabled')
    def test_api(self):
        r=TestClient(app).post('/api/assistant/diagnose',json={'host_a':self.a,'host_b':self.b})
        self.assertEqual(r.status_code,200);self.assertIn('DOMAIN_MISMATCH',[x['issue_code'] for x in r.json()['hypotheses']])
    def test_no_ai_by_default(self):
        r=TestClient(app).post('/api/assistant/diagnose',json={'host_a':self.a})
        self.assertNotIn('ai',r.json())

if __name__=='__main__': unittest.main()
