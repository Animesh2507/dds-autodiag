"""AI planner for RViz2 configuration changes.

The model only *proposes* a short list of actions from a fixed vocabulary. Every action is
validated here against the display catalog, the panel's current displays, live topics and
TF frames; the RViz panel shows the plan and applies it only when the user clicks Apply.
This changes RViz visualization only - never the robot, ROS graph or DDS configuration.
"""
from __future__ import annotations
import json
import re
import time

from . import llm
from .live import topic_list

ACTIONS = ('add_display', 'remove_display', 'set_topic', 'set_property', 'set_enabled',
           'rename_display', 'set_fixed_frame')
MAX_ACTIONS = 20

QOS_PROPS = {
    'Topic/Depth': 'integer queue depth, e.g. 1 for lowest latency',
    'Topic/Reliability Policy': 'Reliable | Best Effort | System Default',
    'Topic/Durability Policy': 'Volatile | Transient Local | System Default',
    'Topic/History Policy': 'Keep Last | Keep All | System Default',
}
CLOUD_PROPS = {
    'Style': 'Points | Squares | Flat Squares | Spheres | Boxes',
    'Size (m)': 'point size in metres, e.g. 0.03',
    'Size (Pixels)': 'point size in pixels (Style=Points), e.g. 3',
    'Alpha': '0..1 transparency',
    'Decay Time': 'seconds to keep old clouds, 0 = only latest',
    'Color Transformer': 'Intensity | AxisColor | FlatColor | RGB8 | RGBF32 | MONO8',
    'Axis': 'X | Y | Z (with Color Transformer AxisColor; Z = colour by height)',
    'Color': 'r; g; b with 0-255 values (with FlatColor)',
    'Use rainbow': 'true | false',
    'Selectable': 'true | false (false is faster for big clouds)',
    **QOS_PROPS,
}

