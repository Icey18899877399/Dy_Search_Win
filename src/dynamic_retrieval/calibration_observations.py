"""Pure transformations of caller-supplied, explicitly grounded observations.

These functions do not verify observations, fetch data, tune against labels, write
configuration, or establish empirical calibration. Publication intervals are not
response latencies or event incubation periods. Currency is never inferred.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re

_COMPONENTS = ('response_latency_seconds', 'rate_limit_quota', 'returned_items')
_DAY_FACTORS = {'second': 86400, 'minute': 1440, 'hour': 24, 'day': 1}
_TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$')


def _digest(value):
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True,
                                separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Observations and provenance must be finite JSON values') from exc
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _number(value, name, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be a finite {"positive" if positive else "nonnegative"} number')
    return value


def _provenance(value, name):
    if not ((isinstance(value, str) and value.strip()) or (isinstance(value, dict) and value)):
        raise ValueError(f'{name} must be a nonempty provenance string or object')
    _digest(value)
    return value


def _rows(observations):
    try:
        rows = list(observations)
    except TypeError as exc:
        raise ValueError('observations must be an iterable of objects') from exc
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('Each observation must be an object')
    return rows


def normalize_source_costs(observations, *, weights, base_cost, budget_unit,
                           base_time_unit='day'):
    """Apply paragraph [0249] literally, over one comparable row per source.

    Each row requires source_id, the three numeric _COMPONENTS, a nonempty
    observation_window and quota_unit, and observation_id or provenance. Window
    and quota unit must match across sources; the caller asserts that these
    labels denote comparable measurements. Duplicate sources or supplied
    observation IDs are rejected. No averaging or hidden deduplication occurs.

    The cost is base_cost * sum(weight[k] * metric[k] / sum_sources(metric[k])).
    In particular rate_limit_quota is NOT inverted: larger quota increases its
    component under the literal patent rule. Weights must sum to one. Every
    denominator must be positive, including components whose weight is zero.
    base_cost is budget_unit / base_time_unit; supported time units convert to
    budget_unit/day. budget_unit is a caller declaration, never a money estimate.
    Zero individual costs are retained and marked incompatible with the current
    engine's positive simulation-unit costs; no clipping is applied.
    """
    rows = _rows(observations)
    if not rows:
        raise ValueError('At least one source observation is required')
    if not isinstance(weights, dict) or set(weights) != set(_COMPONENTS):
        raise ValueError('weights must name exactly the three observation components')
    for name, weight in weights.items():
        _number(weight, f'weight {name}')
    try:
        weight_sum = math.fsum(weights.values())
    except OverflowError as exc:
        raise ValueError('weights must sum to one') from exc
    if not math.isclose(weight_sum, 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError('weights must sum to one')
    _number(base_cost, 'base_cost', positive=True)
    _text(budget_unit, 'budget_unit')
    if not isinstance(base_time_unit, str) or base_time_unit not in _DAY_FACTORS:
        raise ValueError('base_time_unit must be second, minute, hour, or day')
    base_per_day = base_cost * _DAY_FACTORS[base_time_unit]
    _number(base_per_day, 'converted base_cost', positive=True)
    sources_seen, observations_seen = set(), set()
    windows, quota_units = set(), set()
    for row in rows:
        source = _text(row.get('source_id'), 'source_id')
        if source in sources_seen:
            raise ValueError(f'Duplicate source_id: {source}')
        sources_seen.add(source)
        if 'observation_id' in row:
            observation = _text(row['observation_id'], 'observation_id')
            if observation in observations_seen:
                raise ValueError(f'Duplicate observation_id: {observation}')
            observations_seen.add(observation)
        elif 'provenance' not in row:
            raise ValueError('observation_id or provenance is required')
        if 'provenance' in row:
            _provenance(row['provenance'], 'provenance')
        windows.add(_text(row.get('observation_window'), 'observation_window'))
        quota_units.add(_text(row.get('quota_unit'), 'quota_unit'))
        for name in _COMPONENTS:
            _number(row.get(name), name)
    if len(windows) != 1 or len(quota_units) != 1:
        raise ValueError('Sources require consistent observation_window and quota_unit')
    try:
        totals = {name: math.fsum(row[name] for row in rows) for name in _COMPONENTS}
    except OverflowError as exc:
        raise ValueError('Component denominators overflow') from exc
    for name, total in totals.items():
        _number(total, f'{name} denominator', positive=True)
    context = dict(method='patent_0249_literal_weighted_source_ratios', observations=rows,
                   weights=dict(weights), base_cost=base_cost, budget_unit=budget_unit,
                   base_time_unit=base_time_unit)
    provenance_hash = _digest(context)
    sources = {}
    for row in rows:
        components = {name: row[name] / totals[name] for name in _COMPONENTS}
        score = math.fsum(weights[name] * components[name] for name in _COMPONENTS)
        cost = base_per_day * score
        _number(cost, 'cost_per_day')
        sources[row['source_id']] = dict(
            cost_per_day=cost, normalized_components=components, weighted_score=score,
            provenance_hash=_digest(dict(context_hash=provenance_hash, source_id=row['source_id'])),
            config_compatible=cost > 0 and budget_unit == 'simulation_units',
            observation_id=row.get('observation_id'), provenance=row.get('provenance'),
            unit=f'{budget_unit}/day')
    return dict(sources=sources, normalized_totals=totals, weights=dict(weights),
                base_cost=base_cost, base_time_unit=base_time_unit, base_cost_per_day=base_per_day,
                budget_unit=budget_unit, unit=f'{budget_unit}/day',
                observation_window=next(iter(windows)), quota_unit=next(iter(quota_units)),
                provenance_hash=provenance_hash, input_sample_count=len(rows),
                method=context['method'], status='transformed_supplied_observations',
                empirical_calibration=False, applied=False)


def _timestamp(value, name):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError(f'{name} requires a full ISO timestamp with seconds and timezone')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError('Missing timezone')
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid {name} timestamp') from exc


def _quantile(sorted_values, q):
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def estimate_incubation_band(observations, *, event_type, calibration_cutoff,
                             quantile, min_samples=3):
    """Describe observed same-type historical event spans; never tune on labels.

    Rows require unique event_id, event_type, first_relevant_evidence_at and
    event_occurred_at (full timezone-aware ISO strings), timestamp_kind exactly
    'observed_event_times', and separate nonempty evidence_time_provenance and
    event_time_provenance. Those fields attest to independently grounded times;
    this pure function cannot authenticate them. Publication timestamps and
    publication-gap proxies must not be relabeled as observed event times.

    All rows must be well formed, even when ultimately excluded. Other event
    types and events later than the inclusive calibration_cutoff are reported as
    excluded. One day is 86400 elapsed seconds. Quantiles use linear interpolation
    at (n-1)*q; q is explicit and 0.5 <= q < 1. min_samples is an eligibility rule,
    not statistical validation. Below it, no band is returned. The median may
    still describe available eligible samples. No current-task span is inferred.
    """
    rows = _rows(observations)
    _text(event_type, 'event_type')
    cutoff = _timestamp(calibration_cutoff, 'calibration_cutoff')
    _number(quantile, 'quantile')
    if not .5 <= quantile < 1:
        raise ValueError('quantile must satisfy 0.5 <= quantile < 1')
    if type(min_samples) is not int or min_samples < 1:
        raise ValueError('min_samples must be a positive integer')
    seen, samples, excluded = set(), [], []
    for row in rows:
        event_id = _text(row.get('event_id'), 'event_id')
        if event_id in seen:
            raise ValueError(f'Duplicate event_id: {event_id}')
        seen.add(event_id)
        row_type = _text(row.get('event_type'), 'row event_type')
        if row.get('timestamp_kind') != 'observed_event_times':
            raise ValueError('timestamp_kind must be observed_event_times; publication proxies are forbidden')
        _provenance(row.get('evidence_time_provenance'), 'evidence_time_provenance')
        _provenance(row.get('event_time_provenance'), 'event_time_provenance')
        first = _timestamp(row.get('first_relevant_evidence_at'), 'first_relevant_evidence_at')
        occurred = _timestamp(row.get('event_occurred_at'), 'event_occurred_at')
        if first > occurred:
            raise ValueError('first_relevant_evidence_at must not follow event_occurred_at')
        reason = ('different_event_type' if row_type != event_type else
                  'event_after_calibration_cutoff' if occurred > cutoff else None)
        if reason:
            excluded.append(dict(event_id=event_id, reason=reason))
        else:
            samples.append(dict(event_id=event_id, span_days=(occurred-first).total_seconds()/86400))
    spans = sorted(sample['span_days'] for sample in samples)
    sufficient = len(spans) >= min_samples
    band = _quantile(spans, quantile) if sufficient else None
    context = dict(method='linear_quantile_of_observed_historical_event_spans', observations=rows,
                   event_type=event_type, calibration_cutoff=calibration_cutoff,
                   quantile=quantile, min_samples=min_samples)
    return dict(value=band, band_days=band, median_span_days=_quantile(spans, .5) if spans else None,
                sample_count=len(spans), input_sample_count=len(rows),
                excluded_sample_count=len(excluded), excluded_observations=excluded,
                selected_observations=samples, minimum_samples=min_samples,
                event_type=event_type, calibration_cutoff=cutoff.isoformat(), quantile=quantile,
                unit='days', seconds_per_day=86400, method=context['method'],
                provenance_hash=_digest(context),
                status='estimated_from_supplied_observations' if sufficient else 'underidentified',
                reasons=[] if sufficient else ['insufficient_samples'],
                empirical_calibration=False, applied=False)

