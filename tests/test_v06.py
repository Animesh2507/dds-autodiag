import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from autodiag.rag import hybrid_retrieve, grounded_answer
from autodiag.validation import run_fixture, list_fixtures

D=[{'id':'alpha','title':'Domain ID','url':'https://docs.ros.org/a','text':'ROS domain mismatch between hosts'},
   {'id':'beta','title':'Network','url':'https://docs.ros.org/b','text':'Check multicast communication'}]

class V06Tests(unittest.TestCase):
    def test_bm25(self):
        self.assertEqual(hybrid_retrieve('domain mismatch',D)['mode'],'bm25')
    def test_hybrid_embeddings(self):
        def embedding(t):return [1.,0.] if 'domain' in t.lower() else [0.,1.]
        with tempfile.TemporaryDirectory() as tmp:
            result=hybrid_retrieve('domain',D,semantic=True,embedder=embedding,cache_dir=tmp)
            self.assertEqual(result['mode'],'hybrid_local_embeddings')
            self.assertEqual(result['sources'][0]['id'],'alpha')
            self.assertEqual(len(list(Path(tmp).glob('*.json'))),2)
    def test_semantic_failure_fallback(self):
        result=hybrid_retrieve('domain',D,semantic=True,embedder=lambda t: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(result['mode'],'bm25_fallback')
    def test_no_ai(self):
        self.assertEqual(grounded_answer([], 'discovery',docs=D)['ai']['state'],'disabled')
    def test_fault_fixture(self):
        self.assertIn('domain_mismatch',list_fixtures())
        self.assertTrue(run_fixture('domain_mismatch')['passed'])
    def test_unknown_fixture(self):
        with self.assertRaises(KeyError):run_fixture('missing')
