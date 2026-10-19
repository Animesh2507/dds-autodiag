"""Configure-RViz benchmark: how well and how fast does each AI model plan RViz changes?

Every scenario is a fixed RViz state (displays with their real RViz properties, TF frames, live topics and
publisher QoS) plus a request and the checks a correct plan must pass. Nothing touches a robot or RViz: the
planner runs exactly as in the panel, from the same context, and the final plan (model + AutoDiag's
validation and fixes) is scored.

    dds-autodiag bench                                    # the default local model only (free)
    dds-autodiag bench --model ollama:qwen2.5:3b --model anthropic:claude-sonnet-5-5 --markdown
"""
from __future__ import annotations

import copy
import platform
import re
import statistics
import time

from . import __version__, llm
from . import rviz_agent as ra

LIDAR = 'BEST_EFFORT'


def _qos(reliability='RELIABLE', durability='VOLATILE'):
    return {'reliability': reliability, 'durability': durability}


def _topic_props(topic, reliability='Reliable', durability='Volatile', depth='5'):
    return {'Topic': topic, 'Topic/Depth': depth, 'Topic/History Policy': 'Keep Last',
            'Topic/Reliability Policy': reliability, 'Topic/Durability Policy': durability}


GRID = {'name': 'Grid', 'type': 'rviz_default_plugins/Grid', 'enabled': True, 'status': 'Ok', 'topic': '',
        'properties': {'Reference Frame': '<Fixed Frame>', 'Plane Cell Count': '60', 'Normal Cell Count': '0',
                       'Cell Size': '1', 'Line Style': 'Lines', 'Line Style/Line Width': '0.03', 'Color': '90; 95; 105',
                       'Alpha': '0.5', 'Plane': 'XY', 'Offset': '0; 0; 0'}}
AXES = {'name': 'Robot', 'type': 'rviz_default_plugins/Axes', 'enabled': True, 'status': 'Ok', 'topic': '',
        'properties': {'Reference Frame': 'base_link', 'Length': '0.6', 'Radius': '0.06', 'Show Trail': 'false',
                       'Alpha': '1'}}
MAP = {'name': 'Map', 'type': 'rviz_default_plugins/Map', 'enabled': True, 'status': 'Warn', 'topic': '/map',
       'properties': {**_topic_props('/map'), 'Topic/Update Topic': '/map_updates', 'Alpha': '0.85',
                      'Color Scheme': 'map', 'Draw Behind': 'false', 'Resolution': '0', 'Width': '0', 'Height': '0',
                      'Position': '0; 0; 0', 'Orientation': '0; 0; 0; 1', 'Use Timestamp': 'false'}}
SCAN = {'name': 'LaserScan', 'type': 'rviz_default_plugins/LaserScan', 'enabled': True, 'status': 'Warn',
        'topic': '/scan',
        'properties': {**_topic_props('/scan'), 'Topic/Filter size': '10', 'Selectable': 'true', 'Style': 'Flat Squares',
                       'Size (m)': '0.05', 'Alpha': '1', 'Decay Time': '0', 'Position Transformer': 'XYZ',
                       'Color Transformer': 'FlatColor', 'Color': '239; 41; 41', 'Use rainbow': 'true',
                       'Invert Rainbow': 'false', 'Autocompute Intensity Bounds': 'true'}}
CLOUD = {'name': 'PointCloud', 'type': 'rviz_default_plugins/PointCloud2', 'enabled': True, 'status': 'Ok',
         'topic': '/points',
         'properties': {**_topic_props('/points', reliability='Best Effort'), 'Topic/Filter size': '10',
                        'Selectable': 'true', 'Style': 'Flat Squares', 'Size (m)': '0.01', 'Alpha': '1',
                        'Decay Time': '0', 'Position Transformer': 'XYZ', 'Color Transformer': 'AxisColor',
                        'Axis': 'Z', 'Autocompute Value Bounds': 'true', 'Use Fixed Frame': 'true'}}

FRAMES = ['map', 'odom', 'base_link', 'laser', 'velodyne', 'wheel_fl', 'wheel_fr', 'wheel_rl', 'wheel_rr']
TOPICS = {'/scan': 'sensor_msgs/msg/LaserScan', '/points': 'sensor_msgs/msg/PointCloud2',
          '/map': 'nav_msgs/msg/OccupancyGrid', '/odom': 'nav_msgs/msg/Odometry',
          '/robot_description': 'std_msgs/msg/String', '/tf': 'tf2_msgs/msg/TFMessage',
          '/tf_static': 'tf2_msgs/msg/TFMessage', '/cmd_vel': 'geometry_msgs/msg/Twist',
          '/rosout': 'rcl_interfaces/msg/Log', '/parameter_events': 'rcl_interfaces/msg/ParameterEvent'}
