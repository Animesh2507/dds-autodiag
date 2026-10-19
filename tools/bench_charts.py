#!/usr/bin/env python3
"""Draw the AI benchmark charts for the docs from a raw `dds-autodiag bench` JSON file.

    python3 tools/bench_charts.py docs/assets/benchmarks/2026-10-17.json

Writes inline SVGs to docs/assets/benchmarks/charts/. They carry no colours of their own: the docs stylesheet
(.ad-chart in extra.css) paints them for the light and dark theme. Every mark has a hover title, and the tables on the
benchmark page hold the same numbers.
"""
import json
import sys
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'docs' / 'assets' / 'benchmarks' / 'charts'
NAMES = {'claude-opus-5-5': 'Claude Opus 5.5', 'claude-sonnet-5-5': 'Claude Sonnet 5.5', 'claude-haiku-5-5': 'Claude Haiku 5.5'}
SCENARIOS = {'fix_qos': 'Fix two QoS problems', 'cloud_height': '3D cloud by height', 'tf_robot': 'TF + robot + QoS + cloud',
             'follow_up': 'Follow-up: bigger points', 'nav2_view': 'Show the Nav2 plan', 'light_weight': 'Light-weight cloud',
             'camera': 'Pick the camera topic', 'hide_rename': 'Hide and rename'}
SERIES = {'anthropic': 's1', 'qwen3:4b-instruct': 's2', 'qwen2.5:3b': 's3'}  # colour follows the model in every chart


def name(r):
    return NAMES.get(r['model'], r['model'])


def series(r):
    return SERIES.get(r['provider']) or SERIES.get(r['model'], 's1')


def bar(x, y, w, h, cls):
    """Horizontal bar: square at the baseline, 4 px rounded data end."""
    rad = min(4, w / 2, h / 2)
    return (f'<path class="mark {cls}" d="M{x:.1f},{y:.1f}h{w - rad:.1f}a{rad},{rad} 0 0 1 {rad},{rad}v{h - 2 * rad:.1f}'
            f'a{rad},{rad} 0 0 1 -{rad},{rad}h-{w - rad:.1f}z"/>')


def text(x, y, s, cls='t1', anchor='start', extra=''):
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}"{extra}>{escape(str(s))}</text>'


def svg(w, h, label, body):
    return (f'<svg class="ad-chart" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}" '
            f'xmlns="http://www.w3.org/2000/svg">' + ''.join(body) + '</svg>\n')


def axis(x0, x1, top, bottom, vmax, step, unit):
    out = []
    for v in range(0, int(vmax) + 1, step):
        x = x0 + (x1 - x0) * v / vmax
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}"/>')
        out.append(text(x, bottom + 16, f'{v}{unit if v == 0 else ""}', 't3 num small', 'middle'))
    out.append(f'<line class="base" x1="{x0}" y1="{top}" x2="{x0}" y2="{bottom}"/>')
    return out


def median_time(data):
    """One bar per model: median seconds per plan; checks passed alongside."""
    rows = sorted(data['results'], key=lambda r: (r['provider'] != 'anthropic', r['median_seconds']))
    x0, x1, vmax, top, gap = 190, 560, 35, 30, 30
    body, y = [], top
    for group, members in (('CLOUD API', [r for r in rows if r['provider'] == 'anthropic']),
                           ('LOCAL, CPU ONLY', [r for r in rows if r['provider'] != 'anthropic'])):
        body.append(text(0, y + 4, group, 't3 small caps'))
        y += 14
        for r in members:
            w = (x1 - x0) * r['median_seconds'] / vmax
            tip = (f"{name(r)}: median {r['median_seconds']} s per plan, {r['scenarios_passed']}/{r['scenarios']} scenarios, "
                   f"{r['checks_passed']}/{r['checks']} checks")
            body.append(f'<g class="m"><title>{escape(tip)}</title><rect class="hit" x="0" y="{y - 4}" width="720" height="{gap}"/>')
            body.append(text(0, y + 14, name(r)))
            body.append(bar(x0, y + 2, w, 18, series(r)))
            body.append(text(x0 + w + 6, y + 15, f"{r['median_seconds']:.1f} s", 't2 num'))
            body.append(text(720, y + 15, f"{r['checks_passed']}/{r['checks']}", 't1 num', 'end'))
            body.append('</g>')
            y += gap
        y += 10
    body.append(text(720, top - 12, 'checks passed', 't3 small', 'end'))
    body = axis(x0, x1, top - 4, y - 6, vmax, 10, ' s') + body
    body.append(text(x0, y + 26, 'median seconds per plan, over the 8 scenarios', 't3 small'))
    return svg(720, y + 34, 'Median time per plan by model', body)


