import unittest
from unittest.mock import patch
from autodiag.rag import answer, documents, retrieve, _ollama_post

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
if __name__=='__main__':unittest.main()