NAV_TOPICS = {**TOPICS, '/plan': 'nav_msgs/msg/Path', '/global_costmap/costmap': 'nav_msgs/msg/OccupancyGrid',
              '/local_costmap/costmap': 'nav_msgs/msg/OccupancyGrid', '/goal_pose': 'geometry_msgs/msg/PoseStamped',
              '/local_costmap/published_footprint': 'geometry_msgs/msg/PolygonStamped',
              '/amcl_pose': 'geometry_msgs/msg/PoseWithCovarianceStamped'}
CAMERA_TOPICS = {**TOPICS, '/front_camera/image_raw': 'sensor_msgs/msg/Image',
                 '/front_camera/camera_info': 'sensor_msgs/msg/CameraInfo'}
ENDPOINTS = {
    '/scan': [{'kind': 'publisher', 'node': 'lidar_driver', 'type': TOPICS['/scan'], 'qos': _qos(LIDAR)}],
    '/points': [{'kind': 'publisher', 'node': 'velodyne_driver', 'type': TOPICS['/points'], 'qos': _qos(LIDAR)}],
    '/map': [{'kind': 'publisher', 'node': 'map_server', 'type': TOPICS['/map'],
              'qos': _qos('RELIABLE', 'TRANSIENT_LOCAL')}],
    '/robot_description': [{'kind': 'publisher', 'node': 'robot_state_publisher', 'type': TOPICS['/robot_description'],
                            'qos': _qos('RELIABLE', 'TRANSIENT_LOCAL')}],
    '/global_costmap/costmap': [{'kind': 'publisher', 'node': 'global_costmap', 'type': 'nav_msgs/msg/OccupancyGrid',
                                 'qos': _qos('RELIABLE', 'TRANSIENT_LOCAL')}],
    '/local_costmap/costmap': [{'kind': 'publisher', 'node': 'local_costmap', 'type': 'nav_msgs/msg/OccupancyGrid',
                                'qos': _qos('RELIABLE', 'VOLATILE')}],
    '/plan': [{'kind': 'publisher', 'node': 'planner_server', 'type': 'nav_msgs/msg/Path', 'qos': _qos()}],
    '/front_camera/image_raw': [{'kind': 'publisher', 'node': 'front_camera', 'type': 'sensor_msgs/msg/Image',
                                 'qos': _qos(LIDAR)}],
}


def check(action, *, display=None, display_type=None, topic=None, prop=None, value=None, frame=None, label=''):
    """A required action. String fields match case-insensitively; `value` may be a regex (r'...')."""
    return {'action': action, 'display': display, 'display_type': display_type, 'topic': topic, 'property': prop,
            'value': value, 'frame': frame, 'label': label}


def note(pattern, label):
    return {'note': pattern, 'label': label}


def _state(displays, fixed_frame='map'):
    return {'fixed_frame': fixed_frame, 'frames': FRAMES, 'displays': copy.deepcopy(displays)}


