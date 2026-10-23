"""Configuration and its public validation boundary. Defaults are uncalibrated examples."""
from dataclasses import dataclass, asdict, fields
import math


@dataclass
class Config:
    mode: str = 'enhanced'
    initial_window_days: float = 14.
    earliest_days: float = 120.
    min_window_days: float = 3.
    band_days: float = 14.
    grid_days: float = 3.5
    shrink_fraction: float = .25
    total_budget: float = 200.
    rounds: int = 24
    round_budget: float = 20.
    query_cost: float = .2
    read_cost: float = 1.
    band_fraction: float = .25
    recovery_fraction: float = .25
    shared_quota: float = .6
    grid_decay: float = 1.
    gamma: float = .5
    admission: float = .4
    omega: float = 2.
    low_loss: float = .05
    high_loss: float = .2
    epsilon: float = .05
    stable_distance: float = .01
    convergence: float = .9
    source_exhaustion: float = .95
    confirmation_rounds: int = 3
    source_confirmation_rounds: int = 3
    coverage_scale: float = 2.
    survival_alpha: float = 1.
    default_wait_days: float = 1.
    round_interval_days: float = 1.
    slow_multiplier: float = 3.
    slow_fraction: float = .4
    waiting_share: float = .3
    cost_per_day: float = .05
    conversion_cap: float = 10.
    conversion_window: int = 3
    min_source_share: float = .2
    enable_uncertainty_expansion: bool = False
    uncertainty_threshold: float = .95
    initial_source_limit: int = 0

    def __post_init__(self):
        if type(self.enable_uncertainty_expansion) is not bool:
            raise ValueError('enable_uncertainty_expansion must be a JSON boolean')
        if self.mode not in ('fixed', 'basic', 'enhanced'):
            raise ValueError('mode must be fixed, basic or enhanced')
        for key, value in asdict(self).items():
            if key not in ('mode','enable_uncertainty_expansion') and (type(value) not in (int,float)):
                raise ValueError(f'{key} must be numeric')
            if isinstance(value, (int,float)) and not math.isfinite(value):
                raise ValueError(f'{key} must be finite')
        for key in ('initial_window_days','earliest_days','min_window_days','band_days','grid_days',
                    'total_budget','round_budget','query_cost','read_cost','grid_decay','omega',
                    'coverage_scale','survival_alpha','default_wait_days','round_interval_days',
                    'cost_per_day','conversion_cap'):
            if getattr(self,key) <= 0: raise ValueError(f'{key} must be positive')
        for key in ('rounds','confirmation_rounds','source_confirmation_rounds','conversion_window'):
            if type(getattr(self,key)) is not int or getattr(self,key)<1:
                raise ValueError(f'{key} must be a positive integer')
        for key in ('gamma','admission','band_fraction','recovery_fraction','shared_quota',
                    'slow_fraction','waiting_share','min_source_share'):
            if not 0 < getattr(self,key) < 1: raise ValueError(f'{key} must be between zero and one')
        if not 0 < self.shrink_fraction <= 1: raise ValueError('Invalid shrink_fraction')
        if not 0 <= self.low_loss < self.high_loss <= 1: raise ValueError('Invalid loss hysteresis')
        if not 0 < self.convergence <= self.source_exhaustion <= 1: raise ValueError('Invalid exhaustion thresholds')
        if not 0 <= self.stable_distance <= 1 or self.epsilon < 0: raise ValueError('Invalid convergence tolerance')
        if self.slow_multiplier <= 1: raise ValueError('slow_multiplier must exceed 1')
        if not self.min_window_days <= self.initial_window_days <= self.earliest_days:
            raise ValueError('Require min_window <= initial_window <= earliest_days')
        if self.band_fraction + self.recovery_fraction >= 1: raise ValueError('No regular budget reserved')
        if type(self.initial_source_limit) is not int or self.initial_source_limit < 0:
            raise ValueError('Invalid initial_source_limit')
        if not 0 <= self.uncertainty_threshold <= 1: raise ValueError('Invalid uncertainty threshold')

    @classmethod
    def from_dict(cls, value):
        unknown = set(value) - {x.name for x in fields(cls)}
        if unknown: raise ValueError(f'Unknown config keys: {sorted(unknown)}')
        return cls(**value)
