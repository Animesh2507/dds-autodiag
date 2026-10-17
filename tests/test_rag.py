import tempfile
import unittest
from unittest.mock import patch
from autodiag.rag import answer, documents, hybrid_retrieve, retrieve, retrieve_for, terms, _ollama_post

class TestLocalRAG(unittest.TestCase):
    def test_documents(self):
        self.assertGreaterEqual(len(documents()),6)
    def test_qos_retrieval(self):
        hits=retrieve('publisher best effort subscriber reliable QoS mismatch')
        self.assertIn('ros-qos',[d['id'] for d in hits])
    def test_docker_retrieval(self):
        hits=retrieve('Fast DDS shared memory IPC Docker namespace')
        self.assertIn('fastdds-docker',[d['id'] for d in hits])
    def test_no_ai_needed(self):
        result=answer([{'code':'DOMAIN_MISMATCH','summary':'Different domain IDs'}])
        self.assertEqual(result['ai']['state'],'disabled')
    def test_ai_offline_failure(self):
        with patch('autodiag.rag._ollama_post',side_effect=OSError('offline')):
            result=answer([],question='qos',use_ai=True)
        self.assertEqual(result['ai']['state'],'unavailable')
    def test_ollama_restrict_remote_hosts(self):
        with patch.dict('os.environ',{'AUTODIAG_OLLAMA_URL':'http://external.example:11434'}):
            with self.assertRaises(ValueError):
                _ollama_post('/api/chat',{})
    def test_empty(self):
        self.assertEqual(retrieve('anything',[]),[])
    def test_plural_and_stop_words(self):
        # "what are ros actions" must reach the actions page: no stop words, "actions" folded to "action".
        self.assertEqual(retrieve('what are ros actions?')[0]['id'],'ros-actions')
        self.assertEqual(terms('What are the ROS 2 parameters?'),['parameter'])
    def test_unrelated_question_gets_no_documents(self):
        self.assertEqual(retrieve('what is the weather today'),[])
        self.assertEqual(retrieve('how do I use it'),[])
    def test_symptoms_reach_the_right_pages(self):
        self.assertEqual(retrieve('robot and laptop cannot see each other')[0]['id'],'ros-domain')
        self.assertEqual(retrieve('tf error frame does not exist')[0]['id'],'ros-tf2')
        self.assertIn('fastdds-docker',[d['id'] for d in retrieve(
            "Two Docker containers see each other's topics but receive no data")])
    def test_question_first_then_findings(self):
        result=retrieve_for('what are ros actions?','DOMAIN_MISMATCH Different ROS_DOMAIN_ID values')
        ids=[d['id'] for d in result['sources']]
        self.assertEqual(ids[0],'ros-actions')
        self.assertIn('ros-domain',ids)
        self.assertEqual(result['mode'],'bm25')
    def test_semantic_matches_need_similarity(self):
        docs=[{'id':'near','title':'Near','url':'https://x','text':'alpha'},
              {'id':'far','title':'Far','url':'https://y','text':'beta'}]
        vectors={'query':[1.0,0.0],'Near alpha':[0.9,0.3],'Far beta':[0.2,0.98]}
        with tempfile.TemporaryDirectory() as cache:
            result=hybrid_retrieve('query',docs,semantic=True,embedder=lambda t:vectors[t],cache_dir=cache)
        self.assertEqual([d['id'] for d in result['sources']],['near'])
    def test_knowledge_base_is_consistent(self):
        docs=documents()
        self.assertEqual(len({d['id'] for d in docs}),len(docs))
        for d in docs:
            self.assertTrue(d['url'].startswith('https://'),d['id'])
            self.assertTrue(d.get('keywords'),d['id'])
            # Every page is reachable by its own title.
            self.assertIn(d['id'],[hit['id'] for hit in retrieve(d['title'],limit=8)],d['id'])
if __name__=='__main__':unittest.main()
