# Extending Qontinuum with plugins

Qontinuum keeps Qiskit's `QuantumCircuit` as its single canonical intermediate
representation (IR). Everything in the core — the `@qtest` runner, cost
estimation, routing, snapshots — speaks that IR. The **edges** that touch the
outside world are pluggable, so you can add a hardware provider, a simulator
backend, or a new source SDK **without forking Qontinuum**.

| Kind | Protocol | Powers | Entry-point group |
|---|---|---|---|
| **Provider** | `ProviderPlugin` | `qont run --on <name>:<device>` | `qontinuum.providers` |
| **Backend** | `BackendPlugin` | `@qtest(backend="<name>:<arg>")` | `qontinuum.backends` |
| **SDK** | `SDKPlugin` | `load_circuit(<foreign object>)` | `qontinuum.sdks` |

The built-ins (`ibm`, `braket`, `aer`, `qiskit`, `cirq`, `pennylane`) are
themselves ordinary plugins — reading
[`qontinuum/plugins/builtins.py`](https://github.com/XTanishkX/quantum/blob/main/src/qontinuum/plugins/builtins.py)
is the fastest way to learn the shape.

## How discovery works

Discovery is a hybrid, and deliberately robust:

- **Built-ins** are registered in code and are *always* present.
- **Third-party plugins** are found through Python
  [entry points](https://packaging.python.org/en/latest/specifications/entry-points/).
  Install a package that declares one and `qont` picks it up — no core edits.
- A broken or misdeclared plugin becomes an **unavailable record** carrying its
  error. It never crashes discovery or the CLI. Inspect the state anytime:

```console
$ qont plugin list          # everything discovered, built-in and installed
$ qont plugin show ibm --kind provider
$ qont plugin doctor        # what's ready, what needs an extra, what's broken
```

`qont plugin doctor` exits non-zero **only** when a built-in fails to load
(real breakage). A third-party plugin that merely needs an optional dependency
is reported with the exact `pip install` line, but does not fail the check.

## Writing an SDK plugin

An SDK plugin converts a foreign circuit object *into* the Qiskit IR. It needs
`name`, a `matches()` that must never raise, and a `to_qiskit()`:

```python
# my_sdk_plugin/__init__.py
from qiskit import QuantumCircuit

class MySDK:
    name = "mysdk"
    requires = ("mysdk",)          # importable modules it needs to function
    summary = "MySDK circuits via its OpenQASM exporter."

    def matches(self, source) -> bool:
        return (type(source).__module__ or "").startswith("mysdk")

    def to_qiskit(self, source) -> QuantumCircuit:
        from qontinuum.circuits.loader import CircuitLoadError, _load_qasm
        try:
            return _load_qasm(source.to_qasm(), origin="mysdk")
        except Exception as exc:
            raise CircuitLoadError(f"could not convert MySDK circuit: {exc}") from exc

mysdk = MySDK()
```

Declare the entry point in your package's `pyproject.toml`:

```toml
[project.entry-points."qontinuum.sdks"]
mysdk = "my_sdk_plugin:mysdk"
```

After `pip install`, `load_circuit(<a MySDK circuit>)` — and therefore `@qtest`
functions returning one — just works. SDK plugins are tried in order; the first
whose `matches()` returns `True` wins.

## Writing a provider plugin

A provider plugin submits circuits to real hardware. `build_adapter()` returns
an object with a `target: str`, a `catalog_device: tuple[str, str]`, and a
`submit(circuit, shots) -> dict[str, int]` method (see the `HardwareAdapter`
protocol in `qontinuum.hardware.base`):

```python
class MyProvider:
    name = "acme"
    catalog_key = "acme"                 # provider id its devices price under
    requires = ("acme_sdk",)
    summary = "ACME Quantum QPUs."

    def build_adapter(self, device: str):
        from qontinuum.hardware.base import HardwareError
        try:
            from acme_sdk import AcmeClient
        except ImportError as exc:
            raise HardwareError("pip install acme_sdk to run on ACME") from exc
        return AcmeAdapter(device)       # your HardwareAdapter implementation

    def catalog_fragment(self):          # optional: ship pricing + routing data
        return {
            "display": "ACME Quantum",
            "devices": {
                "acme_one": {
                    "display": "ACME One", "qubits": 20,
                    "model": "per_shot", "per_task": 0.10, "per_shot": 0.001,
                    "quality": {"error_1q": 3e-4, "error_2q": 4e-3,
                                "error_readout": 6e-3, "connectivity": "all_to_all"},
                },
            },
        }
```

```toml
[project.entry-points."qontinuum.providers"]
acme = "my_acme_plugin:MyProvider"
```

The optional `catalog_fragment()` lets a provider ship **execution and pricing
together**: return `{"display": ..., "devices": {...}}` and those devices show
up in `qont cost`, `qont route`, and `qont device list`. Bundled catalog
devices always win a key collision, so a plugin can only add, never override,
the shipped pricing data. Pricing uses the catalog's fixed models
(`per_shot`, `per_second`, `gate_shot`, `hqc`) — see
[Cost models](cost-models.md).

## Writing a backend plugin

A backend plugin builds a local simulator from the part of the spec after
`name:`. For `backend="acme:fast"`, the registry calls your `build("fast")`;
for a bare `"acme"` spec the argument is the empty string. Return anything Aer-
compatible (supports `transpile` and `.run(...)`):

```python
class MyBackend:
    name = "acme"
    requires = ()
    summary = "ACME's local noise simulator."

    def build(self, arg: str):
        from qiskit_aer import AerSimulator
        return AerSimulator()            # configure from `arg` as you like
```

```toml
[project.entry-points."qontinuum.backends"]
acme = "my_acme_plugin:MyBackend"
```

## Contract notes

- **Entry point targets** may be a plugin *instance*, or a class/callable that
  the registry instantiates with no arguments.
- **`name`** is the canonical key used for resolution (the `--on` scheme, the
  `backend=` prefix). It — not the entry-point label — decides collisions. A
  third-party plugin whose `name` matches a built-in **shadows** it; `qont
  plugin list` flags this.
- **Keep imports lazy.** Import your heavy SDK inside the methods, not at module
  top level, so importing your plugin is cheap and a missing optional
  dependency degrades gracefully (reported by `qont plugin doctor`) instead of
  crashing.
- **`matches()` must not raise.** A plugin that raises there is skipped during
  loading, not fatal.