SCENARIOS = [
    {'id': 'fix_qos', 'title': 'Fix two silent QoS problems',
     'request': 'My LaserScan and map show nothing. Fix them.',
     'state': _state([GRID, AXES, MAP, SCAN]), 'topics': TOPICS,
     'checks': [check('set_property', display='LaserScan', prop='Topic/Reliability Policy', value='Best Effort',
                      label='LaserScan → Best Effort'),
                check('set_property', display='Map', prop='Topic/Durability Policy', value='Transient Local',
                      label='Map → Transient Local')]},
    {'id': 'cloud_height', 'title': 'Add a 3D cloud colored by height',
     'request': 'Show the 3D point cloud colored by height.',
     'state': _state([GRID, AXES]), 'topics': TOPICS,
     'checks': [check('add_display', display_type='PointCloud2', topic='/points', label='PointCloud2 on /points'),
                check('set_property', prop='Color Transformer', value='AxisColor', label='AxisColor'),
                check('set_property', prop='Axis', value='Z', label='Axis Z'),
                check('set_property', prop='Topic/Reliability Policy', value='Best Effort',
                      label='Best Effort for the lidar')]},
    {'id': 'tf_robot', 'title': 'TF error + robot model + QoS + 3D cloud (the video request)',
     'request': 'RViz shows nothing and reports a TF error. Fix the frames, show the robot model, fix my LaserScan '
                'and map, and show the 3D point cloud colored by height.',
     'state': _state([GRID, AXES, MAP, SCAN], fixed_frame='odom_combined'), 'topics': TOPICS,
     'checks': [check('set_fixed_frame', frame='map', label='Fixed Frame → map'),
                check('add_display', display_type='RobotModel', topic='/robot_description', label='RobotModel'),
                check('set_property', display='LaserScan', prop='Topic/Reliability Policy', value='Best Effort',
                      label='LaserScan → Best Effort'),
                check('set_property', display='Map', prop='Topic/Durability Policy', value='Transient Local',
                      label='Map → Transient Local'),
                check('add_display', display_type='PointCloud2', topic='/points', label='PointCloud2'),
                check('set_property', prop='Axis', value='Z', label='Axis Z')]},
    {'id': 'follow_up', 'title': 'Follow-up: "make the points bigger"',
     'request': 'Make the points bigger.',
     'state': _state([GRID, AXES, CLOUD]), 'topics': TOPICS,
     'history': [{'request': 'Show the 3D point cloud colored by height.',
                  'summary': 'Added a PointCloud2 display on /points colored by height.',
                  'actions': [{'result': 'applied', 'description': 'Add PointCloud2 display "PointCloud" on /points'},
                              {'result': 'applied', 'description': 'Set Axis of "PointCloud" to Z'}]}],
     'checks': [check('set_property', display='PointCloud', prop=r're:^Size \((m|Pixels)\)$',
                      label='bigger point size on the cloud')]},
    {'id': 'nav2_view', 'title': 'Show what Nav2 is planning',
     'request': 'Show me what navigation is planning: the planned path, the global and local costmaps and the robot '
                'footprint.',
     'state': _state([GRID, AXES, MAP]), 'topics': NAV_TOPICS,
     'checks': [check('add_display', display_type='Path', topic='/plan', label='Path on /plan'),
                check('add_display', display_type='Map', topic='/global_costmap/costmap', label='global costmap'),
                check('add_display', display_type='Map', topic='/local_costmap/costmap', label='local costmap'),
                check('set_property', prop='Color Scheme', value='costmap', label='costmap color scheme'),
                check('add_display', display_type='Polygon', topic='/local_costmap/published_footprint',
                      label='footprint polygon')]},
    {'id': 'light_weight', 'title': 'Make a heavy cloud light-weight (and be honest about it)',
     'request': 'The point cloud is too heavy and RViz lags. Make it light-weight and downsample it.',
     'state': _state([GRID, AXES, CLOUD]), 'topics': TOPICS,
     'checks': [check('set_property', display='PointCloud', prop=r're:^(Decay Time|Topic/Depth|Style|Size \(m\)|'
                      r'Size \(Pixels\)|Selectable)$', label='a load-reducing setting'),
                note(r'(?i)voxel|filter node|pcl|downsampl', 'says real downsampling needs a filter node')]},
    {'id': 'camera', 'title': 'Pick the real camera topic',
     'request': 'Show the front camera image.',
     'state': _state([GRID, AXES]), 'topics': CAMERA_TOPICS,
     'checks': [check('add_display', display_type=r're:^(Image|Camera)$', topic='/front_camera/image_raw',
                      label='Image on /front_camera/image_raw')]},
    {'id': 'hide_rename', 'title': 'Hide and rename',
     'request': 'Hide the grid and rename LaserScan to Front lidar.',
     'state': _state([GRID, AXES, MAP, SCAN]), 'topics': TOPICS,
     'checks': [check('set_enabled', display='Grid', value='false', label='Grid hidden'),
                check('rename_display', display='LaserScan', value=r're:(?i)^front lidar$',
                      label='LaserScan renamed')]},
]


def _match(expected, actual) -> bool:
    if expected is None:
        return True
    actual = str(actual or '')
    if expected.startswith('re:'):
        return re.search(expected[3:], actual) is not None
    return expected.strip().lower() == actual.strip().lower()


def score(scenario: dict, result: dict) -> dict:
    actions = result.get('actions', [])
    notes = ' '.join(result.get('notes', []) + [result.get('summary', '')])
    passed = []
    for c in scenario['checks']:
        if 'note' in c:
            ok = re.search(c['note'], notes) is not None
        else:
            ok = any(a.get('action') == c['action'] and all(
                _match(c[k], a.get(k)) for k in ('display', 'display_type', 'topic', 'property', 'value', 'frame'))
                for a in actions)
        passed.append({'label': c['label'], 'ok': ok})
    return {'checks': passed, 'passed': sum(p['ok'] for p in passed), 'total': len(passed),
            'rejected': len(result.get('rejected', []))}


VARIANTS = {'full': dict(slim=False), 'slim': dict(slim=True), 'default': {}}


