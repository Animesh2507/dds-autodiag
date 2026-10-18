import tempfile
import unittest
from unittest.mock import patch
from autodiag import llm
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
        self.assertIn('ros-domain',[d['id'] for d in retrieve('robot and laptop cannot see each other')])
        self.assertEqual(retrieve('tf error frame does not exist')[0]['id'],'ros-tf2')
        self.assertIn('fastdds-docker',[d['id'] for d in retrieve(
            "Two Docker containers see each other's topics but receive no data")])
    def test_maths_and_control_questions(self):
        cases={'my imu reads -9.81 on z at rest':'math-imu','quaternion is invalid in rviz':'math-quaternions',
               'yaw angle wraps around at 180 degrees':'math-euler-angles','my map is shifted in rviz':'math-occupancy-grid',
               'robot does not move with teleop keyboard':'control-cmd-vel',
               'controller is loaded but not active':'control-controller-cli','pid oscillates and overshoots':'control-pid',
               'robot stops short of the goal':'control-nav2-controller-server',
               'robot curves when driving straight':'control-wheel-kinematics'}
        for question,page in cases.items():
            self.assertEqual(retrieve(question)[0]['id'],page,question)
    def test_questions_about_autodiag_itself(self):
        # "this tool" means AutoDiag: how-to questions must reach its own pages.
        self.assertEqual(retrieve('I have 2 robots and i want to transfer the ros config, how can i use this tool '
                                  'for it to compare?')[0]['id'],'autodiag-compare')
        self.assertEqual(retrieve('what can this tool do')[0]['id'],'autodiag-overview')
        cases={'how do I start the dashboard':'autodiag-dashboard','how do I add my claude api key':'autodiag-ai-setup',
               'which commands does dds-autodiag have':'autodiag-cli','how does configure rviz work':'autodiag-configure-rviz',
               'use it on my robot from my laptop':'autodiag-remote-access','can I call autodiag from a script':'autodiag-rest-api'}
        for question,page in cases.items():
            self.assertIn(page,[d['id'] for d in retrieve(question)],question)
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
    def test_whole_pages_reach_the_model(self):
        # A cut-off excerpt makes the model say the documentation is incomplete.
        longest=max(documents(),key=lambda d:len(d['text']))
        self.assertLessEqual(len(longest['text']),llm.EXCERPT_CHARS,longest['id'])
        hit=next(d for d in retrieve(longest['title'],limit=8) if d['id']==longest['id'])
        self.assertIn(longest['text'],llm.build_prompt([],'q',[hit]))
    def test_knowledge_base_is_consistent(self):
        docs=documents()
        self.assertEqual(len({d['id'] for d in docs}),len(docs))
        for d in docs:
            self.assertTrue(d['url'].startswith('https://'),d['id'])
            self.assertTrue(d.get('keywords'),d['id'])
            # Every page is reachable by its own title.
            self.assertIn(d['id'],[hit['id'] for hit in retrieve(d['title'],limit=8)],d['id'])
if __name__=='__main__':unittest.main()
