"""Estimate hardware cost of circuits across the provider catalog."""

from __future__ import annotations

from functools import cache
from importlib import resources

import yaml
from pydantic import BaseModel
from qiskit import QuantumCircuit

from qontinuum.cost.analysis import CircuitProfile, profile_circuit


class CostEstimate(BaseModel):
    provider: str
    device: str
    display: str
    usd: float | None = None  # None when the provider's dollar rate is not public
    units: str = ""  # e.g. "29.8 HQC" when usd is None
    feasible: bool = True
    note: str = ""

    def sort_key(self) -> tuple:
        infinity = float("inf")
        return (not self.feasible, self.usd if self.usd is not None else infinity)


@cache
def load_catalog() -> dict:
    text = (resources.files("qontinuum.cost") / "catalog.yaml").read_text()
    return yaml.safe_load(text)


def estimate_circuit(
    circuit: QuantumCircuit, shots: int, *, catalog: dict | None = None
) -> list[CostEstimate]:
    """Price one circuit at the given shot count on every catalog device."""
    catalog = catalog or load_catalog()
    profile = profile_circuit(circuit)
    out: list[CostEstimate] = []
    for provider_id, provider in catalog["providers"].items():
        for device_id, device in provider["devices"].items():
            out.append(
                _estimate_device(
                    provider_id, provider["display"], device_id, device, profile, shots
                )
            )
    out.sort(key=CostEstimate.sort_key)
    return out


def estimate_suite(
    circuits_and_shots: list[tuple[QuantumCircuit, int]], *, catalog: dict | None = None
) -> list[CostEstimate]:
    """Price a whole test suite: per-device sum over every (circuit, shots) pair."""
    catalog = catalog or load_catalog()
    totals: dict[tuple[str, str], CostEstimate] = {}
    for circuit, shots in circuits_and_shots:
        for est in estimate_circuit(circuit, shots, catalog=catalog):
            key = (est.provider, est.device)
            prior = totals.get(key)
            if prior is None:
                totals[key] = est
                continue
            merged = prior.model_copy()
            merged.feasible = prior.feasible and est.feasible
            if not merged.feasible:
                merged.usd, merged.units = None, ""
                merged.note = "circuit exceeds device qubit count"
            elif prior.usd is not None and est.usd is not None:
                merged.usd = round(prior.usd + est.usd, 4)
            else:
                merged.units = _merge_units(prior.units, est.units)
            totals[key] = merged
    ranked = list(totals.values())
    ranked.sort(key=CostEstimate.sort_key)
    return ranked


def _estimate_device(
    provider_id: str,
    provider_display: str,
    device_id: str,
    device: dict,
    profile: CircuitProfile,
    shots: int,
) -> CostEstimate:
    base = CostEstimate(
        provider=provider_display,
        device=device_id,
        display=device["display"],
        note=device.get("note", ""),
    )
    if profile.num_qubits > device["qubits"]:
        base.feasible = False
        base.note = f"needs {profile.num_qubits} qubits, device has {device['qubits']}"
        return base

    model = device["model"]
    if model == "per_shot":
        base.usd = round(device["per_task"] + shots * device["per_shot"], 4)
    elif model == "per_second":
        runtime = device["runtime"]
        seconds = runtime["overhead_s"] + shots * (
            runtime["per_shot_s"] + profile.depth * runtime["per_layer_s"]
        )
        base.usd = round(seconds * device["per_second"], 4)
    elif model == "gate_shot":
        gate_cost = shots * (
            profile.n_1q_gates * device["rate_1q"]
            + profile.n_2q_effective * device["rate_2q"]
        )
        base.usd = round(device["min_program"] + gate_cost, 4)
    elif model == "hqc":
        hqc = 5 + shots * (
            profile.n_1q_gates + 10 * profile.n_2q_effective + 5 * profile.n_spam
        ) / 5000
        per_unit = device.get("per_unit")
        if per_unit is not None:
            base.usd = round(hqc * per_unit, 4)
        else:
            base.units = f"{hqc:.1f} {device['unit']}"
    else:  # pragma: no cover - guarded by catalog authoring
        raise ValueError(f"unknown pricing model {model!r} for {provider_id}:{device_id}")
    return base


def _merge_units(a: str, b: str) -> str:
    if not (a and b):
        return a or b
    va, unit = a.split(" ", 1)
    vb, _ = b.split(" ", 1)
    return f"{float(va) + float(vb):.1f} {unit}"
