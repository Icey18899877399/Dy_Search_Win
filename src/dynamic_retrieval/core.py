"""Patent equations, deliberately independent of storage and retrieval.

Time arguments use one caller-selected unit (engine: days); budgets are simulated units.
"""
import math
from datetime import datetime, timezone
from collections import defaultdict

ELEMENTS = ('subject', 'action', 'object', 'time', 'location')


def relevance(elements, target):
    pairs = {(k, str(v).strip().casefold()) for k, v in target.items() if v and k in ELEMENTS}
    if not pairs:
        raise ValueError('Target must have at least one nonempty typed element')
    evidence = {(k, str(v).strip().casefold()) for k, v in elements.items() if v and k in ELEMENTS}
    return len(pairs & evidence) / len(pairs)


def fact_key(elements):
    return tuple(str(elements.get(k, '')).strip().casefold() for k in ELEMENTS)


def independent_weights(rows, gamma):
    if not 0 < gamma < 1:
        raise ValueError('gamma must be strictly between zero and one')
    groups = defaultdict(dict)
    for row in rows:
        groups[fact_key(row['elements'])][row['id']] = row
    weights = {}
    for group in groups.values():
        def timestamp(row):
            value=datetime.fromisoformat(row['published_at'].replace('Z','+00:00'))
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        ordered = sorted(group.values(), key=lambda x: (timestamp(x), x['source_id'], x['id']))
        for rank, row in enumerate(ordered):
            weights[row['id']] = gamma ** rank
    return weights


def probabilities(rows, weights, count, omega):
    if count < 2 or omega <= 0 or not math.isfinite(omega):
        raise ValueError('At least two outcomes and a finite positive omega required')
    denom = sum(weights[x['id']] for x in rows)
    scores = [sum(weights[x['id']] * x['support'][c] for x in rows) / denom
              if denom else 0. for c in range(count)]
    logits = [omega * v for v in scores]
    maximum = max(logits)
    exps = [math.exp(v - maximum) for v in logits]
    return [v / sum(exps) for v in exps]


def coverage(budget, scale):
    if budget < 0 or scale <= 0:
        raise ValueError('Budget must be nonnegative and scale positive')
    return -math.expm1(-budget / scale)


def survival(intervals, duration, alpha=1.):
    if alpha <= 0 or duration < 0 or any(x <= 0 for x in intervals):
        raise ValueError('Positive intervals and smoothing; nonnegative duration required')
    return (sum(x > duration for x in intervals) + alpha) / (len(intervals) + alpha)


def exhaustion(intervals, silence, wait, alpha=1., mode='enhanced'):
    if silence < 0 or wait <= 0:
        raise ValueError('Invalid silence or lookahead')
    if not intervals:
        return 0.
    if mode == 'basic':
        return min(1., silence / (sum(intervals) / len(intervals) + wait))
    value = survival(intervals, silence + wait, alpha) / survival(intervals, silence, alpha)
    maximum = max(intervals)
    if silence + wait <= maximum:
        value = min(value, silence / maximum)
    return value


def loss_ratio(loss, volume):
    return loss / (loss + volume) if loss + volume else 0.


def transition_cells(boundary, width, grid_width, cap, decay):
    if min(width, grid_width, cap, decay) <= 0:
        raise ValueError('Transition band parameters must be positive')
    cells = []
    start = boundary - width
    while start < boundary - 1e-12:
        end = min(boundary, start + grid_width)
        distance = boundary - (start + end) / 2
        cells.append(dict(start=start, end=end, distance=distance,
                          budget=cap * math.exp(-decay * distance / width)))
        start = end
    return list(reversed(cells))


def total_variation(current, previous):
    return .5 * sum(abs(a-b) for a, b in zip(current, previous))


def uncertainty(values):
    return -sum(p * math.log(p) for p in values if p > 0) / math.log(len(values))


def can_stop(phis, deltas, threshold, epsilon, mode='enhanced'):
    if not deltas:
        return False
    if mode == 'basic':
        aggregate = sum(phis) / len(phis) if phis else 0.
        return aggregate >= threshold and abs(deltas[-1]) <= epsilon
    return min(phis, default=1.) >= threshold and all(abs(x) <= epsilon for x in deltas)
