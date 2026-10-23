"""Pure, opt-in estimates from explicit observations; no default configuration writes.

Coverage fits -log(1-observed_coverage) = budget / scale through the origin.
It is a descriptive fit to the supplied coverage denominator, not label tuning.
Cost uses sum(explicit_cost) / sum(recovered_span_days), never article intervals.
Units must be supplied; currency estimates are not simulation-budget parameters.
No publication timestamp is treated as observed response latency or incubation.
"""
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
import math

ELEMENTS = ('subject', 'action', 'object', 'time', 'location')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _number(value, name, minimum=None, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if minimum is not None and value < minimum:
        raise ValueError(f'{name} must be at least {minimum}')
    if maximum is not None and value > maximum:
        raise ValueError(f'{name} must be at most {maximum}')
    return value


def _threshold(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} must be a positive integer')


def _unique_rows(observations):
    rows = list(observations)
    seen = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each observation must be an object')
        for field in ('observation_id', 'source_id'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f'{field} must be a nonempty string')
        identity = row['source_id'], row['observation_id']
        if identity in seen and _json(seen[identity]) != _json(row):
            raise ValueError(f'Conflicting repeated observation: {identity}')
        seen[identity] = row
    return rows, list(seen.values())


def _estimate(value, rows, selected, reasons, unit, domain, method):
    return dict(value=value, status='calibrated' if value is not None else 'uncalibrated',
                sample_count=len(selected), input_sample_count=len(rows),
                excluded_sample_count=len(rows)-len(selected), provenance_hash=_digest(rows),
                unit=unit, domain=domain, reasons=sorted(set(reasons)), method=method,
                config_compatible=(value is not None and value > 0 and unit == 'simulation_units'))


def calibrate_sources(observations, min_samples=3):
    """Return separate estimates for each source; never impute missing observations.

    Rows require source_id and observation_id. Coverage observations additionally
    need budget, coverage in [0,1], and budget_unit. Cost observations need
    explicit_cost, recovered_span_days, and cost_unit. None/missing fields are
    unavailable, whereas malformed numbers raise ValueError. Repeated identical
    observation IDs within a source count once; conflicting IDs are rejected.

    Exact 0/1 coverage cannot identify a finite log-linear scale and is excluded.
    Zero recovered spans are excluded. Zero observed costs remain valid data,
    but a zero cost estimate is incompatible with the current positive Config.
    min_samples is a caller-visible eligibility rule, not a statistical guarantee.
    """
    _threshold(min_samples, 'min_samples')
    raw, rows = _unique_rows(observations)
    grouped = defaultdict(list)
    for row in rows:
        for field in ('budget', 'coverage', 'explicit_cost', 'recovered_span_days'):
            if row.get(field) is not None:
                _number(row[field], field, minimum=0, maximum=1 if field == 'coverage' else None)
        grouped[row['source_id']].append(row)
    sources = {}
    for source, group in sorted(grouped.items()):
        estimates = {}
        for metric, fields, unit_field in (
                ('coverage_scale', ('budget', 'coverage'), 'budget_unit'),
                ('cost_per_day', ('explicit_cost', 'recovered_span_days'), 'cost_unit')):
            selected, reasons = [], []
            for row in group:
                if any(row.get(field) is None for field in fields):
                    reasons.append('missing_explicit_observations')
                    continue
                if not isinstance(row.get(unit_field), str) or not row[unit_field].strip():
                    reasons.append('missing_units')
                    continue
                if metric == 'coverage_scale' and (row['budget'] == 0 or not 0 < row['coverage'] < 1):
                    reasons.append('nonidentifying_coverage_endpoint')
                    continue
                if metric == 'cost_per_day' and row['recovered_span_days'] == 0:
                    reasons.append('zero_recovered_span')
                    continue
                selected.append(row)
            units = sorted({row[unit_field] for row in selected})
            unit = units[0] if len(units) == 1 else None
            if len(units) > 1:
                reasons.append('mixed_units')
            if len(selected) < min_samples:
                reasons.append('insufficient_samples')
            domain = {'source_id': source, 'units': units}
            for field in fields:
                if selected:
                    domain[field] = [min(row[field] for row in selected), max(row[field] for row in selected)]
            value = None
            method = ('zero_intercept_log_linear_least_squares' if metric == 'coverage_scale'
                      else 'total_explicit_cost_over_total_recovered_days')
            if len(selected) >= min_samples and unit is not None:
                try:
                    if metric == 'coverage_scale':
                        maximum_budget = max(row['budget'] for row in selected)
                        x = [row['budget'] / maximum_budget for row in selected]
                        y = [-math.log1p(-row['coverage']) for row in selected]
                        value = maximum_budget * (math.fsum(v*v for v in x) /
                                                  math.fsum(a*b for a,b in zip(x,y)))
                    else:
                        value = math.fsum(row['explicit_cost'] for row in selected) / math.fsum(
                            row['recovered_span_days'] for row in selected)
                    if not math.isfinite(value) or (metric == 'coverage_scale' and value <= 0):
                        value = None
                        reasons.append('numerically_unidentifiable')
                except (OverflowError, ZeroDivisionError):
                    value = None
                    reasons.append('numerically_unidentifiable')
            estimates[metric] = _estimate(value, group, selected, reasons, unit, domain, method)
            estimates[metric]['minimum_samples'] = min_samples
            if value is not None and not estimates[metric]['config_compatible']:
                estimates[metric]['config_reason'] = ('unit_conversion_required' if unit != 'simulation_units'
                                                       else 'current_config_requires_positive_value')
        sources[source] = estimates
    return dict(sources=sources, provenance_hash=_digest(raw), input_sample_count=len(raw),
                unique_sample_count=len(rows), applied=False)


def calibrate_gamma(observations, min_duplicate_clusters=3):
    """Reciprocal mean distinct source count over all complete exact fact clusters.

    Eligibility needs min_duplicate_clusters with at least two distinct sources.
    Singletons remain in the mean; repeated documents from one source do not
    increase its cluster count. Facts must contain five nonempty string elements.
    No fuzzy or topic grouping is performed. Exact elements (including extra
    qualifiers), support, polarity, qualifiers, conditions and event_id are part
    of identity when supplied. This estimates repetition, not causal independence.
    """
    _threshold(min_duplicate_clusters, 'min_duplicate_clusters')
    raw, rows = _unique_rows(observations)
    clusters = defaultdict(set)
    selected, reasons = [], []
    for row in rows:
        elements = row.get('elements')
        if not isinstance(elements, dict) or any(
                not isinstance(elements.get(k), str) or not elements[k].strip() for k in ELEMENTS):
            reasons.append('incomplete_exact_fact')
            continue
        identity = {k: row[k] for k in ('elements','support','polarity','qualifiers','conditions','event_id')
                    if k in row}
        clusters[_json(identity)].add(row['source_id'])
        selected.append(row)
    counts = [len(sources) for sources in clusters.values()]
    duplicates = sum(count >= 2 for count in counts)
    value = None
    if duplicates < min_duplicate_clusters:
        reasons.append('insufficient_duplicate_clusters')
    else:
        value = len(counts) / sum(counts)
    result = _estimate(value, rows, selected, reasons, 'dimensionless',
                       {'source_ids': sorted({row['source_id'] for row in selected}),
                        'fact_identity': 'exact_complete_elements_and_supplied_context'},
                       'reciprocal_mean_distinct_sources_per_exact_cluster')
    result.update(cluster_count=len(counts), duplicate_cluster_count=duplicates,
                  distinct_source_counts=sorted(counts), minimum_duplicate_clusters=min_duplicate_clusters,
                  provenance_hash=_digest(raw), config_compatible=value is not None and 0 < value < 1,
                  applied=False)
    return result


def interpolate_policy(table, urgency, budget):
    """Bilinearly interpolate caller-supplied numeric parameters inside a rectangle.

    Table rows are {urgency, budget, parameters:{name:value}}. At least two
    distinct points per axis and every rectangular cell are required; duplicates,
    inconsistent parameter sets, nonfinite values and extrapolation are rejected.
    The supplied table is not asserted to be empirically calibrated. Caller must
    validate Config constraints and units before explicitly applying parameters.
    No urgency is inferred from article publication intervals.
    """
    _number(urgency, 'urgency', minimum=0)
    _number(budget, 'budget', minimum=0)
    table = list(table)
    cells, names = {}, None
    for row in table:
        if not isinstance(row, dict):
            raise ValueError('Each table row must be an object')
        u = _number(row.get('urgency'), 'table urgency', minimum=0)
        b = _number(row.get('budget'), 'table budget', minimum=0)
        parameters = row.get('parameters')
        if not isinstance(parameters, dict) or not parameters or any(
                not isinstance(name, str) or not name.strip() for name in parameters):
            raise ValueError('Each cell needs named numeric parameters')
        if names is None:
            names = set(parameters)
        if set(parameters) != names:
            raise ValueError('Inconsistent parameter names')
        for name, value in parameters.items():
            _number(value, name)
        if (u,b) in cells:
            raise ValueError('Duplicate table coordinates')
        cells[u,b] = parameters
    us = sorted({u for u,b in cells})
    bs = sorted({b for u,b in cells})
    if len(us) < 2 or len(bs) < 2 or len(cells) != len(us)*len(bs):
        raise ValueError('Require a complete rectangle with two or more points per axis')
    if not us[0] <= urgency <= us[-1] or not bs[0] <= budget <= bs[-1]:
        raise ValueError('Extrapolation outside the supplied table is unsupported')
    ui = min(bisect_right(us, urgency)-1, len(us)-2)
    bi = min(bisect_right(bs, budget)-1, len(bs)-2)
    u0,u1 = us[ui:ui+2]
    b0,b1 = bs[bi:bi+2]
    x,y = (urgency-u0)/(u1-u0), (budget-b0)/(b1-b0)
    parameters = {name: math.fsum((cells[u0,b0][name]*(1-x)*(1-y),
                                   cells[u1,b0][name]*x*(1-y),
                                   cells[u0,b1][name]*(1-x)*y,
                                   cells[u1,b1][name]*x*y)) for name in sorted(names)}
    return dict(parameters=parameters, status='supplied_table_interpolation', applied=False,
                provenance_hash=_digest(table), sample_count=len(table),
                domain={'urgency':[us[0],us[-1]], 'budget':[bs[0],bs[-1]]})