# Display catalog: RViz2 Jazzy rviz_default_plugins class ids, the message types they accept and
# the properties a plan may set. Property names must match RViz exactly.
CATALOG = {
    'PointCloud2': {'class_id': 'rviz_default_plugins/PointCloud2', 'types': ['sensor_msgs/msg/PointCloud2'], 'props': CLOUD_PROPS},
    'PointCloud': {'class_id': 'rviz_default_plugins/PointCloud', 'types': ['sensor_msgs/msg/PointCloud'], 'props': CLOUD_PROPS},
    'LaserScan': {'class_id': 'rviz_default_plugins/LaserScan', 'types': ['sensor_msgs/msg/LaserScan'], 'props': CLOUD_PROPS},
    'Image': {'class_id': 'rviz_default_plugins/Image', 'types': ['sensor_msgs/msg/Image'],
              'props': {'Normalize Range': 'true | false', **QOS_PROPS}},
    'Camera': {'class_id': 'rviz_default_plugins/Camera', 'types': ['sensor_msgs/msg/Image'],
               'props': {'Overlay Alpha': '0..1', 'Zoom Factor': 'e.g. 1', **QOS_PROPS}},
    'DepthCloud': {'class_id': 'rviz_default_plugins/DepthCloud', 'types': ['sensor_msgs/msg/Image'],
                   'topic_prop': 'Depth Map Topic', 'props': {}},
    'Map': {'class_id': 'rviz_default_plugins/Map', 'types': ['nav_msgs/msg/OccupancyGrid'],
            'props': {'Alpha': '0..1', 'Color Scheme': 'map | costmap | raw', 'Draw Behind': 'true | false',
                      **QOS_PROPS}},
    'Path': {'class_id': 'rviz_default_plugins/Path', 'types': ['nav_msgs/msg/Path'],
             'props': {'Color': 'r; g; b', 'Alpha': '0..1', 'Line Style': 'Lines | Billboards',
                       'Line Width': 'metres (Billboards)', 'Buffer Length': 'number of paths kept', **QOS_PROPS}},
    'Odometry': {'class_id': 'rviz_default_plugins/Odometry', 'types': ['nav_msgs/msg/Odometry'],
                 'props': {'Keep': 'number of arrows kept', 'Shape': 'Arrow | Axes', **QOS_PROPS}},
    'Pose': {'class_id': 'rviz_default_plugins/Pose', 'types': ['geometry_msgs/msg/PoseStamped'],
             'props': {'Shape': 'Arrow | Axes', 'Color': 'r; g; b', 'Alpha': '0..1', **QOS_PROPS}},
    'PoseWithCovariance': {'class_id': 'rviz_default_plugins/PoseWithCovariance',
                           'types': ['geometry_msgs/msg/PoseWithCovarianceStamped'], 'props': QOS_PROPS},
    'PoseArray': {'class_id': 'rviz_default_plugins/PoseArray', 'types': ['geometry_msgs/msg/PoseArray'],
                  'props': {'Shape': 'Arrow (Flat) | Arrow (3D) | Axes', 'Color': 'r; g; b', **QOS_PROPS}},
    'PointStamped': {'class_id': 'rviz_default_plugins/PointStamped', 'types': ['geometry_msgs/msg/PointStamped'],
                     'props': {'Color': 'r; g; b', 'Radius': 'metres', **QOS_PROPS}},
    'Polygon': {'class_id': 'rviz_default_plugins/Polygon', 'types': ['geometry_msgs/msg/PolygonStamped'],
                'props': {'Color': 'r; g; b', 'Alpha': '0..1', **QOS_PROPS}},
    'Marker': {'class_id': 'rviz_default_plugins/Marker', 'types': ['visualization_msgs/msg/Marker'], 'props': QOS_PROPS},
    'MarkerArray': {'class_id': 'rviz_default_plugins/MarkerArray', 'types': ['visualization_msgs/msg/MarkerArray'],
                    'props': QOS_PROPS},
    'Range': {'class_id': 'rviz_default_plugins/Range', 'types': ['sensor_msgs/msg/Range'],
              'props': {'Color': 'r; g; b', 'Alpha': '0..1', **QOS_PROPS}},
    'GridCells': {'class_id': 'rviz_default_plugins/GridCells', 'types': ['nav_msgs/msg/GridCells'], 'props': QOS_PROPS},
    'TwistStamped': {'class_id': 'rviz_default_plugins/TwistStamped', 'types': ['geometry_msgs/msg/TwistStamped'],
                     'props': QOS_PROPS},
    'Wrench': {'class_id': 'rviz_default_plugins/Wrench', 'types': ['geometry_msgs/msg/WrenchStamped'], 'props': QOS_PROPS},
    'TF': {'class_id': 'rviz_default_plugins/TF', 'types': [], 'topic_prop': None,
           'props': {'Show Names': 'true | false', 'Show Axes': 'true | false', 'Show Arrows': 'true | false',
                     'Marker Scale': 'e.g. 1', 'Update Interval': 'seconds'}},
    'Grid': {'class_id': 'rviz_default_plugins/Grid', 'types': [], 'topic_prop': None,
             'props': {'Reference Frame': 'frame name or <Fixed Frame>', 'Plane Cell Count': 'e.g. 10',
                       'Cell Size': 'metres', 'Color': 'r; g; b', 'Alpha': '0..1'}},
    'Axes': {'class_id': 'rviz_default_plugins/Axes', 'types': [], 'topic_prop': None,
             'props': {'Reference Frame': 'frame name', 'Length': 'metres', 'Radius': 'metres'}},
    'RobotModel': {'class_id': 'rviz_default_plugins/RobotModel', 'types': ['std_msgs/msg/String'],
                   'topic_prop': 'Description Topic',
                   'props': {'Alpha': '0..1', 'Visual Enabled': 'true | false', 'Collision Enabled': 'true | false'}},
}
BY_CLASS = {v['class_id'].lower(): k for k, v in CATALOG.items()}
# Always offered, even before anything publishes (users set up RViz ahead of their sensors).
COMMON_TYPES = ('PointCloud2', 'LaserScan', 'Image', 'Camera', 'Map', 'Odometry', 'Path', 'MarkerArray', 'RobotModel')

