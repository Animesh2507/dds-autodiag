"""Local read-only dashboard and optional authenticated snapshot agent."""
import hmac
import json
import threading
import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import __version__
from .config import public_settings, settings
from .security import COOKIE, SecurityMiddleware
from .collector import collect, summarize
from .core import diagnose
from .transport import health, transport_diagnose
from .knowledge import DOCS
from .live import topic_list, inspect_topic, sample_topic
from .graph import build_graph
from .remote import fetch_snapshot
from .agent import evidence_report, optional_model_explanation
from .redact import mask_for_cloud, node_labels, redact_snapshot
from .report import markdown_report, sort_issues
from .validation import run_fixture, list_fixtures, run_all

HERE = Path(__file__).parent
log = logging.getLogger('autodiag')

app = FastAPI(title='DDS AutoDiag', version=__version__, docs_url='/api/docs', redoc_url=None,
              description='Read-only ROS 2 / DDS communication diagnostics. No endpoint changes your system.')
app.add_middleware(SecurityMiddleware)
app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log the details server-side; never leak tracebacks or command output to the browser.
    log.exception('Unhandled error on %s %s', request.method, request.url.path)
    return JSONResponse({'detail': f'Internal error ({type(exc).__name__}). See server log.'}, status_code=500)


class Comparison(BaseModel):
    host_a: dict
    host_b: dict | None = None


class RemoteRequest(BaseModel):
    url: str = Field(max_length=300)
    token: str = Field(max_length=500)
    host_a: dict | None = None


def check_agent_token(token):
    expected = os.environ.get('AUTODIAG_AGENT_TOKEN', '')
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail='Collector token required or invalid')


# --- Service ---------------------------------------------------------------------------------

@app.get('/api/healthz', tags=['service'])
def healthz():
    """Liveness probe for supervisors (systemd, Docker). Does not run diagnostics."""
    return {'status': 'ok', 'version': __version__}


@app.get('/api/version', tags=['service'])
def version():
    from .cpp_bridge import binary_path
    from .bt_visualizer import _binary
    return {'version': __version__, 'settings': public_settings(),
            'native_core_available': binary_path().is_file(), 'native_bt_available': _binary() is not None}


# --- Login (only active when AUTODIAG_UI_TOKEN is set) ---------------------------------------

LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DDS AutoDiag · Sign in</title><link rel="stylesheet" href="/static/app.css"></head>
<body class="login"><form class="card login-card" method="post" action="/login"><div class="brand"><b>◇</b> DDS AutoDiag</div>
<h1>Sign in</h1><p class="muted">This dashboard is protected by a token (AUTODIAG_UI_TOKEN).</p>{error}
<label class="field"><span>Access token</span><input name="token" type="password" autocomplete="current-password" autofocus required></label>
<button class="primary" type="submit">Sign in</button></form></body></html>"""


@app.get('/login', response_class=HTMLResponse, include_in_schema=False)
def login_page():
    if not settings().auth_enabled:
        return RedirectResponse('/', status_code=303)
    return LOGIN_PAGE.format(error='')


@app.post('/login', include_in_schema=False)
async def login(request: Request):
    # Parsed by hand: avoids a python-multipart dependency for a single field.
    body = (await request.body())[:2000].decode('utf-8', 'replace')
    token = parse_qs(body).get('token', [''])[0]
    expected = settings().ui_token
    if not expected:
        return RedirectResponse('/', status_code=303)
    if not hmac.compare_digest(expected.encode(), token.encode()):
        log.warning('Failed dashboard login from %s', request.client.host if request.client else 'unknown')
        return HTMLResponse(LOGIN_PAGE.format(error='<p class="notice error">Invalid token.</p>'), status_code=401)
    response = RedirectResponse('/', status_code=303)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', secure=request.url.scheme == 'https',
                        max_age=12 * 3600)
    return response


@app.post('/logout', include_in_schema=False)
def logout():
    response = RedirectResponse('/login' if settings().auth_enabled else '/', status_code=303)
    response.delete_cookie(COOKIE)
    return response


# --- Snapshots and environment ---------------------------------------------------------------

@app.get('/api/agent/snapshot', tags=['collector'])
def agent_snapshot(x_autodiag_token: str | None = Header(default=None)):
    check_agent_token(x_autodiag_token)
    return collect()


@app.get('/api/snapshot', tags=['snapshot'])
def snapshot(redact: bool = False):
    """Local snapshot. `redact=true` hashes hostnames, IP addresses and home paths for sharing."""
    s = collect()
    return redact_snapshot(s, salt=secrets.token_hex(8)) if redact else s


@app.post('/api/snapshot/redact', tags=['snapshot'])
def redact_pair(data: Comparison):
    """Redact one or two snapshots with a shared salt so cross-host comparisons still work."""
    salt = secrets.token_hex(8)
    return {'host_a': redact_snapshot(data.host_a, salt),
            'host_b': redact_snapshot(data.host_b, salt) if data.host_b else None}


@app.get('/api/health', tags=['diagnose'])
def health_api():
    s = collect()
    issues = transport_diagnose(s)
    return {'health': health(s, issues), 'issues': issues}


@app.get('/api/topics', tags=['live'])
def topics():
    return topic_list()


@app.get('/api/topic-inspect', tags=['live'])
def topic_inspect(topic: str):
    return inspect_topic(topic)


@app.get('/api/topic-sample', tags=['live'])
def topic_sample(topic: str, timeout: int = 8, reliability: str = 'auto'):
    return sample_topic(topic, timeout, reliability)


@app.get('/api/graph', tags=['live'])
def graph(max_topics: int = 40, include_hidden: bool = False):
    """Publisher -> subscriber graph of the visible topics, each connection checked by the QoS/type rules."""
    return build_graph(max_topics, include_hidden)


@app.get('/api/docs-links', tags=['knowledge'])
def docs_links():
    return DOCS


# --- Diagnosis ---------------------------------------------------------------------------------

@app.post('/api/compare', tags=['diagnose'])
def compare(data: Comparison):
    issues = sort_issues(transport_diagnose(data.host_a, data.host_b))
    return {'issues': issues, 'health': health(data.host_a, issues), 'read_only': True,
            'summary_a': summarize(data.host_a), 'summary_b': summarize(data.host_b) if data.host_b else None,
            'remote_evidence': 'provided_by_operator' if data.host_b else 'not_provided'}


def _remote_error(e):
    code = getattr(e, 'code', None)
    if code == 403:
        return 'The collector rejected the token. Check AUTODIAG_AGENT_TOKEN on the peer.'
    if code is not None:
        return f'The collector answered with HTTP {code}. Is the URL pointing at a DDS AutoDiag server?'
    reason = getattr(e, 'reason', e)
    if isinstance(reason, ConnectionRefusedError):
        return 'Connection refused: nothing is listening at that address/port. Is the collector running?'
    if isinstance(reason, TimeoutError) or isinstance(e, TimeoutError):
        return 'Timed out connecting to the collector. Check the IP address, firewall and SSH tunnel.'
    return f'Could not reach the collector ({type(reason).__name__}).'


@app.post('/api/remote-compare', tags=['diagnose'])
def remote_compare(data: RemoteRequest):
    try:
        remote = fetch_snapshot(data.url, data.token)
    except ValueError as e:
        # Our own validation messages (bad URL, schema, size) are safe and actionable.
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Don't reflect potentially sensitive remote response content.
        detail = _remote_error(e)
        raise HTTPException(status_code=502, detail=detail) from e
    local = data.host_a or collect()
    issues = sort_issues(transport_diagnose(local, remote))
    return {'issues': issues, 'health': health(local, issues), 'remote': remote,
            'summary_a': summarize(local), 'summary_b': summarize(remote),
            'read_only': True, 'remote_evidence': 'live_authenticated_collector'}


@app.post('/api/report', response_class=PlainTextResponse, tags=['diagnose'])
def report(data: Comparison):
    """Markdown report of the comparison, suitable for tickets and chat."""
    issues = transport_diagnose(data.host_a, data.host_b)
    text = markdown_report(data.host_a, data.host_b, issues, health(data.host_a, issues))
    return PlainTextResponse(text, media_type='text/markdown; charset=utf-8',
                             headers={'Content-Disposition': 'attachment; filename="dds-autodiag-report.md"'})


@app.get('/api/selftest', tags=['diagnose'])
def selftest():
    """Run every diagnostic rule against its synthetic fault fixture."""
    return run_all()


@app.post('/api/diagnose', tags=['legacy'])
def legacy(data: dict):
    if not isinstance(data.get('publisher'), dict) or not isinstance(data.get('subscriber'), dict):
        raise HTTPException(422, 'Body must contain "publisher" and "subscriber" objects')
    return {'findings': diagnose(data['publisher'], data['subscriber'])}


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def index():
    return (HERE / 'index.html').read_text()


class AssistantRequest(BaseModel):
    host_a: dict
    host_b: dict | None = None
    explain_with_ai: bool = False


@app.post('/api/assistant/diagnose', tags=['assistant'])
def assistant_diagnose(data: AssistantRequest):
    # Default is deterministic, no external LLM calls.
    issues = transport_diagnose(data.host_a, data.host_b)
    report = evidence_report(data.host_a, issues)
    report['health'] = health(data.host_a, issues)
    if data.explain_with_ai:
        report['ai'] = optional_model_explanation(report)
    return report


from .rag import answer, documents, grounded_answer


class RAGRequest(BaseModel):
    host_a: dict
    host_b: dict | None = None
    question: str = Field(default='', max_length=2000)
    use_local_ai: bool = False


@app.get('/api/rag/status', tags=['assistant'])
def rag_status():
    return {'retrieval': 'offline BM25', 'documents': len(documents()),
            'ai_provider': 'optional local Ollama', 'ai_model': settings().ollama_model,
            'remote_ai_required': False}


@app.post('/api/rag/explain', tags=['assistant'])
def rag_explain(payload: RAGRequest):
    issues = transport_diagnose(payload.host_a, payload.host_b)
    out = answer(issues, payload.question, use_ai=payload.use_local_ai)
    out['health'] = health(payload.host_a, issues)
    return out


class EnhancedRAGRequest(RAGRequest):
    semantic_search: bool = False


@app.post('/api/v06/explain', tags=['assistant'])
def v06_explain(payload: EnhancedRAGRequest):
    issues = transport_diagnose(payload.host_a, payload.host_b)
    output = grounded_answer(issues, payload.question, semantic=payload.semantic_search, use_ai=payload.use_local_ai)
    output['health'] = health(payload.host_a, issues)
    output['issues'] = sort_issues(issues)
    output['diagnostic_provenance'] = 'rule_based_host_snapshots'
    return output


# --- AI explanations (streaming) and provider management -------------------------------------

from .rag import hybrid_retrieve
from . import llm


class StreamRequest(BaseModel):
    host_a: dict | None = None
    host_b: dict | None = None
    question: str = Field(default='', max_length=2000)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(default=None, max_length=200)
    history: list[dict] = Field(default_factory=list, max_length=20)
    semantic_search: bool = False


def _topic_context(topic: str) -> tuple[list, dict]:
    """Live findings for one topic plus a one-line endpoint summary, as AI context, and the node-name labels."""
    report = inspect_topic(topic)
    if report.get('state') != 'ok':
        return [{'code': 'TOPIC_NOT_INSPECTED', 'severity': 'info',
                 'summary': f'Topic {topic} could not be inspected: {report.get("error") or report.get("state")}'[:240]}], {}
    endpoints = report.get('endpoints', [])
    kinds = ', '.join(f"{e['kind']} {e['node']} ({e['qos'].get('reliability', '?')}/{e['qos'].get('durability', '?')})"
                      for e in endpoints[:6])
    types = sorted({e.get('type') for e in endpoints if e.get('type')})
    summary = (f"Topic {topic} [{', '.join(types) or 'type unknown'}]: {report['publisher_count']} publisher(s), "
               f"{report['subscriber_count']} subscriber(s). {kinds}")
    return (report.get('findings', []) + [{'code': 'TOPIC_CONTEXT', 'severity': 'info', 'summary': summary[:240]}],
            node_labels(endpoints))


@app.post('/api/assistant/stream', tags=['assistant'])
def assistant_stream(payload: StreamRequest):
    """NDJSON stream: one `context` event (findings + documentation), then `meta`, `token`… and `done`/`error`.

    `host_a` defaults to a fresh local snapshot; `topic` adds that topic's live endpoints and QoS findings.
    Only sanitized findings, the question and documentation excerpts reach the model. For cloud providers node
    names, the hostname, IP addresses and home paths are masked first (the UI still sees the real values).
    """
    host_a = payload.host_a or collect()
    issues = sort_issues(transport_diagnose(host_a, payload.host_b))
    labels = {}
    if payload.topic:
        topic_issues, labels = _topic_context(payload.topic)
        issues = sort_issues(topic_issues) + issues
    query = ' '.join([payload.question[:400]] + [f"{i.get('code', '')} {i.get('summary', '')}" for i in issues[:16]])
    retrieved = hybrid_retrieve(query, semantic=payload.semantic_search)
    provider = payload.provider or llm.default_provider()
    for_model = mask_for_cloud(issues, labels) if llm.is_cloud(provider) else issues

    def events():
        yield json.dumps({'type': 'context', 'issues': issues, 'sources': retrieved['sources'],
                          'retrieval_mode': retrieved['mode'], 'health': health(host_a, issues)}) + '\n'
        for event in llm.explain_events(provider, for_model, payload.question, retrieved['sources'], payload.model,
                                        payload.history):
            yield json.dumps(event) + '\n'

    # X-Accel-Buffering stops reverse proxies from holding tokens back.
    return StreamingResponse(events(), media_type='application/x-ndjson', headers={'X-Accel-Buffering': 'no'})


class RvizPlanRequest(BaseModel):
    request: str = Field(max_length=1500)
    displays: list[dict] = Field(default_factory=list, max_length=60)
    fixed_frame: str | None = Field(default=None, max_length=200)
    frames: list[str] = Field(default_factory=list, max_length=500)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)
    history: list[dict] = Field(default_factory=list, max_length=10)


@app.post('/api/rviz/plan', tags=['rviz'])
def rviz_plan(payload: RvizPlanRequest):
    """AI plan of RViz display changes, validated against live topics, frames and the display catalog.

    The RViz panel previews the plan and applies it only on user confirmation. Sends display settings,
    topic names/types and TF frame names (no snapshots, hostnames or IPs) to the chosen model.
    """
    from . import rviz_agent
    try:
        return rviz_agent.plan(payload.request, payload.model_dump(), payload.provider, payload.model, payload.history)
    except rviz_agent.PlanError as e:
        raise HTTPException(400, str(e)) from e


@app.get('/api/rviz/catalog', tags=['rviz'])
def rviz_catalog():
    """Display types and settable properties the RViz planner knows."""
    from . import rviz_agent
    return {'actions': list(rviz_agent.ACTIONS), 'displays': rviz_agent.CATALOG}


class ProviderUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)
    make_default: bool = False


@app.get('/api/ai/providers', tags=['assistant'])
def ai_providers():
    """Provider status. Keys are never returned, only whether one is linked and its last 4 characters."""
    return llm.list_providers()


@app.put('/api/ai/providers/{provider}', tags=['assistant'])
def ai_provider_update(provider: str, data: ProviderUpdate):
    try:
        status = llm.update_provider(provider, api_key=data.api_key, model=data.model, base_url=data.base_url,
                                     make_default=data.make_default)
    except llm.ProviderError as e:
        raise HTTPException(400, str(e)) from e
    log.info('AI provider %s updated (key %s)', provider, 'changed' if data.api_key is not None else 'unchanged')
    return status


@app.delete('/api/ai/providers/{provider}/key', tags=['assistant'])
def ai_provider_remove_key(provider: str):
    try:
        return llm.remove_key(provider)
    except llm.ProviderError as e:
        raise HTTPException(400, str(e)) from e


@app.get('/api/ai/providers/{provider}/models', tags=['assistant'])
def ai_provider_models(provider: str, refresh: bool = False):
    """Models this provider offers: fetched live with the linked key (or from Ollama), else suggestions."""
    try:
        return llm.list_models(provider, refresh)
    except llm.ProviderError as e:
        raise HTTPException(400, str(e)) from e


@app.post('/api/ai/providers/{provider}/test', tags=['assistant'])
def ai_provider_test(provider: str):
    try:
        return llm.test_provider(provider)
    except llm.ProviderError as e:
        raise HTTPException(400, str(e)) from e


@app.post('/api/ai/warmup', tags=['assistant'])
def ai_warmup():
    """Preload the local Ollama model in the background so the first answer starts fast."""
    threading.Thread(target=llm.warm_up_ollama, daemon=True).start()
    return {'state': 'warming', 'model': llm.model_for('ollama')}


@app.get('/api/v06/fixtures', tags=['diagnose'])
def fixture_names():
    return {'fixtures': list_fixtures(), 'type': 'synthetic_offline_tests'}


@app.get('/api/v06/fixture/{name}', tags=['diagnose'])
def fixture_result(name: str):
    try:
        return run_fixture(name)
    except KeyError:
        raise HTTPException(404, 'Unknown fixture')


# C++ core: explicit endpoint inputs; no guessed remote environment.
from .cpp_bridge import check_endpoint


class CppEndpoints(BaseModel):
    publisher: dict
    subscriber: dict


@app.post('/api/v07/cpp-diagnose', tags=['native'])
def cpp_diagnose(payload: CppEndpoints):
    try:
        return check_endpoint(payload.publisher, payload.subscriber)
    except (ValueError, OSError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f'C++ diagnostics failed ({type(e).__name__})') from e


@app.post('/api/endpoint-check', tags=['diagnose'])
def endpoint_check(payload: CppEndpoints):
    """Check a hand-described publisher/subscriber pair. Native C++ core when built, else Python rules."""
    pub, sub = payload.publisher, payload.subscriber
    try:
        native = check_endpoint(pub, sub)
    except Exception as e:
        log.warning('Native endpoint check failed, using Python rules: %s', type(e).__name__)
        native = {'state': 'unavailable'}
    if native.get('state') != 'unavailable' and 'findings' in native:
        findings = [{'code': f.get('code'), 'severity': f.get('severity', 'error'), 'summary': f.get('evidence'),
                     'recommended_action': f.get('next_test')} for f in native['findings']]
        return {'engine': 'native C++ core', 'findings': findings}

    def as_core(ep):
        return {'domain_id': ep.get('domain') or None, 'topic': ep.get('topic'), 'type': ep.get('type'),
                'qos': {'reliability': str(ep.get('reliability', '')).lower(), 'durability': str(ep.get('durability', '')).lower()}}
    findings = [{'code': f['code'], 'severity': f['severity'], 'summary': f['conclusion'], 'evidence': f['evidence'],
                 'recommended_action': f['recommendation'], 'confidence': f['confidence']}
                for f in diagnose(as_core(pub), as_core(sub)) if f['code'] != 'NO_STATIC_MISMATCH']
    return {'engine': 'Python rules (native core not built)', 'findings': findings}


# BT visualization: executable events or explicitly labelled simulator.
from .bt_visualizer import run_trace


@app.get('/api/v08/bt/tree', tags=['native'])
def bt_tree():
    from .bt_visualizer import TREE, _binary
    return {'tree': TREE, 'native_available': _binary() is not None}


@app.post('/api/v08/bt/run', tags=['native'])
def bt_run(fault: bool = False):
    return run_trace(fault)


# Consolidated overview: read-only probes; local Docker metadata only.
from .enhanced import summary as enhanced_summary, inspect_shm, discover_local_containers, ollama_status


@app.get('/api/v09/overview', tags=['snapshot'])
def v09_overview():
    with ThreadPoolExecutor(max_workers=2) as pool:
        snap = pool.submit(collect)
        capabilities = pool.submit(lambda: enhanced_summary(None))
        s = snap.result()
        caps = capabilities.result()
    issues = sort_issues(transport_diagnose(s))
    return {'snapshot': s, 'summary': summarize(s), 'health': health(s, issues), 'issues': issues,
            'capabilities': caps, 'scope': 'local_collector_environment', 'read_only': True,
            'version': __version__}


@app.get('/api/v09/ollama', tags=['assistant'])
def v09_ollama():
    return ollama_status()


@app.get('/api/v09/environments', tags=['snapshot'])
def v09_environments():
    return discover_local_containers()


@app.get('/api/v09/shm', tags=['snapshot'])
def v09_shm():
    return inspect_shm()


@app.get('/legacy', response_class=HTMLResponse, include_in_schema=False)
def legacy_ui():
    return (HERE / 'index_legacy.html').read_text()
