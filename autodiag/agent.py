"""Evidence-grounded diagnostic assistant. No automatic changes or agent tool execution."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .knowledge import DOCS, TITLES
from .redact import mask_for_cloud

# Each known issue is mapped to vetted official docs, not a model-generated URL.
ISSUE_DOCS = {
    'DOMAIN_MISMATCH': ('domain', 'Align domain IDs for the relevant ROS 2 processes.'),
    'ROS_ENV_NOT_SOURCED': ('network', 'Source /opt/ros/<distro>/setup.bash before starting AutoDiag, then refresh.'),
    'INVALID_DOMAIN_ID': ('domain', 'Set ROS_DOMAIN_ID to an integer from 0 to 101 and restart the processes.'),
    'DOMAIN_ID_OUTSIDE_SAFE_RANGE': ('domain', 'Move to a domain ID from 0 to 101 to avoid ephemeral-port collisions.'),
    'DISCOVERY_DISABLED': ('discovery', 'Enable automatic discovery or configure ROS_STATIC_PEERS.'),
    'DISCOVERY_RANGE_RESTRICTED': ('discovery', 'Check ROS_AUTOMATIC_DISCOVERY_RANGE on both peers; SUBNET is required across hosts.'),
    'ROS_LOCALHOST_ONLY_DEPRECATED': ('discovery', 'Replace ROS_LOCALHOST_ONLY with ROS_AUTOMATIC_DISCOVERY_RANGE.'),
    'LATCHED_DATA_VOLATILE_SUBSCRIBER': ('qos', 'Set the subscriber durability to Transient Local and restart it.'),
    'RMW_MISMATCH': ('rmw', 'Run both peers with the same RMW_IMPLEMENTATION and retest.'),
    'DISTRO_MISMATCH': ('distro', 'Retest with the same ROS 2 distribution on both peers.'),
    'LOCALHOST_ONLY': ('network', 'Inspect the discovery-range or localhost-only setting on both peers.'),
    'DDS_CONFIG_FILE_MISSING': ('cyclone_interfaces', 'Check that the middleware configuration exists and is mounted.'),
    'CYCLONE_CONFIG_RMW_MISMATCH': ('cyclone_interfaces', 'Inspect per-process RMW and DDS XML configuration.'),
    'SHM_NAMESPACE_UNVERIFIED': ('fastdds_docker', 'Inspect container IPC namespaces and actual enabled transports.'),
    'SHM_IPC_NAMESPACE_DIFFERENCE': ('fastdds_docker', 'Check Docker shared-memory requirements and UDP fallback.'),
    'MULTICAST_CAPABILITY_ABSENT': ('cyclone_discovery', 'Test discovery connectivity, including configured unicast peers.'),
    'INTRA_PROCESS_SEPARATE_PROCESSES': ('intraprocess', 'Intra-process delivery cannot cross process boundaries.'),
    'INTRA_PROCESS_NOT_AUTODETECTABLE': ('intraprocess', 'Inspect per-node intra-process options; this collector cannot infer them.'),
}

def evidence_report(snapshot, findings, topic_report=None):
    """Build limited diagnostic hypotheses, never invented confirmed causes."""
    hypotheses=[]
    for finding in findings:
        code=str(finding.get('code','UNKNOWN'))
        doc_key, next_step=ISSUE_DOCS.get(code, ('network', 'Collect additional host and endpoint evidence.'))
        # Unknown diagnostic codes must not be promoted to high-confidence assertions.
        hypotheses.append({'issue_code':code,'severity':finding.get('severity','info'),
                           'confidence':finding.get('confidence','unknown'),
                           'observation':finding.get('summary',''),
                           'evidence':finding.get('evidence',{}),
                           'next_test': next_step,
                           'documentation':[{'label':TITLES.get(doc_key,doc_key),'url':DOCS[doc_key]}]})
    if not hypotheses:
        hypotheses=[{'issue_code':'NO_CONFIRMED_CAUSE','severity':'info','confidence':'unknown',
                     'observation':'No configured diagnostic rule established a root cause.',
                     'evidence':{},'next_test':'Inspect live endpoint QoS and verify actual sample delivery on both hosts.',
                     'documentation':[{'label':TITLES['qos'],'url':DOCS['qos']}]}]
    return {'mode':'deterministic','hypotheses':hypotheses,'tested_data_delivery':False,
            'caveat':'Environment snapshots may not represent every running process or prove sample delivery.',
            'topic_report':topic_report}

SYSTEM = """You are an engineering diagnostic explainer. Only interpret the evidence in the supplied JSON.
Never assert that a hypothesis is confirmed unless the evidence explicitly confirms it.
Clearly distinguish confirmed configuration mismatch, warning, and unknown; identify missing tests.
Do not invent configurations, measurements, command outputs, documentation links, or vendor identifiers.
No automatic repairs. Never ask for secrets. Respond only in valid JSON with fields summary, possible_causes, next_tests, limitations. possible_causes and next_tests must be arrays of strings."""

def optional_model_explanation(report, *, api_key=None, model=None, endpoint=None, timeout=12):
    """Opt-in, fixed OpenAI-compatible endpoint; sends redacted evidence ONLY. No remote URL inputs."""
    key=api_key or os.getenv('AUTODIAG_LLM_API_KEY')
    model=model or os.getenv('AUTODIAG_LLM_MODEL','')
    endpoint=endpoint or os.getenv('AUTODIAG_LLM_ENDPOINT','https://api.openai.com/v1/chat/completions')
    if not key or not model:
        return {'state':'disabled','reason':'Set AUTODIAG_LLM_API_KEY and AUTODIAG_LLM_MODEL to enable optional AI explanation.'}
    if endpoint != 'https://api.openai.com/v1/chat/completions':
        return {'state':'disabled','reason':'Only the fixed official API endpoint is allowed in this release.'}
    # Do not send raw snapshots: their IPs, usernames, paths, topic payloads may be sensitive.
    sanitized=[{'code':h['issue_code'],'severity':h['severity'],'observation':h['observation'],
               'next_test':h['next_test']} for h in report['hypotheses']]
    sanitized=mask_for_cloud(sanitized)
    body={'model':model,'temperature':0,'messages':[{'role':'system','content':SYSTEM},
            {'role':'user','content':json.dumps({'findings':sanitized,'tested_data_delivery':False})}]}
    request=Request(endpoint,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,
                    'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(request,timeout=timeout) as response:
            result=json.load(response)
        content=result['choices'][0]['message']['content']
        parsed=json.loads(content)
        if not isinstance(parsed,dict) or not all(k in parsed for k in ('summary','possible_causes','next_tests','limitations')):
            raise ValueError('Unexpected AI response structure')
        return {'state':'ok','explanation':parsed,'note':'Untrusted model suggestions; use deterministic findings as source of truth.'}
    except (HTTPError,URLError,ValueError,KeyError,IndexError,TimeoutError) as exc:
        return {'state':'error','reason':type(exc).__name__}