# Conventional ROS topic names, used when a display is added before anything publishes.
DEFAULT_TOPICS = {
    'LaserScan': '/scan', 'PointCloud2': '/points', 'PointCloud': '/points', 'Image': '/camera/image_raw',
    'Camera': '/camera/image_raw', 'DepthCloud': '/camera/depth/image_raw', 'Map': '/map', 'Path': '/plan',
    'Odometry': '/odom', 'Pose': '/goal_pose', 'PoseWithCovariance': '/amcl_pose', 'PoseArray': '/particle_cloud',
    'PointStamped': '/clicked_point', 'Polygon': '/polygon', 'Marker': '/visualization_marker',
    'MarkerArray': '/visualization_marker_array', 'Range': '/range', 'GridCells': '/grid_cells',
    'TwistStamped': '/cmd_vel', 'Wrench': '/wrench', 'RobotModel': '/robot_description',
}

SYSTEM = (
    "You configure RViz2 displays for a ROS 2 user. Turn the request into a short list of actions using ONLY "
    "the action names, display types, property names, topics and frames given in the context. Rules:\n"
    "- Prefer modifying an existing display over adding a duplicate.\n"
    "- add_display needs display_type and topic (topic empty for TF, Grid, Axes); set name to a short label.\n"
    "- For properties of a display you add in the same plan, use set_property with display = that new name.\n"
    "- set_property: property is the exact name (QoS uses Topic/Depth, Topic/Reliability Policy...), value is a "
    "string (true/false for booleans, plain numbers, enum text exactly as listed, colors as 'r; g; b').\n"
    "- set_enabled: value true or false. rename_display: value is the new name. set_fixed_frame: frame.\n"
    "- Only use topics whose message type matches the display type. If something cannot be done in RViz "
    "(e.g. true point-cloud downsampling needs a filter node such as pcl_ros VoxelGrid; RViz can only reduce "
    "load with Decay Time 0, Topic/Depth 1, Best Effort, Style Points, smaller Size), say so in notes.\n"
    "- If no matching topic is publishing, STILL add the requested display using its conventional topic name "
    "(LaserScan /scan, PointCloud2 /points, Image /camera/image_raw, Map /map, Odometry /odom, MarkerArray "
    "/visualization_marker_array); it shows data once a publisher appears. Never return an empty plan for that.\n"
    "- When the user names a frame to view in (e.g. 'in base_link'), add set_fixed_frame.\n"
    "- To colour a cloud by height: Color Transformer AxisColor and Axis Z. A display that shows nothing "
    "should be fixed (topic, QoS), not disabled, unless the user asks to hide it.\n"
    "- Use the earlier conversation to resolve follow-ups such as 'make it bigger', 'the other topic' or "
    "'do what you suggested'; but the CONTEXT is the current truth. Do not repeat changes already applied.\n"
    "- Unused fields are empty strings. Keep summary to one sentence. No more than 12 actions.")

PLAN_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['summary', 'actions', 'notes'],
    'properties': {
        'summary': {'type': 'string'},
        'notes': {'type': 'array', 'items': {'type': 'string'}},
        'actions': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['action', 'display', 'display_type', 'topic', 'property', 'value', 'frame'],
            'properties': {
                'action': {'type': 'string', 'enum': list(ACTIONS)},
                'display': {'type': 'string'}, 'display_type': {'type': 'string'}, 'topic': {'type': 'string'},
                'property': {'type': 'string'}, 'value': {'type': 'string'}, 'frame': {'type': 'string'}}}},
    },
}


class PlanError(Exception):
    pass


_topics_cache: dict = {'at': 0.0, 'value': None}


def _discover() -> dict | None:
    """One discovery pass over the whole graph that waits until every node's endpoints are in (see graph.py).

    Per-topic `ros2 topic info` calls can miss a publisher under load, which made plans skip QoS fixes."""
    from .graph import discover_all
    return discover_all()


