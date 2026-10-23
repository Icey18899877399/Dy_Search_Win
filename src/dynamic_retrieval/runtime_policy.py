"""Opt-in, supplied runtime policy; validation is not empirical calibration.

The caller supplies a median evidence-incubation span and its provenance. Article
publication gaps are never inferred as this span. Urgency is that span divided by
remaining task duration. Budgets are absolute simulation units, not fractions or
currency. Only the three documented parameters vary; slow_fraction stays fixed.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math

from .calibration import interpolate_policy
from .models import Config

PARAMETERS = frozenset(('slow_multiplier', 'waiting_share', 'shared_quota'))


def _number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be {"positive" if positive else "nonnegative"}')
    return value


def _digest(value):
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Runtime policy must contain finite JSON-compatible data') from exc
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _validated_config(cfg, parameters):
    if not isinstance(cfg, Config):
        raise ValueError('cfg must be a Config')
    # Revalidate even an existing Config, because dataclass attributes are mutable.
    return Config.from_dict(dict(asdict(cfg), **parameters))


def validate_runtime_policy(profile, cfg):
    """Return a detached, validated profile, leaving caller inputs untouched.

    Required keys: evidence_span_days (explicit positive median incubation span),
    evidence_span_provenance (nonempty string), task_duration_days (positive),
    budget_unit ('simulation_units'), and table. The table uses the public
    calibration.interpolate_policy row format and exactly PARAMETERS names.
    Every rectangle cell must be present with at least two points on each axis.

    All parameters are nonincreasing with urgency; slow_multiplier is also
    nonincreasing with budget, as required by [0103]. Endpoint and interpolated
    parameters must satisfy Config. out_of_domain is 'error' by default, or
    explicitly 'clamp'. No profile can assert independent empirical validation.
    """
    if not isinstance(profile, dict):
        raise ValueError('runtime_policy must be an object')
    result = deepcopy(profile)
    _validated_config(cfg, {})
    for name in ('evidence_span_days', 'task_duration_days'):
        _number(result.get(name), name, positive=True)
    provenance = result.get('evidence_span_provenance')
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError('evidence_span_provenance must be a nonempty string')
    if result.get('budget_unit') != 'simulation_units':
        raise ValueError('budget_unit must be simulation_units (absolute budget)')
    if result.get('calibration_status', 'supplied_unvalidated') != 'supplied_unvalidated':
        raise ValueError('A supplied runtime policy cannot assert empirical calibration')
    if result.get('independently_validated', False) is not False:
        raise ValueError('A supplied runtime policy cannot assert independent validation')
    domain_policy = result.setdefault('out_of_domain', 'error')
    if domain_policy not in ('error', 'clamp'):
        raise ValueError('out_of_domain must be error or clamp')
    table = result.get('table')
    if not isinstance(table, list) or not table:
        raise ValueError('table must be a nonempty list')
    cells = {}
    for row in table:
        if not isinstance(row, dict):
            raise ValueError('Each table row must be an object')
        u = _number(row.get('urgency'), 'table urgency')
        b = _number(row.get('budget'), 'table budget')
        params = row.get('parameters')
        if not isinstance(params, dict) or set(params) != PARAMETERS:
            raise ValueError('Table parameters must be exactly slow_multiplier, waiting_share, shared_quota')
        _validated_config(cfg, params)
        if (u, b) in cells:
            raise ValueError('Duplicate table coordinates')
        cells[u, b] = params
    us = sorted({u for u, _ in cells})
    bs = sorted({b for _, b in cells})
    # Public interpolation owns rectangle completeness and numeric checks.
    interpolation = interpolate_policy(table, us[0], bs[0])
    for b in bs:
        for low, high in zip(us, us[1:]):
            for name in PARAMETERS:
                if cells[high, b][name] > cells[low, b][name]:
                    raise ValueError(f'{name} must be nonincreasing with urgency')
    for u in us:
        for low, high in zip(bs, bs[1:]):
            if cells[u, high]['slow_multiplier'] > cells[u, low]['slow_multiplier']:
                raise ValueError('slow_multiplier must be nonincreasing with budget')
    result['calibration_status'] = 'supplied_unvalidated'
    result['independently_validated'] = False
    result.pop('provenance_hash', None)
    result.pop('table_hash', None)
    result['provenance_hash'] = _digest(result)
    result['table_hash'] = interpolation['provenance_hash']
    return result


def runtime_parameters(profile, elapsed_days, remaining_budget, cfg):
    """Return (new parameter dict, audit trace); no Config or profile mutation.

    elapsed_days is zero for the first round. At or beyond the deadline return
    ({}, trace) with status='deadline_reached'; the engine owns stopping. No
    division or table interpolation is performed for an expired task. For live
    tasks, the default is an explicit out-of-domain error. Opt-in clamping keeps
    raw inputs, actual interpolation coordinates, domain and changed axes in the
    trace. Returned params and trace['parameters'] do not share mutable state.
    """
    p = validate_runtime_policy(profile, cfg)
    _number(elapsed_days, 'elapsed_days')
    _number(remaining_budget, 'remaining_budget')
    remaining = p['task_duration_days'] - elapsed_days
    us = [row['urgency'] for row in p['table']]
    bs = [row['budget'] for row in p['table']]
    domain = dict(urgency=[min(us), max(us)], budget=[min(bs), max(bs)])
    trace = dict(status='deadline_reached' if remaining <= 0 else 'supplied_table_interpolation',
                 elapsed_days=elapsed_days, task_duration_days=p['task_duration_days'],
                 task_remaining_days=remaining, evidence_span_days=p['evidence_span_days'],
                 evidence_span_provenance=p['evidence_span_provenance'],
                 remaining_budget=remaining_budget, budget_unit=p['budget_unit'],
                 urgency=None, interpolation_coordinates=None, domain=domain,
                 clamped_axes=[], out_of_domain=p['out_of_domain'], parameters={},
                 slow_fraction=cfg.slow_fraction, provenance_hash=p['provenance_hash'],
                 table_hash=p['table_hash'], calibration_status='supplied_unvalidated',
                 independently_validated=False)
    if remaining <= 0:
        return {}, trace
    urgency = _number(p['evidence_span_days'] / remaining, 'computed urgency')
    coordinates = dict(urgency=urgency, budget=remaining_budget)
    for axis, value in coordinates.items():
        low, high = domain[axis]
        if not low <= value <= high:
            if p['out_of_domain'] == 'error':
                raise ValueError(f'{axis}={value} outside supplied table domain [{low}, {high}]')
            coordinates[axis] = min(high, max(low, value))
            trace['clamped_axes'].append(axis)
    interpolated = interpolate_policy(p['table'], **coordinates)
    params = interpolated['parameters']
    _validated_config(cfg, params)
    trace.update(urgency=urgency, interpolation_coordinates=coordinates,
                 parameters=deepcopy(params))
    return params, trace
