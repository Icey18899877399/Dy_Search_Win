"""Validate and prepare explicit source costs without authenticating observations.

Profile v1 accepts only version, observations, weights, base_cost, budget_unit,
and optional base_time_unit (default day). The existing [0249] transformation
owns all ratio, weight, denominator, and time-unit arithmetic. Weights sum to
one, so costs summed over ALL visible sources equal base_cost per day after
unit conversion. Selecting a subset never renormalizes that subset's costs.
"""
from copy import deepcopy
import hashlib
import json
import math

from .calibration_observations import normalize_source_costs, _timestamp

_REQUIRED = {'version', 'observations', 'weights', 'base_cost', 'budget_unit'}
_ALLOWED = _REQUIRED | {'base_time_unit'}
_KINDS = {'retrieval_interface': 'supplied_interface_observations',
          'synthetic': 'synthetic_formula_fixture'}


def _finite_json(value, ancestors=None):
    """Reject Python-only types, ambiguous keys, cycles and nonfinite metadata."""
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError('profile requires finite JSON numbers')
        return
    if type(value) not in (list, dict):
        raise ValueError('profile must contain only finite JSON values')
    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        raise ValueError('profile must not contain JSON cycles')
    ancestors.add(identity)
    try:
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError('profile JSON object keys must be strings')
            children = value.values()
        else:
            children = value
        for child in children:
            _finite_json(child, ancestors)
    finally:
        ancestors.remove(identity)


def _source_ids(values):
    if isinstance(values, (str, bytes, dict)):
        raise ValueError('source_ids must be a collection of unique nonempty source IDs')
    try:
        values = list(values)
    except TypeError as exc:
        raise ValueError('source_ids must be a collection of source IDs') from exc
    if not values or any(type(value) is not str or not value.strip() for value in values):
        raise ValueError('source_ids must contain nonempty source IDs')
    if len(set(values)) != len(values):
        raise ValueError('source_ids must not contain duplicates')
    return set(values)


def prepare_source_cost_profile(profile, source_ids, cutoff):
    """Return isolated engine parameters, original profile provenance and status.

    Observations require every field accepted by normalize_source_costs plus a
    nonempty interface_id, full timezone-aware observed_at, and measurement_kind
    ('retrieval_interface' or 'synthetic'). Kinds must be uniform. Extra observation
    metadata is preserved but must be finite JSON. Source IDs must match the full
    visible-source set exactly, and observed_at must not exceed the full aware
    ISO cutoff. No source falls back to defaults and no zero cost is clipped.

    The profile's supplied provenance is retained, never verified. The adapter
    applies a deterministic transformation, not empirical calibration. Supported
    base_time_unit values are those of the existing normalizer: second, minute,
    hour and day. Only simulation_units are compatible with the current engine.
    """
    if type(profile) is not dict:
        raise ValueError('source cost profile must be a JSON object')
    _finite_json(profile)
    missing, unknown = _REQUIRED - set(profile), set(profile) - _ALLOWED
    if missing or unknown:
        raise ValueError(f'Invalid profile fields: missing={sorted(missing)}, unknown={sorted(unknown)}')
    if profile['version'] != 'patent_source_cost_v1':
        raise ValueError('version must be patent_source_cost_v1')
    if profile['budget_unit'] != 'simulation_units':
        raise ValueError('budget_unit must be simulation_units for engine compatibility')
    if type(profile['observations']) is not list or not profile['observations']:
        raise ValueError('observations must be a nonempty JSON list')
    expected_sources = _source_ids(source_ids)
    cutoff_time = _timestamp(cutoff, 'cutoff')
    seen, kinds = set(), set()
    for row in profile['observations']:
        if type(row) is not dict:
            raise ValueError('Each observation must be a JSON object')
        source = row.get('source_id')
        if type(source) is not str or not source.strip():
            raise ValueError('source_id must be a nonempty string')
        if source in seen:
            raise ValueError(f'Duplicate source_id: {source}')
        seen.add(source)
        if type(row.get('interface_id')) is not str or not row['interface_id'].strip():
            raise ValueError('interface_id must be a nonempty string')
        kind = row.get('measurement_kind')
        if type(kind) is not str or kind not in _KINDS:
            raise ValueError('measurement_kind must be retrieval_interface or synthetic')
        kinds.add(kind)
        if _timestamp(row.get('observed_at'), 'observed_at') > cutoff_time:
            raise ValueError(f'observed_at for {source} is after task cutoff')
    if len(kinds) != 1:
        raise ValueError('measurement_kind must be uniform across the profile')
    if seen != expected_sources:
        raise ValueError('profile source_ids must match all visible sources exactly: '
                         f'missing={sorted(expected_sources-seen)}, extra={sorted(seen-expected_sources)}')

    frozen_profile = deepcopy(profile)
    transformed = normalize_source_costs(
        deepcopy(frozen_profile['observations']), weights=frozen_profile['weights'],
        base_cost=frozen_profile['base_cost'], budget_unit=frozen_profile['budget_unit'],
        base_time_unit=frozen_profile.get('base_time_unit', 'day'))
    source_parameters = {}
    for source, row in transformed['sources'].items():
        if not row['config_compatible'] or row['cost_per_day'] <= 0:
            raise ValueError(f'Engine requires positive compatible cost_per_day for source {source}; '
                             'zero costs cannot be applied')
        source_parameters[source] = {'cost_per_day': row['cost_per_day']}
    serialized = json.dumps(frozen_profile, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':'), allow_nan=False)
    profile_digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    kind = next(iter(kinds))
    diagnostics = dict(
        observation_status=_KINDS[kind], measurement_kind=kind,
        status='transformed_supplied_observations', method=transformed['method'],
        empirical_calibration=False, provenance_verified=False, applied=True,
        normalization_scope='all_visible_sources', subset_renormalization=False,
        source_count=len(source_parameters), source_ids=sorted(expected_sources),
        unit=transformed['unit'], base_cost_per_day=transformed['base_cost_per_day'],
        total_source_cost_per_day=math.fsum(row['cost_per_day'] for row in source_parameters.values()),
        cutoff=cutoff_time.isoformat())
    return dict(source_parameters=source_parameters,
                provenance=dict(profile=frozen_profile, profile_digest=profile_digest,
                                digest_algorithm='sha256_canonical_json_utf8',
                                transformation=transformed, cutoff=cutoff_time.isoformat(),
                                source_ids=sorted(expected_sources), empirical_calibration=False,
                                provenance_verified=False),
                diagnostics=diagnostics)