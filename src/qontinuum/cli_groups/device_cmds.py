"""qont device — the QPU fleet as seen from your terminal."""

from __future__ import annotations

import statistics
from typing import Annotated

import typer

from qontinuum.cli_util import JsonOpt, console, emit, emit_object, fail

app = typer.Typer(help="Browse, compare, and interrogate QPUs.", no_args_is_help=True)

DeviceArg = Annotated[str, typer.Argument(help="Catalog device id, e.g. rigetti_cepheus.")]
IBMDeviceArg = Annotated[str, typer.Argument(help="IBM device, e.g. manila or brisbane[@live].")]


def _catalog_devices() -> dict[str, dict]:
    from qontinuum.cost import load_catalog

    out: dict[str, dict] = {}
    for provider_id, provider in load_catalog()["providers"].items():
        for device_id, device in provider["devices"].items():
            out[device_id] = {"provider": provider["display"], "provider_id": provider_id, **device}
    return out


def _device_or_fail(device_id: str) -> dict:
    devices = _catalog_devices()
    if device_id not in devices:
        fail(f"unknown device {device_id!r}; run `qont device list`")
    return devices[device_id]


def _row(device_id: str, dev: dict) -> dict:
    quality = dev.get("quality") or {}
    return {
        "id": device_id,
        "provider": dev["provider"],
        "name": dev["display"],
        "qubits": dev["qubits"],
        "pricing": dev["model"],
        "err_2q": quality.get("error_2q"),
        "connectivity": quality.get("connectivity"),
    }


@app.command("list")
def list_cmd(json_mode: JsonOpt = False) -> None:
    """Every device in the pricing catalog."""
    rows = [_row(device_id, dev) for device_id, dev in sorted(_catalog_devices().items())]
    emit(rows, json_mode=json_mode, title="device catalog",
         columns=[("id", "ID"), ("provider", "Provider"), ("name", "Device"),
                  ("qubits", "Qubits"), ("pricing", "Pricing"),
                  ("err_2q", "2Q err"), ("connectivity", "Topology")],
         right_align={"qubits", "err_2q"})


@app.command()
def show(device: DeviceArg, json_mode: JsonOpt = False) -> None:
    """Full catalog card for one device."""
    dev = _device_or_fail(device)
    flat = {k: v for k, v in dev.items() if not isinstance(v, dict)}
    flat.update({f"quality.{k}": v for k, v in (dev.get("quality") or {}).items()})
    flat.update({f"runtime.{k}": v for k, v in (dev.get("runtime") or {}).items()})
    emit_object(flat, json_mode=json_mode, title=dev["display"])


@app.command()
def compare(a: DeviceArg, b: DeviceArg, json_mode: JsonOpt = False) -> None:
    """Two devices side by side."""
    ra, rb = _row(a, _device_or_fail(a)), _row(b, _device_or_fail(b))
    rows = [{"metric": key, a: ra[key], b: rb[key]} for key in ra if key != "id"]
    emit(rows, json_mode=json_mode, title=f"{a} vs {b}",
         columns=[("metric", "Metric"), (a, a), (b, b)])


@app.command()
def topology(device: DeviceArg) -> None:
    """Sketch the qubit connectivity."""
    dev = _device_or_fail(device)
    kind = (dev.get("quality") or {}).get("connectivity", "unknown")
    n = dev["qubits"]
    console.print(f"[bold]{dev['display']}[/bold] — {n} qubits, [cyan]{kind}[/cyan]")
    if kind == "all_to_all":
        console.print("  every qubit couples to every other (trapped-ion style);\n"
                      "  no SWAP routing overhead.")
    elif kind == "heavy_hex":
        console.print("  IBM heavy-hex lattice (degree <= 3):\n"
                      "    o - o - o\n"
                      "        |\n"
                      "    o - o - o\n"
                      "        |\n"
                      "    o - o - o\n"
                      "  expect ~1.6x two-qubit gate growth after routing.")
    elif kind == "square":
        console.print("  square lattice (degree <= 4):\n"
                      "    o - o - o\n"
                      "    |   |   |\n"
                      "    o - o - o\n"
                      "  expect ~1.4x two-qubit gate growth after routing.")
    elif kind == "linear":
        console.print("  linear chain: o - o - o - o; worst-case routing (~2x).")
    else:
        console.print("  connectivity not recorded in the catalog.")


@app.command()
def calib(
    device: IBMDeviceArg,
    limit: Annotated[int, typer.Option(help="Max qubits to display.")] = 10,
    json_mode: JsonOpt = False,
) -> None:
    """Per-qubit calibration table (T1/T2/readout) from bundled or @live data."""
    rows = _calibration_rows(device)
    emit(rows[:limit] if not json_mode else rows, json_mode=json_mode,
         title=f"calibration — {device} ({len(rows)} qubits)",
         columns=[("qubit", "Q"), ("t1_us", "T1 (µs)"), ("t2_us", "T2 (µs)"),
                  ("readout_err", "Readout err")],
         right_align={"t1_us", "t2_us", "readout_err"})