def _snapshot_inspector(snapshot: dict | None):
    if snapshot is None:
        return None
    return lambda topic: {'state': 'ok', 'endpoints': snapshot.get(topic, [])}


def _live_topics(snapshot: dict | None = None) -> dict[str, str]:
    """topic -> type, cached briefly (each query spins up a ROS node)."""
    if snapshot is not None:
        return {t: eps[0]['type'] for t, eps in snapshot.items() if eps and eps[0].get('type')}
    if _topics_cache['value'] is None or time.monotonic() - _topics_cache['at'] > 15:
        result = topic_list()
        _topics_cache.update(at=time.monotonic(),
                             value={t['topic']: t['type'] for t in result.get('topics', [])} if result.get('state') == 'ok' else {})
    return dict(_topics_cache['value'])


def display_type_name(value: str) -> str | None:
    """Accept 'PointCloud2', 'pointcloud2' or 'rviz_default_plugins/PointCloud2'."""
    v = (value or '').strip()
    if v.lower() in BY_CLASS:
        return BY_CLASS[v.lower()]
    for name in CATALOG:
        if name.lower() == v.lower():
            return name
    return None


def _short(msg_type: str) -> str:
    return msg_type.rsplit('/', 1)[-1]


def _fixed_frame_fix(state: dict) -> str | None:
    """A frame to switch to when the Fixed Frame is not in the TF tree (then RViz shows nothing at all)."""
    frames, fixed = state.get('frames') or [], state.get('fixed_frame')
    if not frames or not fixed or fixed in frames:
        return None
    return next((f for f in ('map', 'odom', 'world', 'base_link') if f in frames), frames[0])


def _context(state: dict, topics: dict[str, str], qos: dict[str, dict]) -> str:
    """Compact plain-text context: small local models read this far faster than JSON."""
    lines = [f"Fixed frame: {state.get('fixed_frame') or 'unknown'}",
             'TF frames: ' + (', '.join(state.get('frames', [])[:60]) or 'unknown')]
    better = _fixed_frame_fix(state)
    if better:
        lines.append(f'Diagnosed problem: the Fixed Frame "{state.get("fixed_frame")}" does not exist in the TF tree, so '
                     f'RViz can show nothing -> set_fixed_frame to "{better}".')
    lines.append('Current displays:')
    used_types = set()
    for d in state.get('displays', [])[:40]:
        dtype = display_type_name(d.get('type', '')) or d.get('type', '?')
        used_types.add(dtype)
        props = '; '.join(f'{k}={v}' for k, v in list((d.get('properties') or {}).items())[:25])
        fact = qos.get(d.get('name', ''), {}).get('fact', '')
        lines.append(f'- "{d.get("name")}" ({dtype}) {"enabled" if d.get("enabled") else "disabled"}, '
                     f'status {d.get("status") or "?"}, topic {d.get("topic") or "-"}'
                     + (f'; {fact}' if fact else '') + (f'; {props}' if props else ''))
    if not state.get('displays'):
        lines.append('- (none)')
    lines.append('Topics: ' + (', '.join(f'{t} [{_short(ty)}]' for t, ty in sorted(topics.items())[:150]) or 'none visible'))
    present = {ty for ty in topics.values()}
    lines.append('Display types you may add or configure (message type; settable properties):')
    for name, c in CATALOG.items():
        if name in used_types or name in COMMON_TYPES or not c['types'] or present.intersection(c['types']):
            props = '; '.join(f'{k} ({v})' for k, v in c['props'].items())
            lines.append(f"- {name}: {', '.join(_short(t) for t in c['types']) or 'no topic'}; {props or 'no common settings'}")
    hints = [h['fact'] for h in qos.values() if h.get('fix')]
    if hints:
        lines.append('Diagnosed problems (fix these by changing the display, do not disable it): ' + ' '.join(hints))
    return '\n'.join(lines)


