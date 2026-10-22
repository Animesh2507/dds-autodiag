import unittest
from unittest.mock import patch
from autodiag.live import _parse_verbose,_qos_findings,inspect_topic,topic_list
from autodiag.remote import fetch_snapshot
from autodiag.server import check_agent_token
from fastapi import HTTPException
class LiveTests(unittest.TestCase):
 def test_parse_and_mismatch(self):
  s="""Publisher count: 1
Node name: talker
Topic type: geometry_msgs/msg/PoseStamped
Reliability: BEST_EFFORT
Durability: VOLATILE
Subscription count: 1
Node name: listener
Topic type: geometry_msgs/msg/PoseStamped
Reliability: RELIABLE
Durability: VOLATILE
"""
  e=_parse_verbose(s)
  self.assertEqual(len(e),2)
  self.assertEqual(_qos_findings(e)[0]['code'],'RELIABILITY_MISMATCH')
 def test_parse_keeps_node_namespace(self):
  s="""Publisher count: 1
Node name: sensor
Node namespace: /robot1
Topic type: sensor_msgs/msg/LaserScan
Reliability: BEST_EFFORT
Durability: VOLATILE
Subscription count: 1
Node name: sensor
Node namespace: /robot2
Topic type: sensor_msgs/msg/LaserScan
Reliability: RELIABLE
Durability: VOLATILE
"""
  e=_parse_verbose(s)
  self.assertEqual([x['node'] for x in e],['robot1/sensor','robot2/sensor'])
  self.assertEqual(_qos_findings(e)[0]['code'],'RELIABILITY_MISMATCH')
 def test_parse_root_namespace_is_bare_name(self):
  s="""Publisher count: 1
Node name: talker
Node namespace: /
Topic type: std_msgs/msg/String
Reliability: RELIABLE
"""
  self.assertEqual(_parse_verbose(s)[0]['node'],'talker')
 def test_compatible(self):
  e=[{'kind':'publisher','node':'p','qos':{'reliability':'RELIABLE','durability':'TRANSIENT_LOCAL'}},{'kind':'subscriber','node':'s','qos':{'reliability':'BEST_EFFORT','durability':'VOLATILE'}}]
  # QoS-compatible (no errors); only the late-joiner warning for latched data remains.
  f=_qos_findings(e)
  self.assertEqual([x for x in f if x['severity']=='error'],[])
  self.assertEqual([x['code'] for x in f],['LATCHED_DATA_VOLATILE_SUBSCRIBER'])
 def test_reject_bad_topic(self):self.assertEqual(inspect_topic('/abc;rm -rf /')['state'],'invalid')
 def test_topics_error(self):
  with patch('autodiag.live._call',return_value={'state':'unavailable','error':'no ros2'}):
   self.assertEqual(topic_list()['state'],'unavailable')
 def test_remote_reject_public(self):
  with self.assertRaises(ValueError):fetch_snapshot('http://8.8.8.8:8080','secret')
 def test_remote_reject_name(self):
  with self.assertRaises(ValueError):fetch_snapshot('http://example.com:8080','secret')
 def test_agent_auth(self):
  with patch.dict('os.environ',{'AUTODIAG_AGENT_TOKEN':'safe-secret'}):
   check_agent_token('safe-secret')
   with self.assertRaises(HTTPException):check_agent_token('bad')

 def test_latched_publisher_volatile_subscriber(self):
  e=[{'kind':'publisher','node':'map_server','qos':{'reliability':'RELIABLE','durability':'TRANSIENT_LOCAL'}},
     {'kind':'subscriber','node':'rviz','qos':{'reliability':'RELIABLE','durability':'VOLATILE'}}]
  f=_qos_findings(e)
  self.assertEqual([x['code'] for x in f],['LATCHED_DATA_VOLATILE_SUBSCRIBER'])
  self.assertEqual(f[0]['severity'],'warning')
 def test_latched_both_sides_is_clean(self):
  e=[{'kind':'publisher','node':'map_server','qos':{'reliability':'RELIABLE','durability':'TRANSIENT_LOCAL'}},
     {'kind':'subscriber','node':'rviz','qos':{'reliability':'RELIABLE','durability':'TRANSIENT_LOCAL'}}]
  self.assertEqual(_qos_findings(e),[])
if __name__=='__main__':unittest.main()
