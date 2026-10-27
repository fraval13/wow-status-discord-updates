"""Line-graph data and elapsed level durations, never fabricated before tracking."""

def timeline(tracking):
    from .archive import timestamp
    points = tracking.get('points', []) if tracking else []
    first = min(point['at'] for point in points) if points else None
    result = {'timezone': 'Europe/Oslo', 'time_basis': 'elapsed_wall_clock_including_offline',
              'x_axis': 'elapsed_seconds', 'y_axis': 'level', 'points': [], 'durations': []}
    for point in points:
        result['points'].append({
            'level': point['level'], 'recorded_at': timestamp(point['at']),
            'elapsed_seconds': point['at'] - first, 'segment': point['segment'],
            'source': 'level_up_event' if point['kind'] == 'level' else 'baseline_observation',
            'event_id': point.get('event_id')})
    for previous, point in zip(points, points[1:]):
        if (previous['segment'] != point['segment'] or point['kind'] != 'level'
                or point['level'] != previous['level'] + 1 or point['at'] < previous['at']):
            continue
        partial = previous['kind'] == 'baseline'
        duration = point['at'] - previous['at']
        result['durations'].append({
            'level': previous['level'], 'next_level': point['level'], 'partial': partial,
            'elapsed_seconds': None if partial else duration,
            'elapsed_lower_bound_seconds': duration if partial else None,
            'started_at': timestamp(previous['at']), 'finished_at': timestamp(point['at']),
            'source': 'recorded_level_events' if not partial else 'baseline_to_level_event'})
    if tracking and tracking.get('observed_until'):
        result['observed_until'] = timestamp(tracking['observed_until'])
    return result