def _topic_qos(state: dict, inspect=None) -> dict[str, dict]:
    """Inspect the topics of current displays: offered publisher QoS vs. what the display requests."""
    from concurrent.futures import ThreadPoolExecutor
    from .live import inspect_topic
    inspect_topic = inspect or inspect_topic
    targets = [d for d in state.get('displays', []) if str(d.get('topic', '')).startswith('/')][:6]
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        reports = list(pool.map(lambda d: inspect_topic(d['topic']), targets))
    out = {}
    for d, rep in zip(targets, reports):
        if rep.get('state') != 'ok':
            continue
        pubs = [e for e in rep.get('endpoints', []) if e.get('kind') == 'publisher']
        name, props = d.get('name', ''), d.get('properties') or {}
        if not pubs:
            out[name] = {'fact': f'no publisher on {d["topic"]} right now'}
            continue
        offered_rel = {str(e['qos'].get('reliability', '')).upper() for e in pubs}
        offered_dur = {str(e['qos'].get('durability', '')).upper() for e in pubs}
        fact = f"publishers on {d['topic']} offer {'/'.join(sorted(offered_rel))} reliability, {'/'.join(sorted(offered_dur))} durability"
        fix = []
        if any('BEST_EFFORT' in r for r in offered_rel) and str(props.get('Topic/Reliability Policy', '')).lower() == 'reliable':
            fix.append(('Topic/Reliability Policy', 'Best Effort'))
            fact += f'; "{name}" requests Reliable, so it receives nothing -> set Topic/Reliability Policy to Best Effort'
        if all('VOLATILE' in r for r in offered_dur) and str(props.get('Topic/Durability Policy', '')).lower() == 'transient local':
            fix.append(('Topic/Durability Policy', 'Volatile'))
            fact += f'; "{name}" requests Transient Local from a Volatile publisher -> set Topic/Durability Policy to Volatile'
        if all('TRANSIENT_LOCAL' in r for r in offered_dur) and str(props.get('Topic/Durability Policy', '')).lower() == 'volatile':
            fix.append(('Topic/Durability Policy', 'Transient Local'))
            fact += (f'; "{name}" requests Volatile from a latched (Transient Local) publisher, so it misses data published '
                     'before it started -> set Topic/Durability Policy to Transient Local')
        out[name] = {'fact': fact, 'fix': fix}
    return out


def _added_display_qos(actions: list, inspect=None) -> dict[str, dict]:
    """QoS fixes for displays added in this plan: RViz creates them Reliable and Volatile, which receives nothing
    from a best-effort publisher (most lidar and camera drivers) and misses latched data such as a map."""
    from concurrent.futures import ThreadPoolExecutor
    from .live import inspect_topic
    inspect_topic = inspect or inspect_topic
    targets = [a for a in actions if a['action'] == 'add_display' and a.get('topic') and not a.get('not_publishing')
               and a.get('topic_property', 'Topic') == 'Topic'][:6]
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        reports = list(pool.map(lambda a: inspect_topic(a['topic']), targets))
    out = {}
    for a, rep in zip(targets, reports):
        pubs = [e for e in rep.get('endpoints', []) if e.get('kind') == 'publisher'] if rep.get('state') == 'ok' else []
        if not pubs:
            continue
        reliability = {str(e['qos'].get('reliability', '')).upper() for e in pubs}
        durability = {str(e['qos'].get('durability', '')).upper() for e in pubs}
        fix = []
        if any('BEST_EFFORT' in r for r in reliability):
            fix.append(('Topic/Reliability Policy', 'Best Effort'))
        if all('TRANSIENT_LOCAL' in d for d in durability):
            fix.append(('Topic/Durability Policy', 'Transient Local'))
        if fix:
            out[a['display']] = {'fact': f'publishers on {a["topic"]} offer {"/".join(sorted(reliability))} reliability, '
                                         f'{"/".join(sorted(durability))} durability', 'fix': fix}
    return out


def _loose(name: str) -> str:
    """'laser_scan', 'Laser Scan' and 'LaserScan' all match."""
    return ''.join(ch for ch in name.lower() if ch.isalnum())


