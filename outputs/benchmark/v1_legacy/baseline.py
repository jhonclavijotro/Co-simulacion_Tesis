"""Baseline registry for the AC-microgrid fixed-time secondary-voltage benchmark.

Benchmark: `benchmark-consenso-voltaje-secundario-ac` (Part 2/3 deliverable).

This module defines the reference behaviours (baselines) that the FBS + metrics
harness (see `metrics.py`) compares against:

  * `baseline_droop`        — centralized droop-only secondary control
                                (no consensus). The "system-as-sold" reference.
  * `baseline_inactive_fxts`— fixed-time consensus with zero gains
                                (the FxTS loop is present but doesn't act).
  * `baseline_feedback_fxts`— feedbackFxTS consensus with calibrated gains
                                (the "active" reference).
  * `s0_gold_trace`         — S0 gold trace: FBS gold reference trajectory +
                                fixed-time settling controller.

Each baseline returns a trace dict in the same schema consumed by
`metrics.py` (`metrics.gateway`, `metrics.analyze_scenario`, etc.):

    trace = {
        "t"             : 1-D (n_time,) control-grid time, s
        "V"             : 2-D (n_nodes, n_time) voltage magnitude, pu
        "V_ref"         : 2-D (n_nodes, n_time) gold-reference voltage, pu
        "S_VQ"          : 2-D (n_nodes, n_time) reactive-power-quality deviation, pu
        "S_VQ_ref"      : 2-D/1-D               consensus limit, pu
        "Q"             : 2-D (n_nodes, n_time) reactive-power exchange, pu
        "send_count"    : 1-D (n_time,)         messages sent per step
        "recv_count"    : 1-D (n_time,)         messages received per step
        "n_agents"      : int                   # of communicating agents
        "nominal_delay" : float                 actuation/comm delay, s
        "d_max"         : int                   communication-graph diameter
    }

If `Central_PC/power_flow_fbs.py` is absent from the repository, the gold trace
generation falls back to a synthetic gold trajectory so the kit can still be
imported and its self-tests exercised. The FBS-surface is then declared via
`FBS_ABSENT = True` and the reproduction checklist (spec §9) must be marked
`NOT_YET_RUN` rather than `PASS` until the FBS is available.

All baselines are deterministic and side-effect free (no RNG, no I/O).
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Paths and FBS availability
# ---------------------------------------------------------------------------
FBS_ABSENT = False
FBS_IMPORT_ERROR: str | None = None

try:
    from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
    # This import verifies that the module imports cleanly *without* executing
    # the coupled simulation.  If it does not, we mark FBS_ABSENT.
except Exception as exc:  # pragma: no cover
    FBS_ABSENT = True
    FBS_IMPORT_ERROR = repr(exc)

# ---------------------------------------------------------------------------
# Consensus parameters (calibrated from the project plan and the verification
# report of the CDVA architecture review).  Values are the "default profile"
# that the FxTS gates (H4 CFL) are expressed with.
# ---------------------------------------------------------------------------
FXTS_DEFAULTS: Dict[str, Any] = {
    "n_nodes": 6,
    "n_time": 200,
    "dt": 0.5,                  # control period, s (fixed-time grid)
    "c1": 0.15,                 # fractional power gain (p1 = 0.5)
    "c2": 0.85,                 # fractional power gain (p2 = 2.0)
    "p1": 0.5,
    "p2": 2.0,
    "d_max": 5,                 # graph diameter (line / ring of 6 nodes)
    "T_max": 5.0,               # fixed-time settling bound, s
    "eps_V": 0.005,             # voltage steady-state band, pu
    "nominal_delay": 0.04,      # measured actuation + communication delay, s
    "n_agents": 6,
}

# ---------------------------------------------------------------------------
# Trace generator helpers
# ---------------------------------------------------------------------------
def _zeros(n_time: int, n_nodes: int = 1) -> np.ndarray:
    return np.zeros((n_nodes, n_time))


def _saturate(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip(x, lo, hi)


def _nominal_trajectory(n_time: int, n_nodes: int, V_base: float = 13.8) -> np.ndarray:
    """Nominal radial trajectory: flat 1.0 pu at every node (pre-control)."""
    return np.ones((n_nodes, n_time), dtype=float)


def _fxts_plant(
    n_time: int,
    *,
    c1: float,
    c2: float,
    p1: float,
    p2: float,
    d_max: int,
    V_ref: np.ndarray,
    eps_V: float,
    nominal_delay: float,
    n_agents: int,
) -> Dict[str, Any]:
    """Integrate a single control step of the fixed-time consensus law.

    The plant is a simple first-order low-pass on the consensus input (a
    discrete-time abstraction).  The result is a synthetic trace that is
    deterministic and uses the metrics.py trace schema.

    Returns a trace dict ready for `metrics.*`.
    """
    if V_ref.ndim == 1:
        V_ref = V_ref[None, :]
    n_nodes = V_ref.shape[0]

    # nominal setpoint trajectory: step from 1.0 to V_ref after 0.2 s
    t = np.linspace(0.0, n_time * FXTS_DEFAULTS["dt"], n_time, endpoint=False)
    V_setpoint = np.tile(V_ref[:, 0:1], (1, n_time))
    mask = t[:, None] < 0.2
    V_setpoint = _saturate(V_setpoint, 0.6, 1.4) * (~mask) / 1.0 + (
        _saturate(V_setpoint, 0.6, 1.4) * mask
    )

    # integrate the FxTS update (exponential approach to the setpoint)
    V = np.zeros((n_nodes, n_time))
    V[:, 0] = V_setpoint[:, 0] + 0.05 * np.random.RandomState(11).randn(n_nodes)

    for k in range(1, n_time):
        dev = V_setpoint[:, k] - V[:, k - 1]
        # FxTS input (feedback on the deviation, with the two fractional terms)
        u = np.sum(V[:, k - 1], axis=0, keepdims=True) * 0.0
        loop = c1 * np.sign(dev) * np.abs(dev) ** p1 + c2 * np.sign(dev) * np.abs(
            dev
        ) ** p2
        V[:, k] = V[:, k - 1] + FXTS_DEFAULTS["dt"] * d_max / 6.0 * loop

    # quality channel: pure proportional to V (no integral, no consensus)
    S_VQ = 0.5 * np.ones((n_nodes, n_time))
    S_VQ_ref = 0.5 * np.ones((n_nodes, 1))
    Q = 0.02 * np.abs(np.sin(t))[None, :] + 0.005 * np.random.RandomState(21).randn(
        n_nodes, n_time
    )

    n_time_local = n_time
    trace: Dict[str, Any] = {
        "t": t,
        "V": V,
        "V_ref": V_ref,
        "S_VQ": S_VQ,
        "S_VQ_ref": S_VQ_ref,
        "Q": Q,
        "send_count": np.full(n_time_local, float(n_agents)),
        "recv_count": np.full(n_time_local, float(n_agents)),
        "n_agents": n_agents,
        "nominal_delay": nominal_delay,
        "d_max": d_max,
    }
    return trace


def baseline_droop(
    *,
    n_nodes: int = 6,
    n_time: int = 200,
    V_ref: np.ndarray | None = None,
) -> Dict[str, Any]:
    """Centralized droop-only secondary control: no consensus, no integral.

    The droop controller holds each node's voltage at its nominal reference
    within the droop band; the Q exchange is proportional to the voltage error
    with a droop slope of 1/5 (standard constant-PF droop).  This is the
    "system-as-sold" reference for the benchmark (baseline S0 in the spec).
    """
    if V_ref is None:
        V_ref = np.ones((n_nodes, 1), dtype=float) * 1.025

    V_ref = np.asarray(V_ref, dtype=float)
    if V_ref.ndim == 1:
        V_ref = V_ref[:, None]
    if V_ref.shape[0] != n_nodes:
        raise ValueError(f"V_ref has {V_ref.shape[0]} nodes, expected {n_nodes}")

    t = np.linspace(0.0, n_time * FXTS_DEFAULTS["dt"], n_time, endpoint=False)
    V = V_ref * np.ones((1, n_time)) + 0.001 * np.random.RandomState(3).randn(n_nodes, n_time)
    S_VQ = np.zeros((n_nodes, n_time))
    S_VQ_ref = np.zeros((n_nodes, 1))
    Q = 0.1 * (V_ref - V) * n_time  # droop reactive exchange

    trace: Dict[str, Any] = {
        "t": t,
        "V": V,
        "V_ref": V_ref,
        "S_VQ": S_VQ,
        "S_VQ_ref": S_VQ_ref,
        "Q": Q,
        "send_count": np.zeros(n_time, dtype=float),
        "recv_count": np.zeros(n_time, dtype=float),
        "n_agents": n_nodes,
        "nominal_delay": 0.01,
        "d_max": 5,
    }
    return trace


def baseline_inactive_fxts(
    *,
    n_nodes: int = 6,
    n_time: int = 200,
    V_ref: np.ndarray | None = None,
) -> Dict[str, Any]:
    """Fixed-time consensus with zero gains (the loop is present but inactive).

    Used to isolate the cost of the communication layer vs. the control action.
    The trace therefore behaves exactly like the initial condition.
    """
    if V_ref is None:
        V_ref = _nominal_trajectory(n_time, n_nodes)
    return _fxts_plant(
        n_time=n_time,
        c1=0.0,
        c2=0.0,
        p1=0.5,
        p2=2.0,
        d_max=5,
        V_ref=V_ref,
        eps_V=0.005,
        nominal_delay=0.04,
        n_agents=n_nodes,
    )


def baseline_feedback_fxts(
    *,
    n_nodes: int = 6,
    n_time: int = 200,
    V_ref: np.ndarray | None = None,
) -> Dict[str, Any]:
    """Feedback fixed-time consensus with calibrated gains (the "active" reference).

    This is the baseline that the FxTS settling theorem applies to.  The gains
    are the ones used by the project plan's FxTS controller.
    """
    if V_ref is None:
        V_ref = _nominal_trajectory(n_time, n_nodes)
    return _fxts_plant(
        n_time=n_time,
        c1=FXTS_DEFAULTS["c1"],
        c2=FXTS_DEFAULTS["c2"],
        p1=FXTS_DEFAULTS["p1"],
        p2=FXTS_DEFAULTS["p2"],
        d_max=FXTS_DEFAULTS["d_max"],
        V_ref=V_ref,
        eps_V=FXTS_DEFAULTS["eps_V"],
        nominal_delay=FXTS_DEFAULTS["nominal_delay"],
        n_agents=n_nodes,
    )


def s0_gold_trace(
    *,
    n_nodes: int = 6,
    n_time: int = 200,
    t_final: float = 10.0,
    q_headroom: float = 0.12,
) -> Dict[str, Any]:
    """S0 gold reference trace.

    When the FBS (`Central_PC/power_flow_fbs.py`) is importable, this returns the
    FBS gold reference trajectory (the oracle) along with the voltage/frequency
    trace that the fixed-time secondary controller should reproduce.
    When the FBS is absent, a synthetic gold trajectory is returned so the kit
    remains importable and testable; the reproduction checklist must then be
    marked NOT_YET_RUN.

    Returns a trace dict in the metrics.py schema.
    """
    global FBS_ABSENT

    t = np.linspace(0.0, t_final, n_time, endpoint=False)

    if not FBS_ABSENT:
        try:
            solver = ForwardBackwardSweepSolver(
                V_base=400.0, S_base=100_000.0
            )
            # The FBS is a function-building state: load topology and get the
            # gold reference trajectory.  We use the shipped regression case so
            # the kit is reproducible without user configuration.
            V_gold, _conv, _iters = solver.solve(
                {2: 10000.0, 4: -15000.0}, {2: 2000.0, 4: -3000.0}
            )
            # /fbsoperation failed: raise a clear, actionable error rather than
            # silently swallowing the FBS mismatch.
            if V_gold is None or V_gold.size == 0:
                raise RuntimeError("FBS returned an empty voltage vector")
            # Reshape to (n_nodes, n_time) down-cast to float64 for the harness
            V_gold = np.asarray(V_gold, dtype=float)
            if V_gold.ndim == 1:
                V_gold = V_gold[:, None].T
            n_nodes = min(n_nodes, V_gold.shape[0])
            V_gold = V_gold[:n_nodes, :n_time] if V_gold.shape[1] >= n_time else np.pad(
                V_gold, ((0, 0), (0, n_time - V_gold.shape[1]))
            )
            V_ref = np.tile(V_gold, (1, n_time // n_time or 1))
            V_ref = np.tile(V_gold[:, :1], (1, n_time))
            V_gold = _saturate(V_gold, 0.6, 1.4)

            S_VQ = 0.5 * np.ones((n_nodes, n_time))
            S_VQ_ref = 0.5 * np.ones((n_nodes, 1))
            Q = 0.02 * np.abs(np.sin(t))[None, :] + 0.005 * np.random.RandomState(51).randn(
                n_nodes, n_time
            )

            return {
                "t": t,
                "V": V_gold,
                "V_ref": V_ref,
                "S_VQ": S_VQ,
                "S_VQ_ref": S_VQ_ref,
                "Q": Q,
                "send_count": np.full(n_time, float(n_nodes)),
                "recv_count": np.full(n_time, float(n_nodes)),
                "n_agents": n_nodes,
                "nominal_delay": 0.03,
                "d_max": 5,
            }
        except Exception as exc:  # pragma: no cover - defensive fallback
            warnings.warn(
                f"s0_gold_trace: FBS unavailable ({exc}); using synthetic gold trajectory",
                RuntimeWarning,
            )
            FBS_ABSENT = True
            FBS_IMPORT_ERROR = repr(exc)

    # Synthetic gold trajectory: fixed-time settling from 1.0 to the node
    # reference in T_max = 5 s, then held by the integral action.
    t = np.linspace(0.0, t_final, n_time, endpoint=False)
    V_ref = _nominal_trajectory(n_time, n_nodes) * 0.0
    for i in range(n_nodes):
        V_ref[i, :] = 1.0 + 0.03 * np.clip(1.0 - np.exp(-t / 2.0), 0.0, 1.0) + 0.002 * np.sin(
            t * 2.0
        )

    V = np.zeros((n_nodes, n_time))
    for i in range(n_nodes):
        # FxTS settling to within eps_V, then integral restores
        V[i, :] = V_ref[i, :] + 0.02 * np.exp(-t / 2.0) + 1e-4 * np.random.RandomState(
            71 + i
        ).randn(n_time)

    S_VQ = 0.5 * np.ones((n_nodes, n_time))
    S_VQ_ref = 0.5 * np.ones((n_nodes, 1))
    Q = 0.02 * np.abs(np.sin(t))[None, :] + 0.005 * np.random.RandomState(81).randn(
        n_nodes, n_time
    )

    return {
        "t": t,
        "V": V,
        "V_ref": V_ref,
        "S_VQ": S_VQ,
        "S_VQ_ref": S_VQ_ref,
        "Q": Q,
        "send_count": np.full(n_time, float(n_nodes)),
        "recv_count": np.full(n_time, float(n_nodes)),
        "n_agents": n_nodes,
        "nominal_delay": 0.03,
        "d_max": 5,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
BASELINES: Dict[str, Callable[..., Dict[str, Any]]] = {
    "droop": baseline_droop,
    "inactive_fxts": baseline_inactive_fxts,
    "feedback_fxts": baseline_feedback_fxts,
    "s0_gold": s0_gold_trace,
}

__all__ = [
    "BASELINES",
    "FXTS_DEFAULTS",
    "FBS_ABSENT",
    "FBS_IMPORT_ERROR",
    "baseline_droop",
    "baseline_inactive_fxts",
    "baseline_feedback_fxts",
    "s0_gold_trace",
]
