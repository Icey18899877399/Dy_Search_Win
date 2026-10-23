"""Paragraphs 0193-0206: literal per-cell budgets, with explicit resource denial."""
import math

def literal_cells(boundary, width, fraction, cap, decay):
    # Work in relative coordinates: epoch-day accumulation can manufacture an
    # almost-zero residual cell that would still receive the full near cap.
    ratio=1/fraction
    nearest=round(ratio)
    count=nearest if math.isclose(ratio,nearest,rel_tol=0,abs_tol=1e-10) else math.ceil(ratio)
    cells=[]
    for i in range(count):
        left=i*fraction; right=min(1.,(i+1)*fraction)
        if i==count-1:right=1.
        distance_fraction=1-(left+right)/2
        cells.append(dict(start=boundary-width*(1-left),end=boundary-width*(1-right),
            distance=width*distance_fraction,budget=cap*math.exp(-decay*distance_fraction)))
    return list(reversed(cells))


def validate_grid_policy(policy, config=None):
    if not isinstance(policy,dict) or set(policy)!={'version','cap_fraction','width_fraction'}:
        raise ValueError('grid policy requires version, cap_fraction and width_fraction')
    if policy['version']!='patent_grid_v1':raise ValueError('Unknown grid policy')
    for key in ('cap_fraction','width_fraction'):
        value=policy[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1:
            raise ValueError('grid fractions must be finite and in (0, 1]')
    if policy['width_fraction']<.001:raise ValueError('grid policy exceeds 1000 cells')
    if config is not None:
        # Reject an incompatible ordinary configuration instead of silently
        # renormalizing every cell. Partial final rounds use explicit skip records.
        cells=literal_cells(1.,1.,policy['width_fraction'],policy['cap_fraction'],config.grid_decay)
        if math.fsum(c['budget'] for c in cells)+config.slow_fraction>1+1e-12:
            raise ValueError('grid nominal budget plus slow watch budget exceeds regular round budget; reduce cap_fraction or cell count')
    return dict(policy)

def plan_grid_budget(*,boundary,earliest,band_days,baseline,decay,policy,available):
    policy=validate_grid_policy(policy)
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in
           (boundary,earliest,band_days,baseline,decay,available)):
        raise ValueError('grid geometry and budgets must be finite')
    if min(band_days,baseline,decay)<=0 or available<0 or earliest>boundary:
        raise ValueError('Invalid grid geometry or available budget')
    cells=literal_cells(boundary,band_days,policy['width_fraction'],
                           baseline*policy['cap_fraction'],decay)
    remaining=available
    for index,c in enumerate(cells,1):
        nominal=c.pop('budget')
        c.update(index=index,nominal_budget=nominal,allocated_budget=0.,spent=0.,
            search_start=max(earliest,c['start']),search_end=c['end'])
        if c['end']<=earliest:c['reason']='outside_archive_horizon'
        elif nominal>remaining+1e-12:c['reason']='insufficient_round_budget'
        else:
            c['allocated_budget']=nominal;remaining=max(0.,remaining-nominal);c['reason']='allocated'
    return dict(policy=policy,nominal_band_days=band_days,grid_days=band_days*policy['width_fraction'],
        cap=baseline*policy['cap_fraction'],decay=decay,earliest=earliest,cells=cells,
        nominal_total=math.fsum(c['nominal_budget'] for c in cells),
        total_allocated=math.fsum(c['allocated_budget'] for c in cells),available=available,
        cross_round_credit=False,shortfall_rule='fund_affordable_cells_nearest_first_no_scaling')