def validate(raw: dict, state: dict, topics: dict[str, str]) -> dict:
    """Normalize the model's plan and reject anything unsafe or impossible, with a reason."""
    existing = {str(d.get('name', '')).lower(): d for d in state.get('displays', [])}
    loose = {_loose(name): name for name in existing}
    frames = set(state.get('frames') or [])
    added: dict[str, str] = {}  # lower(name) -> display type
    actions, rejected, notes = [], [], [str(n)[:300] for n in (raw.get('notes') or [])][:6]

    def reject(a, reason):
        rejected.append({'action': a, 'reason': reason})

    for a in (raw.get('actions') or [])[:MAX_ACTIONS]:
        if not isinstance(a, dict):
            continue
        a = {k: str(a.get(k) or '').strip()[:200] for k in ('action', 'display', 'display_type', 'topic', 'property', 'value', 'frame')}
        kind = a['action']
        target = a['display'].lower()
        if target not in existing and target not in added:
            target = loose.get(_loose(target), next((n for n in added if _loose(n) == _loose(target)), target))
        target_type = display_type_name(existing[target].get('type', '')) if target in existing else added.get(target)
        if kind not in ACTIONS:
            reject(a, f'Unknown action "{kind}".')
            continue
        if kind == 'add_display':
            dtype = display_type_name(a['display_type'])
            if not dtype:
                reject(a, f'Unknown display type "{a["display_type"]}".')
                continue
            entry = CATALOG[dtype]
            waiting = False
            if entry.get('topic_prop', 'Topic') and entry['types']:
                if a['topic'] and not a['topic'].startswith('/'):
                    a['topic'] = '/' + a['topic']
                if not a['topic']:
                    # Prefer a live topic of the right type, else the conventional name.
                    live = sorted(t for t, ty in topics.items() if ty in entry['types'])
                    a['topic'] = live[0] if len(live) == 1 else DEFAULT_TOPICS.get(dtype, '')
                if a['topic'] in topics and topics[a['topic']] not in entry['types']:
                    reject(a, f'{a["topic"]} is {topics[a["topic"]]}, but {dtype} shows {", ".join(entry["types"])}.')
                    continue
                waiting = bool(a['topic']) and a['topic'] not in topics
            name = a['display'] or (dtype + (' ' + a['topic'] if a['topic'] else ''))
            if name.lower() in existing or name.lower() in added:
                name = f'{name} ({len(added) + 2})'
            added[name.lower()] = dtype
            actions.append({**a, 'action': kind, 'display': name, 'display_type': dtype,
                            'class_id': entry['class_id'], 'topic_property': entry.get('topic_prop', 'Topic') or '',
                            'not_publishing': waiting,
                            'description': f'Add {dtype} display "{name}"' + (f' on {a["topic"]}' if a['topic'] else '')
                            + (' (not publishing yet)' if waiting else '')})
            continue
        if kind == 'set_fixed_frame':
            if not a['frame']:
                reject(a, 'No frame given.')
                continue
            if frames and a['frame'] not in frames:
                notes.append(f'Frame "{a["frame"]}" is not in the current TF tree; RViz will show a transform error until it appears.')
            actions.append({**a, 'description': f'Set Fixed Frame to {a["frame"]}'})
            continue
        if target not in existing and target not in added:
            reject(a, f'No display named "{a["display"]}".')
            continue
        display_name = existing[target]['name'] if target in existing else next(
            act['display'] for act in actions if act['action'] == 'add_display' and act['display'].lower() == target)
        a['display'] = display_name
        a['display_type'] = target_type or ''
        if kind == 'remove_display':
            actions.append({**a, 'description': f'Remove display "{display_name}"'})
        elif kind == 'set_topic':
            entry = CATALOG.get(target_type or '', {})
            if not a['topic']:
                reject(a, 'No topic given.')
                continue
            if not a['topic'].startswith('/'):
                a['topic'] = '/' + a['topic']
            if entry.get('types') and a['topic'] in topics and topics[a['topic']] not in entry['types']:
                reject(a, f'{a["topic"]} is {topics[a["topic"]]}, which "{display_name}" cannot show.')
                continue
            waiting = a['topic'] not in topics
            actions.append({**a, 'topic_property': entry.get('topic_prop', 'Topic') or 'Topic', 'not_publishing': waiting,
                            'description': f'Set topic of "{display_name}" to {a["topic"]}'
                            + (' (not publishing yet)' if waiting else '')})
        elif kind == 'set_property':
            if not a['property']:
                reject(a, 'No property given.')
                continue
            known = (existing.get(target) or {}).get('properties') or {}
            catalog_props = CATALOG.get(target_type or '', {}).get('props', {})
            # Models sometimes nest a top-level setting ("Color Transformer/Axis" -> "Axis").
            if '/' in a['property'] and a['property'] not in catalog_props and a['property'] not in known:
                leaf = a['property'].rsplit('/', 1)[-1].strip()
                if leaf in catalog_props or leaf in known:
                    a['property'] = leaf
            if known and a['property'] not in known and a['property'] not in catalog_props:
                reject(a, f'"{display_name}" has no property "{a["property"]}".')
                continue
            actions.append({**a, 'description': f'Set {a["property"]} of "{display_name}" to {a["value"]}'})
        elif kind == 'set_enabled':
            on = a['value'].lower() in ('true', '1', 'yes', 'on', 'enable', 'enabled')
            actions.append({**a, 'value': 'true' if on else 'false',
                            'description': f'{"Enable" if on else "Disable"} display "{display_name}"'})
        elif kind == 'rename_display':
            if not a['value']:
                reject(a, 'No new name given.')
                continue
            actions.append({**a, 'description': f'Rename "{display_name}" to "{a["value"]}"'})
    if any(act.get('not_publishing') for act in actions):
        notes.append('Displays marked "not publishing yet" stay empty until something publishes on that topic; '
                     'change the topic in the Displays panel if your robot uses another name.')
    return {'summary': str(raw.get('summary', ''))[:400], 'actions': actions, 'rejected': rejected,
            'notes': list(dict.fromkeys(notes))}