@app.command()
def drift(device: IBMDeviceArg, json_mode: JsonOpt = False) -> None:
    """Calibration weather report: today's live device vs the bundled snapshot.

    Requires a saved (free) IBM account for the live side.
    """
    name = device.partition("@")[0]
    bundled = _calibration_summary(name)
    live = _calibration_summary(f"{name}@live")
    rows = []
    for metric in bundled:
        a, b = bundled[metric], live.get(metric)
        change = (b - a) / a * 100 if (a and b is not None) else None
        rows.append({"metric": metric, "bundled": a, "live": b,
                     "change_pct": round(change, 1) if change is not None else None})
    emit(rows, json_mode=json_mode, title=f"calibration drift — {name}",
         columns=[("metric", "Metric"), ("bundled", "Bundled"), ("live", "Live"),
                  ("change_pct", "Δ %")], right_align={"bundled", "live", "change_pct"})


@app.command()
def queue(device: IBMDeviceArg) -> None:
    """Live queue depth for an IBM device (needs a saved account)."""
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
    except ImportError:
        fail("needs the [ibm] extra: pip install 'qontinuum[ibm]'")
    try:
        service = QiskitRuntimeService()
        name = device if device.startswith("ibm_") else f"ibm_{device}"
        backend = service.backend(name)
        status = backend.status()
    except Exception as exc:
        fail(f"could not reach IBM Quantum: {exc}")
    console.print(f"[bold]{name}[/bold]: {status.pending_jobs} pending jobs, "
                  f"operational={status.operational}")


@app.command()
def best(
    qubits: Annotated[int, typer.Option(help="Qubits your workload needs.")] = 2,
    budget: Annotated[float | None, typer.Option(help="Max USD for 1000 shots.")] = None,
    json_mode: JsonOpt = False,
) -> None:
    """Quick router: best devices for a qubit count and optional budget."""
    from qiskit import QuantumCircuit

    from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
    from qontinuum.router import rank, score_devices

    qc = QuantumCircuit(qubits)
    qc.h(0)
    for i in range(qubits - 1):
        qc.cx(i, i + 1)
    qc.measure_all()
    scores = rank(
        score_devices([profile_circuit(qc)], estimate_suite([(qc, 1000)]), load_catalog()),
        optimize="value",
    )
    rows = []
    for s in scores:
        if not s.feasible:
            continue
        if budget is not None and (s.usd is None or s.usd > budget):
            continue
        rows.append({"device": s.display, "provider": s.provider,
                     "success": s.success_prob, "usd_1000_shots": s.usd,
                     "usd_per_success": s.usd_per_success})
    emit(rows, json_mode=json_mode,
         title=f"best devices for a {qubits}-qubit entangling workload (1000 shots)",
         columns=[("device", "Device"), ("provider", "Provider"), ("success", "Success"),
                  ("usd_1000_shots", "Cost"), ("usd_per_success", "$/success")],
         right_align={"success", "usd_1000_shots", "usd_per_success"})


def _target_backend(device: str):
    from qontinuum.noise import NoiseSourceError

    name, _, mode = device.partition("@")
    try:
        if mode == "live":
            from qiskit_ibm_runtime import QiskitRuntimeService

            service = QiskitRuntimeService()
            return service.backend(name if name.startswith("ibm_") else f"ibm_{name}")
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

        wanted = name.removeprefix("fake_").removeprefix("ibm_").lower()
        for backend in FakeProviderForBackendV2().backends():
            if backend.name.removeprefix("fake_").removeprefix("ibm_").lower() == wanted:
                return backend
        raise NoiseSourceError(f"no bundled calibration for {name!r}")
    except ImportError:
        fail("needs the [ibm] extra: pip install 'qontinuum[ibm]'")
    except NoiseSourceError as exc:
        fail(str(exc))
    except Exception as exc:
        fail(f"could not load calibration for {device!r}: {exc}")


def _calibration_rows(device: str) -> list[dict]:
    backend = _target_backend(device)
    target = backend.target
    rows = []
    measure = target.get("measure", {}) if "measure" in target.operation_names else {}
    for q in range(backend.num_qubits):
        props = target.qubit_properties[q] if target.qubit_properties else None
        m = measure.get((q,))
        rows.append({
            "qubit": q,
            "t1_us": round(props.t1 * 1e6, 1) if props and props.t1 else None,
            "t2_us": round(props.t2 * 1e6, 1) if props and props.t2 else None,
            "readout_err": round(m.error, 4) if m and m.error is not None else None,
        })
    return rows


def _calibration_summary(device: str) -> dict[str, float | None]:
    rows = _calibration_rows(device)

    def med(key: str) -> float | None:
        vals = [r[key] for r in rows if r[key] is not None]
        return round(statistics.median(vals), 4) if vals else None

    return {"median_t1_us": med("t1_us"), "median_t2_us": med("t2_us"),
            "median_readout_err": med("readout_err")}
