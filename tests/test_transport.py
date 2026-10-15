import unittest
from autodiag.transport import health,transport_diagnose

def snap(domain='8',host='a',rmw='rmw_cyclonedds_cpp'):
    return {'environment':{'ROS_DOMAIN_ID':domain,'RMW_IMPLEMENTATION':rmw},'identity':{'host':host,'pid':1},'container':{'detected':False},'network':{'interfaces':[]},'transport':{'requested_mode':'auto'},'ros':{'cli_available':True,'daemon':{'state':'running'},'graph':{'state':'ok'}}}
class TestTransport(unittest.TestCase):
    def test_domain(self): self.assertIn('DOMAIN_MISMATCH',[x['code'] for x in transport_diagnose(snap(),snap('9'))])
    def test_localhost(self):
        a=snap();a['environment']['ROS_LOCALHOST_ONLY']='1'
        self.assertIn('LOCALHOST_ONLY',[x['code'] for x in transport_diagnose(a,snap(host='b'))])
    def test_intra(self):
        a=snap();a['transport']['requested_mode']='intra_process'
        b=snap(host='b');b['identity']['pid']=2
        self.assertIn('INTRA_PROCESS_SEPARATE_PROCESSES',[x['code'] for x in transport_diagnose(a,b)])
    def test_shm(self):
        a=snap();b=snap('8','a');a['transport']['requested_mode']='dds_shm'
        a['container']={'detected':True,'ipc_namespace':'ipc:[1]'};b['container']={'detected':True,'ipc_namespace':'ipc:[2]'}
        self.assertIn('SHM_IPC_NAMESPACE_DIFFERENCE',[x['code'] for x in transport_diagnose(a,b)])
    def test_health_conservative(self):self.assertEqual(health(snap(),[])['status'],'insufficient_evidence')
    def test_config(self):
        a=snap();a['environment']['CYCLONEDDS_URI']='file:///missing.xml';a['config_files']={'CYCLONEDDS_URI':{'status':'missing'}}
        self.assertIn('DDS_CONFIG_FILE_MISSING',[x['code'] for x in transport_diagnose(a)])
if __name__=='__main__':unittest.main()