_CLOUD_TYPES = ('PointCloud2', 'PointCloud', 'LaserScan')


def _complete(result: dict, qos: dict, request: str = '', state: dict | None = None) -> None:
    """Deterministic additions the model tends to miss; each is labelled so the user can see why."""
    actions = result['actions']
    types = {a['display'].lower(): a['display_type'] for a in actions if a['action'] == 'add_display'}

    def has(display, prop):
        return any(a['action'] == 'set_property' and a['display'].lower() == display.lower() and a['property'] == prop
                   for a in actions)

    extra = []
    for a in actions:
        if a['action'] != 'set_property':
            continue
        dtype = types.get(a['display'].lower()) or a.get('display_type', '')
        needed = {'Axis': 'AxisColor', 'Color': 'FlatColor'}.get(a['property'])
        if needed and dtype in _CLOUD_TYPES and not has(a['display'], 'Color Transformer'):
            extra.append({**a, 'property': 'Color Transformer', 'value': needed, 'auto': True,
                          'description': f'Set Color Transformer of "{a["display"]}" to {needed} (needed for {a["property"]})'})
    for name, info in qos.items():
        for prop, value in info.get('fix') or []:
            if not has(name, prop):
                extra.append({'action': 'set_property', 'display': name, 'display_type': '', 'topic': '', 'property': prop,
                              'value': value, 'frame': '', 'auto': True,
                              'description': f'Set {prop} of "{name}" to {value} (AutoDiag QoS fix)'})
                # The diagnosed fix supersedes the model disabling that display.
                for a in actions:
                    if a['action'] == 'set_enabled' and a['display'] == name and a['value'] == 'false':
                        a['unchecked'] = True
    # Insert each Color Transformer right before the property that needs it.
    for e in extra:
        if e['property'] == 'Color Transformer':
            index = next(i for i, a in enumerate(actions) if a['display'] == e['display'] and a['action'] == 'set_property')
            actions.insert(index, e)
        else:
            actions.append(e)
    state = state or {}
    # A Fixed Frame missing from the TF tree blanks every display; fix it even if the model did not.
    better = _fixed_frame_fix(state)
    if better and not any(a['action'] == 'set_fixed_frame' and a['frame'] in state.get('frames', []) for a in actions):
        actions[:] = [a for a in actions if a['action'] != 'set_fixed_frame']
        actions.insert(0, {'action': 'set_fixed_frame', 'display': '', 'display_type': '', 'topic': '', 'property': '',
                           'value': '', 'frame': better, 'auto': True,
                           'description': f'Set Fixed Frame to {better} ("{state.get("fixed_frame")}" is not in the TF tree; '
                                          'AutoDiag TF fix)'})
    # A frame named in the request ("... in the base_link frame") that the model did not apply.
    if 'frame' in request.lower() and not any(a['action'] == 'set_fixed_frame' for a in actions):
        words = set(re.findall(r'[A-Za-z0-9_/]+', request))
        named = [f for f in state.get('frames', []) if f in words and f != state.get('fixed_frame')]
        if len(named) == 1:
            actions.append({'action': 'set_fixed_frame', 'display': '', 'display_type': '', 'topic': '', 'property': '',
                            'value': '', 'frame': named[0], 'auto': True,
                            'description': f'Set Fixed Frame to {named[0]} (from your request)'})
    # Drop repeated settings of the same property (keep the first, which is the most specific).
    seen = set()
    for a in list(actions):
        key = (a['action'], a['display'].lower(), a['property']) if a['action'] == 'set_property' else None
        if key and key in seen:
            actions.remove(a)
        elif key:
            seen.add(key)
    if any(info.get('fix') for info in qos.values()):
        result['notes'].insert(0, 'AutoDiag found QoS mismatches between your displays and their publishers; fixes are included.')


