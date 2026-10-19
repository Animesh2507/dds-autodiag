#!/usr/bin/env python3
"""Exercise every dashboard/CLI function against the running lab collector."""
from __future__ import annotations
import json, os, sys, urllib.error, urllib.request

BASE = os.environ.get("AUTODIAG_URL", "http://127.0.0.1:18087")
TOKEN = os.environ.get("AUTODIAG_AGENT_TOKEN", "lab-collector-token")
PEER = os.environ.get("AUTODIAG_PEER", "http://127.0.0.1:18088")
SNAPS = os.path.expanduser("~/autodiag-lab")


def req(method, path, body=None, headers=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    h = {"Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
        if not raw:
            return resp.status, None
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, raw.decode("utf-8", "replace")


def ok(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"{mark:4}  {name:<42} {detail}")
    return 0 if cond else 1


def main():
    fails = 0
    st, hz = req("GET", "/api/healthz")
    fails += ok("service healthz", st == 200 and hz.get("status") == "ok", hz)
    st, ver = req("GET", "/api/version")
    fails += ok("service version", st == 200 and ver.get("version"), ver.get("version"))
    st, home = req("GET", "/")
    fails += ok("ui console shell", st == 200 and "Event log" in str(home))
    st, _ = req("GET", "/legacy")
    fails += ok("ui legacy still served", st == 200)
    st, _ = req("GET", "/api/docs")
    fails += ok("openapi /api/docs", st == 200)

    st, ov = req("GET", "/api/v09/overview")
    issues = [i.get("code") for i in (ov or {}).get("issues", [])] if isinstance(ov, dict) else []
    fails += ok("overview snapshot", st == 200 and isinstance(ov, dict), f"issues={issues}")

    st, topics = req("GET", "/api/topics")
    names = [t["topic"] for t in (topics or {}).get("topics", [])]
    need = ["/lab/scan", "/lab/map", "/lab/odom", "/lab/camera", "/lab/status", "/lab/cmd_vel"]
    fails += ok("topics discover lab graph", st == 200 and all(t in names for t in need),
                f"{len(names)} topics: {', '.join(t for t in need if t in names)}")

    def inspect(topic):
        st, body = req("GET", f"/api/topic-inspect?topic={topic}")
        codes = [f["code"] for f in (body or {}).get("findings", [])] if isinstance(body, dict) else []
        return st, body, codes

    st, scan, codes = inspect("/lab/scan")
    fails += ok("inspect scan reliability mismatch", st == 200 and "RELIABILITY_MISMATCH" in codes, codes)
    st, cam, codes = inspect("/lab/camera")
    fails += ok("inspect camera reliability mismatch", st == 200 and "RELIABILITY_MISMATCH" in codes, codes)
    st, mp, codes = inspect("/lab/map")
    fails += ok("inspect map latched/volatile", st == 200 and "LATCHED_DATA_VOLATILE_SUBSCRIBER" in codes, codes)
    st, odom, codes = inspect("/lab/odom")
    fails += ok("inspect odom compatible (no QoS fault)", st == 200 and not codes, codes)
    st, status, codes = inspect("/lab/status")
    fails += ok("inspect status type mismatch", st == 200 and "TYPE_MISMATCH" in codes, codes)
    st, pose, codes = inspect("/lab/amcl_pose")
    fails += ok("inspect waiting /lab/amcl_pose", st == 200 and pose.get("publisher_count", 1) == 0,
                f"pubs={pose.get('publisher_count')} subs={pose.get('subscriber_count')} {codes}")

    st, sample = req("GET", "/api/topic-sample?topic=/lab/odom&timeout=5&reliability=reliable")
    fails += ok("sample odom reliable (should arrive)", st == 200 and sample.get("state") == "ok",
                sample.get("state"))
    st, sample = req("GET", "/api/topic-sample?topic=/lab/scan&timeout=3&reliability=reliable")
    fails += ok("sample scan reliable (should time out)", st == 200 and sample.get("state") == "timeout",
                sample.get("state"))
    st, sample = req("GET", "/api/topic-sample?topic=/lab/scan&timeout=5&reliability=best_effort")
    fails += ok("sample scan best_effort (should arrive)", st == 200 and sample.get("state") == "ok",
                sample.get("state"))

    st, graph = req("GET", "/api/graph")
    edges = (graph or {}).get("edges", []) if isinstance(graph, dict) else []
    waiting = (graph or {}).get("waiting", []) if isinstance(graph, dict) else []
    red = [e for e in edges if (e.get("severity") or e.get("state")) in ("error", "problem", "red")]
    # graph edge shape may use findings
    bad = [e for e in edges if e.get("findings") or e.get("severity") in ("error", "warning")]
    fails += ok("graph built", st == 200 and graph.get("state") == "ok",
                f"edges={len(edges)} waiting={len(waiting)} with_findings={len(bad)}")

    st, selft = req("GET", "/api/selftest")
    fails += ok("tools selftest", st == 200 and selft.get("ok") is True,
                f"{selft.get('passed')}/{selft.get('total')}")

    st, rag = req("GET", "/api/rag/status")
    fails += ok("assistant rag status", st == 200, rag.get("state") if isinstance(rag, dict) else rag)

    snap = req("GET", "/api/snapshot")[1]
    question = {"host_a": snap,
                "question": "Why does a reliable subscriber get nothing from a best-effort lidar on /lab/scan?",
                "use_local_ai": False}
    st, expl = req("POST", "/api/rag/explain", question)
    srcs = (expl or {}).get("sources", []) if isinstance(expl, dict) else []
    fails += ok("assistant docs retrieval", st == 200 and len(srcs) >= 1, f"{len(srcs)} sources")

    st, prov = req("GET", "/api/ai/providers")
    fails += ok("about ai providers", st == 200, list((prov or {}).keys())[:6] if isinstance(prov, dict) else "")

    # Hosts: live peer (laptop on 18088) and file peer
    st, live = req("POST", "/api/remote-compare",
                   {"url": PEER, "token": TOKEN})
    live_codes = [i.get("code") for i in (live or {}).get("issues", [])] if isinstance(live, dict) else []
    fails += ok("hosts live compare laptop", st == 200 and "RMW_MISMATCH" in live_codes, live_codes)

    laptop = os.path.join(SNAPS, "laptop.json")
    isolated = os.path.join(SNAPS, "isolated.json")
    if os.path.isfile(laptop) and os.path.isfile(isolated):
        local = req("GET", "/api/snapshot")[1]
        with open(laptop) as f:
            peer = json.load(f)
        st, cmp = req("POST", "/api/compare", {"host_a": local, "host_b": peer})
        codes = [i.get("code") for i in (cmp or {}).get("issues", [])]
        fails += ok("hosts file compare laptop", st == 200 and "RMW_MISMATCH" in codes, codes)
        with open(isolated) as f:
            peer = json.load(f)
        st, cmp = req("POST", "/api/compare", {"host_a": local, "host_b": peer})
        codes = [i.get("code") for i in (cmp or {}).get("issues", [])]
        fails += ok("hosts file compare isolated", st == 200 and "DOMAIN_MISMATCH" in codes, codes)
    else:
        fails += ok("hosts file snapshots present", False, SNAPS)

    st, docker = req("GET", "/api/v09/environments")
    fails += ok("hosts docker scan (optional)", st == 200, (docker or {}).get("state") if isinstance(docker, dict) else "")

    st, shm = req("GET", "/api/v09/shm")
    fails += ok("transport shm observations", st == 200, (shm or {}).get("state") if isinstance(shm, dict) else "")

    st, report = req("POST", "/api/report", {"host_a": req("GET", "/api/snapshot")[1]})
    fails += ok("export markdown report", st == 200 and "DDS AutoDiag" in str(report), "")

    print()
    print("failed" if fails else "all feature checks passed", f"({fails} failures)")
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.reason, e.read()[:300])
        sys.exit(1)
    except Exception as e:
        print("error:", type(e).__name__, e)
        sys.exit(1)
