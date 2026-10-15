from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Finding:
    code: str
    severity: str
    conclusion: str
    evidence: dict
    recommendation: str
    confidence: str = 'high'

def diagnose(a: dict[str, Any], b: dict[str, Any]) -> list[dict]:
    findings=[]
    def add(code, severity, conclusion, evidence, recommendation, confidence='high'):
        findings.append(asdict(Finding(code,severity,conclusion,evidence,recommendation,confidence)))
    if a.get('domain_id') is not None and b.get('domain_id') is not None and a['domain_id'] != b['domain_id']:
        add('DOMAIN_MISMATCH','error','Different ROS_DOMAIN_ID values',{'host_a':a['domain_id'],'host_b':b['domain_id']},'Align ROS_DOMAIN_ID on both systems and restart managed ROS processes.')
    if a.get('topic') and b.get('topic') and a['topic'] != b['topic']:
        add('TOPIC_MISMATCH','error','Topic names differ',{'publisher':a['topic'],'subscriber':b['topic']},'Use identical resolved topic names or explicit remapping.')
    if a.get('type') and b.get('type') and a['type'] != b['type']:
        add('TYPE_MISMATCH','error','ROS message types differ',{'publisher':a['type'],'subscriber':b['type']},'Use matching ROS interface types and compatible definitions.')
    offered=a.get('qos',{}); requested=b.get('qos',{})
    if offered.get('reliability')=='best_effort' and requested.get('reliability')=='reliable':
        add('RELIABILITY_MISMATCH','error','Offered reliability cannot satisfy requested reliability',{'offered':'best_effort','requested':'reliable'},'Request best_effort on the subscriber if application semantics permit.')
    if offered.get('durability')=='volatile' and requested.get('durability')=='transient_local':
        add('DURABILITY_MISMATCH','error','Offered durability cannot satisfy requested durability',{'offered':'volatile','requested':'transient_local'},'Use a volatile subscriber or a transient_local publisher as appropriate.')
    if a.get('network',{}).get('multicast') is False or b.get('network',{}).get('multicast') is False:
        add('MULTICAST_WARNING','warning','Multicast reported unavailable on at least one host',{'host_a':a.get('network',{}).get('multicast'),'host_b':b.get('network',{}).get('multicast')},'Check discovery configuration and test multicast or configured unicast peers.','medium')
    if not findings:
        add('NO_STATIC_MISMATCH','info','No supported static mismatch detected',{'inputs':'provided snapshots'},'Verify endpoint discovery and actual data delivery; this result does not prove connectivity.','medium')
    return findings