MAX_HISTORY_TURNS = 4


def _history_text(history: list | None) -> str:
    """Earlier turns as compact text: what was asked, proposed, and what really happened in RViz."""
    lines = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        lines.append(f"- User asked: {str(turn.get('request', ''))[:500]}")
        if turn.get('summary'):
            lines.append(f"  You answered: {str(turn['summary'])[:400]}")
        for note in (turn.get('notes') or [])[:4]:
            lines.append(f"  Your note: {str(note)[:300]}")
        for a in (turn.get('actions') or [])[:15]:
            if isinstance(a, dict):
                lines.append(f"  {str(a.get('result') or 'proposed, not applied')[:60]}: {str(a.get('description', ''))[:200]}")
        if turn.get('undone'):
            lines.append('  The user pressed Undo: those applied changes were reverted.')
    return '\n'.join(lines)


def plan(request: str, state: dict, provider: str | None = None, model: str | None = None,
         history: list | None = None) -> dict:
    if not request.strip():
        raise PlanError('Describe what you want to see in RViz.')
    provider = provider or llm.default_provider()
    started = time.monotonic()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        snapshot = _discover()
        inspect = _snapshot_inspector(snapshot)
        topics_job, qos_job = pool.submit(_live_topics, snapshot), pool.submit(_topic_qos, state, inspect)
        topics, qos = topics_job.result(), qos_job.result()
    earlier = _history_text(history)
    prompt = ('CONTEXT (current RViz state, already including any applied changes):\n' + _context(state, topics, qos)
              + (f'\n\nEARLIER IN THIS CONVERSATION (oldest first):\n{earlier}' if earlier else '')
              + '\n\nREQUEST: ' + request.strip()[:1000])
    if llm.is_cloud(provider):
        from .redact import mask_for_cloud
        prompt = mask_for_cloud(prompt)
    try:
        raw = llm.complete_json(provider, SYSTEM, prompt, PLAN_SCHEMA, model)
    except llm.ProviderError as exc:
        raise PlanError(str(exc)) from exc
    result = validate(raw, state, topics)
    qos = {**qos, **_added_display_qos(result['actions'], inspect)}
    _complete(result, qos, request, state)
    result.update(provider=provider, model=model or llm.model_for(provider),
                  seconds=round(time.monotonic() - started, 2))
    return result