def per_scenario(data):
    """Rows of scenarios: the range of the cloud models as one bar, each local model as a dot; a ring = checks failed."""
    claude = [r for r in data['results'] if r['provider'] == 'anthropic']
    local = [r for r in data['results'] if r['provider'] != 'anthropic']
    runs = {(r['model'], run['scenario']): run for r in data['results'] for run in r['runs']}
    ids = [s['id'] for s in data['scenarios']]
    x0, x1, vmax, top, gap = 190, 690, 75, 46, 30
    X = lambda v: x0 + (x1 - x0) * v / vmax
    body = []
    # legend: always present for more than one series
    lx = 0
    for cls, label, kind in (('s1', 'Claude Opus, Sonnet and Haiku (range)', 'bar'), ('s2', 'qwen3:4b-instruct', 'dot'),
                             ('s3', 'qwen2.5:3b', 'dot'), ('s3', 'a check failed', 'ring')):
        if kind == 'bar':
            body.append(f'<rect class="mark {cls}" x="{lx}" y="5" width="16" height="7" rx="3.5"/>')
        elif kind == 'dot':
            body.append(f'<circle class="mark {cls}" cx="{lx + 6}" cy="8.5" r="5"/>')
        else:
            body.append(f'<circle class="failed k3" cx="{lx + 6}" cy="8.5" r="4.5"/>')
        body.append(text(lx + 22, 13, label, 't2 small'))
        lx += 22 + len(label) * 6.4 + 22
    y = top
    for sid in ids:
        cl = [runs[(r['model'], sid)] for r in claude]
        lo, hi = min(c['seconds'] for c in cl), max(c['seconds'] for c in cl)
        tip = 'Claude: ' + ', '.join(f"{name(r).split()[1]} {runs[(r['model'], sid)]['seconds']:.1f} s" for r in claude)
        body.append(f'<g class="m"><title>{escape(SCENARIOS[sid] + " · " + tip)}</title>'
                    f'<rect class="hit" x="0" y="{y - 12}" width="{X(hi) + 12:.0f}" height="{gap}"/>')
        body.append(text(0, y + 4, SCENARIOS[sid]))
        body.append(f'<rect class="mark s1" x="{X(lo):.1f}" y="{y - 3.5}" width="{max(X(hi) - X(lo), 7):.1f}" height="7" rx="3.5"/></g>')
        for r in local:
            run = runs[(r['model'], sid)]
            ok = run['passed'] == run['total']
            cx = X(run['seconds'])
            tip = f"{SCENARIOS[sid]} · {r['model']}: {run['seconds']:.1f} s, {run['passed']}/{run['total']} checks"
            mark = (f'<circle class="mark ring {series(r)}" cx="{cx:.1f}" cy="{y}" r="5"/>' if ok
                    else f'<circle class="failed k{series(r)[1]}" cx="{cx:.1f}" cy="{y}" r="4.5"/>')
            body.append(f'<g class="m"><title>{escape(tip)}</title><circle class="hit" cx="{cx:.1f}" cy="{y}" r="12"/>{mark}')
            if not ok:
                body.append(text(cx + 10, y + 4, f"{run['passed']}/{run['total']} checks", 't2 small num'))
            body.append('</g>')
        y += gap
    body = axis(x0, x1, top - 14, y - 12, vmax, 15, ' s') + body
    body.append(text(x0, y + 22, 'seconds per plan, one run per scenario', 't3 small'))
    return svg(720, y + 30, 'Time per plan in each scenario', body)


def retrieval(data):
    """The local model with the full display catalog in the prompt versus retrieval: three small panels, one axis each."""
    base = data['full_prompt_baseline'][0]
    now = next(r for r in data['results'] if r['model'] == base['model'])
    panels = [('Median time per plan', 'median_seconds', lambda v: f'{v:.1f} s', None),
              ('Mean prompt tokens', 'mean_prompt_tokens', lambda v: f'{v:,.0f}', None),
              ('Checks passed', 'checks_passed', lambda v: f'{v:.0f}/{now["checks"]}', now['checks'])]
    pw, gapx, body = 220, 30, []
    for k, (title, key, fmt, cap) in enumerate(panels):
        px = k * (pw + gapx)
        vmax = cap or max(base[key], now[key]) * 1.18
        body.append(text(px, 14, title, 't1 small strong'))
        for j, (label, r, cls) in enumerate((('Full catalog', base, 'de'), ('Retrieval', now, 's2'))):
            y = 30 + j * 34
            w = (pw - 60) * r[key] / vmax
            tip = f"{label} prompt, {base['model']}: {title.lower()} {fmt(r[key])}"
            body.append(f'<g class="m"><title>{escape(tip)}</title><rect class="hit" x="{px}" y="{y - 2}" width="{pw}" height="30"/>')
            body.append(text(px, y + 10, label, 't2 small'))
            body.append(bar(px, y + 14, w, 12, cls))
            body.append(text(px + w + 6, y + 24, fmt(r[key]), 't1 small num'))
            body.append('</g>')
        body.append(f'<line class="base" x1="{px}" y1="40" x2="{px}" y2="98"/>')
    body.append(text(0, 122, f"{base['model']} on the CPU, same 8 scenarios; retrieval is the default now", 't3 small'))
    return svg(720, 128, 'Full prompt versus retrieval for the local model', body)


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'docs/assets/benchmarks/2026-10-17.json')
    data = json.loads(src.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    for file, draw in (('median-time.svg', median_time), ('per-scenario.svg', per_scenario), ('retrieval.svg', retrieval)):
        (OUT / file).write_text(draw(data))
        print('wrote', OUT / file)


if __name__ == '__main__':
    main()
