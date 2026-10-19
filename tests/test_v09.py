import json
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

    def test_docker_lists_ip_and_connect_url(self):
        ps = {'state': 'ok', 'stdout': json.dumps({
            'ID': 'abc123def456', 'Names': 'lab-collector', 'Image': 'dds-autodiag:lab',
            'Status': 'Up', 'Networks': 'host'}) + '\n'}
        inspect = {'state': 'ok', 'stdout': json.dumps([{
            'Id': 'abc123def4569999',
            'HostConfig': {'NetworkMode': 'host'},
            'NetworkSettings': {'Networks': {}, 'Ports': {}},
            'Config': {'Env': ['AUTODIAG_PORT=18087', 'ROS_DOMAIN_ID=87']},
        }])}
        with patch('autodiag.enhanced.shutil.which', return_value='/usr/bin/docker'), \
             patch('autodiag.enhanced.run', side_effect=[ps, inspect]):
            out = discover_local_containers()
        self.assertEqual(out['state'], 'ok')
        row = out['environments'][0]
        self.assertEqual(row['ports'], ['18087'])
        self.assertIn('http://127.0.0.1:18087', row['connect_urls'])
    def test_ui_and_endpoints(self):
        c=TestClient(app)
        for path in ('/','/legacy','/api/v09/overview','/api/v09/shm','/api/v09/ollama','/api/v09/environments'):
            self.assertEqual(c.get(path).status_code,200,path)
        html=c.get('/').text
        self.assertIn('Diagnostic assistant',html)
        self.assertIn('Local Docker environments',html)
        self.assertIn('NOT VERIFIED',html)
