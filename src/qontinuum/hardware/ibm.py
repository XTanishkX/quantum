"""Submit circuits to IBM Quantum hardware via Qiskit Runtime SamplerV2."""

from __future__ import annotations

from qiskit import QuantumCircuit

from qontinuum.assertions.stats import normalize_counts
from qontinuum.hardware.base import HardwareError

_INSTALL_HINT = "pip install 'qontinuum[ibm]' and save an IBM Quantum account first"


class IBMAdapter:
    catalog_device = ("ibm", "heron_payg")

    def __init__(self, backend_name: str):
        self.target = backend_name if backend_name.startswith("ibm_") else f"ibm_{backend_name}"
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
        except ImportError as exc:
            raise HardwareError(f"qiskit-ibm-runtime not installed; {_INSTALL_HINT}") from exc
        try:
            self._service = QiskitRuntimeService()
            self._backend = self._service.backend(self.target)
        except Exception as exc:
            raise HardwareError(
                f"could not connect to IBM backend {self.target!r}: {exc}; {_INSTALL_HINT}"
            ) from exc

    def submit(self, circuit: QuantumCircuit, shots: int) -> dict[str, int]:
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
        from qiskit_ibm_runtime import SamplerV2

        pm = generate_preset_pass_manager(optimization_level=1, backend=self._backend)
        isa_circuit = pm.run(circuit)
        sampler = SamplerV2(mode=self._backend)
        try:
            job = sampler.run([isa_circuit], shots=shots)
            pub_result = job.result()[0]
        except Exception as exc:
            raise HardwareError(f"IBM job failed on {self.target}: {exc}") from exc
        # join_data() merges all classical registers into one BitArray.
        counts = pub_result.join_data().get_counts()
        return normalize_counts(counts)
