"""Noisy simulators built from IBM device calibration data.

Two modes, selected by the backend spec string:

- ``ibm:<device>`` — offline. Uses the calibration snapshot bundled with
  ``qiskit-ibm-runtime``'s fake provider (real historical device data), so CI
  runs need no account and no network.
- ``ibm:<device>@live`` — online. Fetches the device's *current* calibration
  through a saved IBM Quantum account (free open plan) and simulates today's
  actual noise.

Both return an :class:`~qiskit_aer.AerSimulator` configured with the device's
noise model, basis gates, and coupling map, so transpilation targets the real
topology.
"""

from __future__ import annotations

import warnings

from qiskit_aer import AerSimulator

_INSTALL_HINT = (
    "IBM noise models need the optional dependency qiskit-ibm-runtime; "
    "install it with: pip install 'qontinuum[ibm]'"
)


class NoiseSourceError(RuntimeError):
    """The requested IBM device/calibration could not be resolved."""


def noisy_simulator(device: str) -> AerSimulator:
    """Build an Aer simulator with the named IBM device's noise profile."""
    name, _, mode = device.partition("@")
    if mode == "live":
        return _from_live_calibration(name)
    if mode:
        raise NoiseSourceError(f"unknown calibration mode {mode!r}; only '@live' is supported")
    return _from_bundled_snapshot(name)


def _normalize(name: str) -> str:
    return name.removeprefix("fake_").removeprefix("ibm_").lower()


def _from_bundled_snapshot(name: str) -> AerSimulator:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

            backends = FakeProviderForBackendV2().backends()
    except ImportError as exc:
        raise NoiseSourceError(_INSTALL_HINT) from exc

    wanted = _normalize(name)
    for backend in backends:
        if _normalize(backend.name) == wanted:
            return AerSimulator.from_backend(backend)

    available = ", ".join(sorted(_normalize(b.name) for b in backends))
    raise NoiseSourceError(
        f"no bundled calibration snapshot for {name!r}; available devices: {available}"
    )


def _from_live_calibration(name: str) -> AerSimulator:
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
    except ImportError as exc:
        raise NoiseSourceError(_INSTALL_HINT) from exc

    try:
        service = QiskitRuntimeService()
    except Exception as exc:
        raise NoiseSourceError(
            "no saved IBM Quantum account; run "
            "QiskitRuntimeService.save_account(channel='ibm_quantum_platform', token=...) "
            "once, or use the offline 'ibm:<device>' form"
        ) from exc

    device = name if name.startswith("ibm_") else f"ibm_{name}"
    try:
        backend = service.backend(device)
    except Exception as exc:
        raise NoiseSourceError(f"IBM Quantum has no backend named {device!r}: {exc}") from exc
    return AerSimulator.from_backend(backend)
