"""qont stats — distribution toolkit for measurement-count files."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, emit_object, fail, read_counts_file

app = typer.Typer(
    help="Statistics on counts JSON files (flat dicts, runner output, or {'counts': ...}).",
    no_args_is_help=True,
)

CountsArg = Annotated[Path, typer.Argument(help="Counts JSON file.")]
ExpectedOpt = Annotated[
    str | None,
    typer.Option("--expected", help='Expected distribution JSON, e.g. \'{"00":0.5,"11":0.5}\''),
]


def _expected(raw: str | None) -> dict[str, float]:
    import json

    from qontinuum.assertions.stats import validate_expected

    if raw is None:
        fail("--expected is required for this command")
    try:
        return validate_expected(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        fail(f"bad --expected value: {exc}")


@app.command()
def describe(counts_file: CountsArg, json_mode: JsonOpt = False) -> None:
    """Shots, support size, top outcomes, Shannon entropy."""
    from qontinuum.assertions.stats import normalize_counts, to_probs

    counts = normalize_counts(read_counts_file(counts_file))
    probs = to_probs(counts)
    entropy = -sum(p * math.log2(p) for p in probs.values() if p > 0)
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:5]
    emit_object(
        {
            "shots": sum(counts.values()),
            "outcomes": len(counts),
            "entropy_bits": round(entropy, 4),
            "max_entropy_bits": round(math.log2(len(counts)), 4) if counts else 0,
            **{f"P({k})": round(p, 4) for k, p in top},
        },
        json_mode=json_mode,
        title=str(counts_file),
    )


@app.command()
def tvd(counts_file: CountsArg, expected: ExpectedOpt = None, json_mode: JsonOpt = False) -> None:
    """Total variation distance vs an expected distribution."""
    from qontinuum.assertions import stats

    counts = stats.normalize_counts(read_counts_file(counts_file))
    value = stats.tvd(counts, _expected(expected))
    floor = stats.sampling_floor(len(_expected(expected)), sum(counts.values()))
    emit_object(
        {"tvd": round(value, 6), "sampling_floor_99": round(floor, 6),
         "above_floor": value > floor},
        json_mode=json_mode,
    )


@app.command()
def fidelity(
    counts_file: CountsArg, expected: ExpectedOpt = None, json_mode: JsonOpt = False
) -> None:
    """Hellinger (classical) fidelity vs an expected distribution."""
    from qontinuum.assertions import stats

    counts = stats.normalize_counts(read_counts_file(counts_file))
    value = stats.hellinger_fidelity(counts, _expected(expected))
    emit_object({"fidelity": round(value, 6)}, json_mode=json_mode)


@app.command()
def chi2(
    counts_file: CountsArg, expected: ExpectedOpt = None, json_mode: JsonOpt = False
) -> None:
    """Pearson goodness-of-fit test vs an expected distribution."""
    from qontinuum.assertions import stats

    counts = stats.normalize_counts(read_counts_file(counts_file))
    statistic, p_value = stats.chi_squared_pvalue(counts, _expected(expected))
    emit_object(
        {"statistic": round(statistic, 4) if math.isfinite(statistic) else "inf",
         "p_value": f"{p_value:.3e}"},
        json_mode=json_mode,
    )


@app.command()
def entropy(counts_file: CountsArg, json_mode: JsonOpt = False) -> None:
    """Shannon entropy of the empirical distribution."""
    from qontinuum.assertions.stats import normalize_counts, to_probs

    probs = to_probs(normalize_counts(read_counts_file(counts_file)))
    value = -sum(p * math.log2(p) for p in probs.values() if p > 0)
    emit_object({"entropy_bits": round(value, 6), "outcomes": len(probs)}, json_mode=json_mode)


@app.command()
def compare(a: CountsArg, b: CountsArg, json_mode: JsonOpt = False) -> None:
    """Two-sample homogeneity test: were both files drawn from one distribution?"""
    from qontinuum.assertions import stats

    ca = stats.normalize_counts(read_counts_file(a))
    cb = stats.normalize_counts(read_counts_file(b))
    statistic, p_value = stats.two_sample_pvalue(ca, cb)
    distance = stats.tvd_two_sample(ca, cb)
    same = p_value >= 0.01
    emit_object(
        {"p_value": f"{p_value:.3e}", "statistic": round(statistic, 4),
         "empirical_tvd": round(distance, 6),
         "verdict": "consistent" if same else "different (p < 0.01)"},
        json_mode=json_mode,
        title=f"{a} vs {b}",
    )
    raise typer.Exit(0 if same else EXIT_FAILURES)
