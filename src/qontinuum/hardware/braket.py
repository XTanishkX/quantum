"""Submit circuits to QPUs on AWS Braket.

Requires the optional dependencies (``pip install 'qontinuum[braket]'``) and
AWS credentials with Braket permissions in the environment.
"""

from __future__ import annotations

from qiskit import QuantumCircuit

from qontinuum.assertions.stats import normalize_counts
from qontinuum.hardware.base import HardwareError

_INSTALL_HINT = "pip install 'qontinuum[braket]' and configure AWS credentials"

# Catalog device key -> Braket device ARN.
DEVICE_ARNS = {
    "ionq_forte": "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-1",
    "rigetti_cepheus": "arn:aws:braket:us-west-1::device/qpu/rigetti/Cepheus-1-108Q",
    "iqm_garnet": "arn:aws:braket:eu-north-1::device/qpu/iqm/Garnet",
    "iqm_emerald": "arn:aws:braket:eu-north-1::device/qpu/iqm/Emerald",
}


class BraketAdapter:
    def __init__(self, device_key: str):
        if device_key not in DEVICE_ARNS:
            raise HardwareError(
                f"unknown Braket device {device_key!r}; "
                f"available: {', '.join(sorted(DEVICE_ARNS))}"
            )
        self.target = f"braket:{device_key}"
        self.catalog_device = ("braket", device_key)
        self._arn = DEVICE_ARNS[device_key]
        try:
            from braket.aws import AwsDevice
            from qiskit_braket_provider.providers.adapter import to_braket
        except ImportError as exc:
            raise HardwareError(
                f"braket SDK / qiskit-braket-provider not installed; {_INSTALL_HINT}"
            ) from exc
        self._to_braket = to_braket
        try:
            self._device = AwsDevice(self._arn)
        except Exception as exc:
            raise HardwareError(f"could not open Braket device {self._arn}: {exc}") from exc

    def submit(self, circuit: QuantumCircuit, shots: int) -> dict[str, int]:
        try:
            braket_circuit = self._to_braket(circuit)
            task = self._device.run(braket_circuit, shots=shots)
            counts = task.result().measurement_counts
        except Exception as exc:
            raise HardwareError(f"Braket job failed on {self.target}: {exc}") from exc
        # Braket bitstrings are big-endian (qubit 0 first); qiskit convention
        # is little-endian, so reverse to keep assertions consistent.
        return normalize_counts({k[::-1]: v for k, v in dict(counts).items()})
