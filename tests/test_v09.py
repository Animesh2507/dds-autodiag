import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from autodiag.server import app
from autodiag.enhanced import detect_rmw, inspect_shm, discover_local_containers

class TestV09(unittest.TestCase):
    def test_rmw_doctor_parsing(self):
        with patch('autodiag.enhanced.shutil.which', return_value='/usr/bin/ros2'), patch('autodiag.enhanced.run',return_value={'state':'ok','stdout':'RMW MIDDLEWARE\nmiddleware name : rmw_fastrtps_cpp'}),patch.dict('os.environ',{},clear=True):
            o=detect_rmw();self.assertEqual(o['effective'],'rmw_fastrtps_cpp');self.assertIsNone(o['configured'])
    def test_no_shm_claim(self):
        self.assertEqual(inspect_shm()['actual_transport'],'NOT_VERIFIED')
    def test_docker_cli_unavailable(self):
        with patch('autodiag.enhanced.shutil.which',return_value=None):
            self.assertEqual(discover_local_containers()['state'],'unavailable')
    def test_ui_and_endpoints(self):
        c=TestClient(app)
        for path in ('/','/legacy','/api/v09/overview','/api/v09/shm','/api/v09/ollama','/api/v09/environments'):
            self.assertEqual(c.get(path).status_code,200,path)
        html=c.get('/').text
        self.assertIn('Unified diagnostic assistant',html)
        self.assertIn('Local Docker environments',html)
        self.assertIn('NOT VERIFIED',html)
