"""Score devices for a workload: estimated success probability x cost.

The success model is deliberately simple and transparent — a product of
per-operation survival probabilities from the catalog's approximate median
error rates, with a connectivity-dependent multiplier on two-qubit gate count
to account for SWAP-routing overhead on sparse topologies. It is routing
guidance ("which device class is sane for this job"), not a fidelity
prediction.
"""

from __future__ import annotations

from pydantic import BaseModel

from qontinuum.cost.analysis import CircuitProfile
from qontinuum.cost.estimator import CostEstimate

# Extra two-qubit gates incurred mapping an abstract circuit onto the topology.
ROUTING_OVERHEAD = {
    "all_to_all": 1.0,
    "heavy_hex": 1.6,
    "square": 1.4,
    "linear": 2.0,
}


class RouteScore(BaseModel):
    provider: str
    device: str
    display: str
    success_prob: float | None = None  # None when no quality data in the catalog
    usd: float | None = None
    units: str = ""
    feasible: bool = True
    note: str = ""

    @property
    def usd_per_success(self) -> float | None:
        """Expected dollars per successful (error-free) shot batch."""
        if self.usd is None or not self.success_prob:
            return None
        return self.usd / self.success_prob


def success_probability(profile: CircuitProfile, quality: dict) -> float:
    """P(a single shot survives with no gate or readout error)."""
    overhead = ROUTING_OVERHEAD[quality["connectivity"]]
    # Routing overhead only bites once the circuit spans >2 qubits.
    n_2q = profile.n_2q_effective * (overhead if profile.num_qubits > 2 else 1.0)
    p = (1 - quality["error_1q"]) ** profile.n_1q_gates
    p *= (1 - quality["error_2q"]) ** n_2q
    p *= (1 - quality["error_readout"]) ** profile.n_measurements
    return p


def score_devices(
    profiles: list[CircuitProfile],
    estimates: list[CostEstimate],
    catalog: dict,
) -> list[RouteScore]:
    """Combine suite cost estimates with per-device success probabilities.

    ``estimates`` must be suite-level (one entry per device); the success
    probability reported is the worst (deepest) circuit's, since that is the
    one that decides whether the device is usable for the suite.
    """
    quality_by_device = {
        device_id: device.get("quality")
        for provider in catalog["providers"].values()
        for device_id, device in provider["devices"].items()
    }
    scores = []
    for est in estimates:
        quality = quality_by_device.get(est.device)
        success = None
        if quality is not None and est.feasible and profiles:
            success = min(success_probability(p, quality) for p in profiles)
        scores.append(
            RouteScore(
                provider=est.provider,
                device=est.device,
                display=est.display,
                success_prob=success,
                usd=est.usd,
                units=est.units,
                feasible=est.feasible,
                note=est.note,
            )
        )
    return scores


def rank(scores: list[RouteScore], optimize: str = "value") -> list[RouteScore]:
    """Order devices best-first by 'cost', 'fidelity', or 'value' ($/success)."""
    infinity = float("inf")

    def key(s: RouteScore) -> tuple:
        if optimize == "cost":
            metric = s.usd if s.usd is not None else infinity
        elif optimize == "fidelity":
            metric = -(s.success_prob if s.success_prob is not None else -infinity)
        elif optimize == "value":
            metric = s.usd_per_success if s.usd_per_success is not None else infinity
        else:
            raise ValueError(f"unknown optimize target {optimize!r}")
        return (not s.feasible, metric)

    return sorted(scores, key=key)