def run_one(scenario: dict, provider: str, model: str | None, variant: str = 'default') -> dict:
    snapshot = {t: eps for t, eps in ENDPOINTS.items() if t in scenario['topics']}
    inspect = ra._snapshot_inspector(snapshot)
    qos = ra._topic_qos(scenario['state'], inspect)
    started = time.monotonic()
    try:
        result = ra.plan_with_context(scenario['request'], scenario['state'], scenario['topics'], qos, provider, model,
                                      scenario.get('history'), inspect, **VARIANTS[variant])
    except ra.PlanError as exc:
        return {'scenario': scenario['id'], 'error': str(exc), 'seconds': round(time.monotonic() - started, 2),
                'passed': 0, 'total': len(scenario['checks']), 'checks': [], 'rejected': 0, 'usage': {}}
    s = score(scenario, result)
    return {'scenario': scenario['id'], 'seconds': round(time.monotonic() - started, 2), 'usage': result.get('usage', {}),
            **s}


def run(models: list[tuple[str, str | None]], scenario_ids: list[str] | None = None, repeat: int = 1,
        progress=None, variant: str = 'default') -> dict:
    chosen = [s for s in SCENARIOS if not scenario_ids or s['id'] in scenario_ids]
    out = []
    for provider, model in models:
        model = model or llm.model_for(provider)
        runs = []
        for _ in range(repeat):
            for sc in chosen:
                r = run_one(sc, provider, model, variant)
                runs.append(r)
                if progress:
                    progress(provider, model, r)
        out.append({'provider': provider, 'model': model, 'runs': runs, **summarize(runs)})
    return {'version': __version__, 'date': time.strftime('%Y-%m-%d'), 'machine': machine(), 'variant': variant,
            'scenarios': [{'id': s['id'], 'title': s['title'], 'checks': len(s['checks'])} for s in chosen],
            'results': out}


def summarize(runs: list[dict]) -> dict:
    ok = [r for r in runs if 'error' not in r]
    secs = [r['seconds'] for r in ok]
    return {'scenarios_passed': sum(1 for r in ok if r['passed'] == r['total']), 'scenarios': len(runs),
            'checks_passed': sum(r['passed'] for r in runs), 'checks': sum(r['total'] for r in runs),
            'errors': len(runs) - len(ok), 'rejected': sum(r['rejected'] for r in runs),
            'median_seconds': round(statistics.median(secs), 1) if secs else None,
            'mean_prompt_tokens': _mean(r['usage'].get('prompt_tokens') for r in ok),
            'mean_output_tokens': _mean(r['usage'].get('output_tokens') for r in ok),
            'mean_prompt_seconds': _mean([r['usage'].get('prompt_seconds') for r in ok], 1),
            'mean_output_seconds': _mean([r['usage'].get('output_seconds') for r in ok], 1)}


def _mean(values, digits=0):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    m = sum(vals) / len(vals)
    return round(m, digits) if digits else int(round(m))


def machine() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        with open('/proc/cpuinfo') as f:
            cpu = next((ln.split(':', 1)[1].strip() for ln in f if ln.startswith('model name')), cpu)
    except OSError:
        pass
    return f'{cpu}, {platform.system()} {platform.release()}'


def markdown(report: dict) -> str:
    lines = [f"Configure-RViz benchmark · DDS AutoDiag {report['version']} · {report['date']} · {report['machine']}", '',
             '| Model | Scenarios fully right | Checks passed | Median time per plan | Prompt / output tokens |',
             '|---|---|---|---|---|']
    for r in report['results']:
        tokens = f"{r['mean_prompt_tokens'] or '–'} / {r['mean_output_tokens'] or '–'}"
        err = f" ({r['errors']} errors)" if r['errors'] else ''
        lines.append(f"| {r['provider']} · `{r['model']}` | {r['scenarios_passed']}/{r['scenarios']}{err} | "
                     f"{r['checks_passed']}/{r['checks']} | {r['median_seconds']} s | {tokens} |")
    lines += ['', '| Scenario | ' + ' | '.join(f"`{r['model']}`" for r in report['results']) + ' |',
              '|---|' + '---|' * len(report['results'])]
    for sc in report['scenarios']:
        cells = []
        for r in report['results']:
            runs = [x for x in r['runs'] if x['scenario'] == sc['id']]
            good = sum(1 for x in runs if x['passed'] == x['total'])
            cells.append(f"{'✅' if good == len(runs) else '⚠️' if good else '❌'} "
                         f"{sum(x['passed'] for x in runs)}/{sum(x['total'] for x in runs)} · "
                         f"{statistics.median(x['seconds'] for x in runs):.0f} s")
        lines.append(f"| {sc['title']} | " + ' | '.join(cells) + ' |')
    return '\n'.join(lines) + '\n'
