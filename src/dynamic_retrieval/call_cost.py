"""Thread-safe observations of API attempts, not billing or simulated budget.

A missing token count remains unknown. Cache usage is historical, never added to
new requests. JSONL persistence is optional and failure is explicit. Snapshots
cover completed attempts; abrupt process termination can leave an in-flight
attempt without a final event. Share one ledger across worker threads.
"""
import copy
import json
import math
import os
from pathlib import Path
import threading

TOKEN_FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens',
                'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')
CORE_FIELDS = TOKEN_FIELDS[:3]
CATEGORIES = {'http', 'connection', 'transport', 'response_json', 'endpoint',
              'completion', 'cache_read', 'cache_write', 'unexpected'}


class CallCostError(RuntimeError):
    """A safe telemetry error; callers must not silently discard it."""


def observed_usage(value):
    """Allow only documented, nonnegative integral token fields; no raw data."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in TOKEN_FIELDS
            if type(value.get(key)) is int and value[key] >= 0}


class CallCostLedger:
    def __init__(self, jsonl_path=None):
        self.jsonl_path = Path(jsonl_path) if jsonl_path is not None else None
        self._events = []
        self._lock = threading.Lock()

    def _persist(self, event):
        if self.jsonl_path is None:
            return
        try:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open('a', encoding='utf-8') as stream:
                if event is not None:
                    stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError, TypeError):
            raise CallCostError('Unable to persist API cost ledger') from None

    def preflight(self):
        """Fail before new transport if the durable destination cannot be used."""
        with self._lock:
            self._persist(None)

    def record(self, kind, *, elapsed_seconds, outcome, usage=None, attempt=None,
               cache_key=None, error_category=None, http_status=None):
        if kind not in ('network_attempt', 'cache_read') or outcome not in ('success', 'failure'):
            raise CallCostError('Invalid API cost event category')
        if (type(elapsed_seconds) not in (float, int) or not math.isfinite(elapsed_seconds)
                or elapsed_seconds < 0):
            raise CallCostError('Invalid API cost duration')
        if error_category is not None and error_category not in CATEGORIES:
            raise CallCostError('Invalid API cost error category')
        if attempt is not None and (type(attempt) is not int or attempt < 1):
            raise CallCostError('Invalid API cost attempt')
        if cache_key is not None and (not isinstance(cache_key, str) or len(cache_key) != 64
                                    or any(c not in '0123456789abcdef' for c in cache_key)):
            raise CallCostError('Invalid API cost cache key')
        if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
            raise CallCostError('Invalid API cost HTTP status')
        event = {'kind': kind, 'elapsed_seconds': float(elapsed_seconds), 'outcome': outcome,
                 'usage': observed_usage(usage), 'attempt': attempt, 'cache_key': cache_key,
                 'error_category': error_category, 'http_status': http_status}
        with self._lock:
            # Preserve observed spend even if persistence subsequently fails.
            self._events.append(event)
            self._persist(event)

    def snapshot(self):
        with self._lock:
            events = copy.deepcopy(self._events)
        network = [e for e in events if e['kind'] == 'network_attempt']
        cache = [e for e in events if e['kind'] == 'cache_read']
        observed = {k: sum(e['usage'].get(k, 0) for e in network) for k in TOKEN_FIELDS}
        actual = {k: observed[k] if all(k in e['usage'] for e in network) else None
                  for k in TOKEN_FIELDS}
        return {'network_attempts': len(network), 'cache_reads': len(cache),
                'cache_hits': sum(e['outcome'] == 'success' for e in cache),
                'failed_network_attempts': sum(e['outcome'] == 'failure' for e in network),
                'unknown_usage_attempts': sum(any(k not in e['usage'] for k in CORE_FIELDS) for e in network),
                'actual_usage': actual, 'observed_usage': observed,
                'historical_cache_usage': {k: sum(e['usage'].get(k, 0) for e in cache)
                    if all(k in e['usage'] for e in cache) else None for k in TOKEN_FIELDS},
                'historical_observed_usage': {k: sum(e['usage'].get(k, 0) for e in cache) for k in TOKEN_FIELDS},
                'historical_unknown_usage_reads': sum(any(k not in e['usage'] for k in CORE_FIELDS) for e in cache),
                'elapsed_seconds': sum(e['elapsed_seconds'] for e in events),
                'network_elapsed_seconds': sum(e['elapsed_seconds'] for e in network),
                'events': events}
