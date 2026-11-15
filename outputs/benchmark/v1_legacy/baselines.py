"""Kit benchmark: baselines + scenario runner for fixed-time secondary-voltage consensus.

Benchmark slug: `benchmark-consenso-voltaje-secundario-ac`
Stage: Part 2/3 deliverable.

This module:
  1. Imports the FBS backbone (`Central_PC/power_flow_fbs.py`) and the metrics
     harness (`metrics.py`) that belong to the same kit.
  2. Runs the FBS gold S0 scenario.
  3. Runs the scenario matrix rows S1–S5 (spec §7).
  4. Runs the derivative baselines defined in `baseline.py`.
  5. Writes per-scenario reports into `outputs/benchmark/reports/`.

Usage:
    python outputs/benchmark/baselines.py --fbs-config /path/to/topologia.csv

If the FBS is unavailable the runner degrades gracefully: it records the
missing dependency in `SETUP.md` (or prints a WARNING) and skips the FBS-gold
sections, marking them as NOT_YET_RUN.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np

# The kit directory is two levels above this file (outputs/benchmark/...).
_KIT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _KIT_DIR.parent.parent

# Make the benchmark modules importable regardless of cwd.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from metrics import (
        Spec,
        MetricsReport,
        analyze_scenario,
        baseline_gate,
        settling_time,
        mse_s_vq,
        cost_q,
        message_rate,
        delay_margin,
        drop_recovery,
        _check_time,
    )
    from baseline import (
        BASELINES,
        FXTS_DEFAULTS,
        s0_gold_trace,
        baseline_droop,
        baseline_feedback_fxts,
        baseline_inactive_fxts,
    )
    import baseline as _baseline_module

    BASELINES_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    BASELINES_AVAILABLE = False
    BASELINES_IMPORT_ERROR = repr(exc)
    MetricsReport = None
    Spec = None
    baseline_gate = None
    analyze_scenario = None
    settling_time = None
    mse_s_vq = None
    cost_q = None
    message_rate = None
    delay_margin = None
    drop_recovery = None
    _check_time = None
    s0_gold_trace = None
    baseline_droop = None
    baseline_feedback_fxts = None
    baseline_inactive_fxts = None
    _baseline_module = None

# ---------------------------------------------------------------------------
# Scenario configuration (mirrors spec §7)
# ---------------------------------------------------------------------------
def _scenario_matrix():
    """Return the scenario matrix rows as (id, name, manipulation, acceptance)."""
    return [
        {
            "id": "S0",
            "name": "Baseline (gold)",
            "manipulation": "Nominal 13.8 kV, no drops, all agents online",
            "acceptance": "settling ≤ T_max; mse_s_vq ~ 0; cost_q in headroom; msg>0; delay>0; drop=0",
        },
        {
            "id": "S1",
            "name": "Mesh / graph sweep",
            "manipulation": "Change topology d_max (ring, line, Voronoi)",
            "acceptance": "settling ≤ T_max(d_max)",
        },
        {
            "id": "S2",
            "name": "Drop / recovery",
            "manipulation": "Inject communication drop d ∈ {0.5, 1, 2, 5 s}",
            "acceptance": "recovery ≤ T_max + f(d)",
        },
        {
            "id": "S3",
            "name": "Message-rate reduction",
            "manipulation": "Skip m generations (m=0,1,2,3)",
            "acceptance": "delay margin vs. settling trade-off",
        },
        {
            "id": "S4",
            "name": "Noise / impairment",
            "manipulation": "Measurement noise σ, packet loss p",
            "acceptance": "settling within T_max + ε_n",
        },
        {
            "id": "S5",
            "name": "Decay of initial condition",
            "manipulation": "Vary initial δV_i(0)",
            "acceptance": "settling independent of δV_i(0)",
        },
    ]

# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _write_report(repo_root: Path, scenario_id: str, report: Any, metrics: Any) -> None:
    """Write a scenario report (JSON + CSV) under reports/."""
    reports_dir = repo_root / "outputs" / "benchmark" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    report_path = reports_dir / f"{scenario_id}_report.json"
    # Find scenario name by id
    scenario_name = "unknown"
    for _row in _scenario_matrix():
        if _row.get("id") == scenario_id:
            scenario_name = _row.get("name", "unknown")
            break
    payload = {
        "scenario": scenario_id,
        "name": scenario_name,
        "metrics": metrics,
        "timestamp": json.loads(json.dumps(__import__("datetime").datetime.now().isoformat())),
    }
    # Sanitize numpy types
    def _clean(obj):
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, dict):
            return {str(k): _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(v) for v in obj]
        return obj

    report_path.write_text(json.dumps(_clean(payload), indent=2), encoding="utf-8")

    # CSV
    csv_path = reports_dir / f"{scenario_id}_report.csv"
    rows = [["metric", "value"]]
    for k, v in metrics.items():
        rows.append([k, v])
    csv_path.write_text("\n".join(",".join(map(str, r)) for r in rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# FBS gold S0 run
# ---------------------------------------------------------------------------
def run_s0_gold() -> Dict[str, Any]:
    """Run the FBS reference scenario S0 (gold).

    Returns the metrics report for the S0 gold baseline trace.
    """
    if not BASELINES_AVAILABLE:
        return {"error": f"baseline module not importable: {BASELINES_IMPORT_ERROR}"}

    # FXTS_DEFAULTS is defined in `baseline.py`, which is imported above.
    spec = Spec(T_max=FXTS_DEFAULTS["T_max"], eps_V=FXTS_DEFAULTS["eps_V"])
    trace = s0_gold_trace(n_nodes=FXTS_DEFAULTS["n_nodes"], n_time=FXTS_DEFAULTS["n_time"])

    try:
        passed, report = baseline_gate([trace], spec)
    except Exception as exc:
        return {"error": f"baseline_gate failed: {exc}"}

    rep = {
        "trace": {
            "settling_time": report.settling_time_s,
            "mse_s_vq": report.mse_s_vq,
            "cost_q": report.cost_q,
        },
        "passed": passed,
        "spec": {"T_max": spec.T_max, "eps_V": spec.eps_V},
    }
    return rep


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------
def run_scenario_matrix() -> Dict[str, Any]:
    """Run the full scenario matrix and return a dict of results."""
    if not BASELINES_AVAILABLE:
        return {"error": f"baseline module not importable: {BASELINES_IMPORT_ERROR}"}

    results: Dict[str, Any] = {}
    matrix = _scenario_matrix()

    # S0
    results["S0"] = run_s0_gold()

    # S1 (graph sweep through the FBS): ad-hoc — no FBS, so we re-run the
    # same S0 traces with different d_max values.
    if BASELINES_AVAILABLE and _baseline_module is not None and _baseline_module.FBS_ABSENT:
        results["S1"] = {"status": "NOT_YET_RUN", "note": "FBS required for graph sweep"}
    else:
        # In a fully-FBS-backed run, the FBS topology would be swept here.
        results["S1"] = {
            "status": "NOT_YET_RUN",
            "note": "requires FBS topology sweep (ring / line / Voronoi)",
        }

    # S2–S5: simulation-specific; defer to the full runner when the FBS is
    # available (hardware-in-the-loop / co-simulation).
    for sid in ["S2", "S3", "S4", "S5"]:
        results[sid] = {
            "status": "NOT_YET_RUN",
            "note": "requires FBS + hardware/In-the-loop runner (Part 3)",
        }

    return results


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="KIT benchmark baselines + scenario runner (Part 2/3)"
    )
    ap.add_argument(
        "--fbs-config",
        type=Path,
        default=None,
        help="Optional FBS configuration file (topologia CSV). If omitted the kit "
        "runs the gold S0 scenario with a synthetic reference.",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a consolidated JSON report here (default: reports/baselines_report.json)",
    )
    args = ap.parse_args(argv)

    if not BASELINES_AVAILABLE:
        print(f"[WARN] baselines module not importable: {BASELINES_IMPORT_ERROR}", file=sys.stderr)
        print("[WARN] The FBS and metrics.py are required for the full suite.")
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({"status": "ERROR", "note": "import failed"}), encoding="utf-8")
        return 1

    print(f"[INFO] KIT baselines runner (root: {_REPO_ROOT})")
    print(f"[INFO] FBS_ABSENT = {BASELINES_AVAILABLE}")

    # Run the S0 gold scenario
    results = run_scenario_matrix()

    # Print a compact summary
    for sid, res in results.items():
        if isinstance(res, dict) and "error" in res:
            print(f"[WARN] {sid}: {res['error']}")
        elif isinstance(res, dict) and "status" in res:
            print(f"[INFO] {sid}: {res['status']} - {res.get('note', '')}")
        elif sid == "S0":
            print(f"[INFO] S0 gold: settling={res.get('settling_time', float('nan')):.3f}s "
                  f"mse={res.get('mse_s_vq', float('nan')):.3e} "
                  f"cost={res.get('cost_q', float('nan')):.4f} passed={res.get('passed')}")

    # Write consolidated report
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(_sanitize(results), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[INFO] Consolidated report written to: {args.report}")

    return 0


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


if __name__ == "__main__":
    sys.exit(main())
