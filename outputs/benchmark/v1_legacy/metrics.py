"""Kit benchmark metrics harness.

Metrics for **"fixed-time consensus in the secondary voltage loop of an AC microgrid"**
(benchmark `benchmark-consenso-voltaje-secundario-ac`, Part 1/3).

Exports (by number, matching the spec §8):

    settling_time(trace, spec) -> (float, bounded_bool)
    mse_s_vq(trace, spec)      -> float
    cost_q(trace, spec)        -> float
    message_rate(trace, spec)  -> (float, float)   # (sustained, burst)
    delay_margin(...)          -> DelayMarginReport
    drop_recovery(trace, spec) -> DropRecoveryReport
    baseline_gate(traces, spec)-> (bool, MetricsReport)
    analyze_scenario(traces, spec)-> MetricsReport

Trace schema
------------
A canonical trace is a plain object/dict with, minimally:

    t                : 1D (n_time,)   control-grid time, s
    V                : 2D (n_nodes, n_time) voltage magnitude, pu
    V_ref            : 2D (n_nodes, n_time) gold-reference voltage, pu
    S_VQ             : 2D (n_nodes, n_time) reactive-power-quality deviation, pu
    S_VQ_ref         : 2D/1D            consensus limit of S_VQ, pu
    Q                : 2D (n_nodes, n_time) reactive-power exchange, pu
    send_count       : 1D (n_time,)     messages sent per control step
    recv_count       : 1D (n_time,)     messages received per control step
    n_agents         : int              number of communicating agents
    n_nodes          : int              (if not inferable)
    nominal_delay    : float            measured per-step actuation/comm delay, s
    d_max            : int              graph diameter (communication graph)

1-D data arrays are treated as a single node over time; 2-D arrays are (n_nodes, n_time).

All metrics are deterministic and side-effect free (no RNG, no I/O). Results are plain floats
or structured dataclasses. Seeding is the harness's responsibility.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def _as_matrix(x: np.ndarray, *, n_nodes: int | None = None) -> np.ndarray:
    """Normalize a data array to 2-D (n_nodes, n_time).

    1-D input  -> one node over time  (n_nodes = 1).
    2-D input  -> unchanged (n_time = x.shape[1]).
    """
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        return x[None, :]
    if n_nodes is not None and x.shape[0] != n_nodes:
        if x.shape[1] == n_nodes and x.shape[0] != 1:
            warnings.warn(
                "Trace matrix has first axis size %d but n_nodes=%d; assuming transpose."
                % (x.shape[0], n_nodes),
                stacklevel=2,
            )
            x = x.T
        elif x.shape[0] == n_nodes:
            pass
        else:
            raise ValueError(
                f"n_nodes={n_nodes} does not match array first-axis {x.shape[0]}."
            )
    return x


def _as_matrix1(x: np.ndarray, *, n_nodes: int | None = None) -> np.ndarray:
    """Like _as_matrix but forbid n-dim > 2."""
    m = _as_matrix(x, n_nodes=n_nodes)
    if m.ndim > 2:
        raise ValueError(f"trace matrix must be 1-D or 2-D, got {m.ndim}-D")
    return m


def _check_time(t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    if t.ndim != 1:
        raise ValueError("time 't' must be 1-D")
    if t.size < 2:
        raise ValueError("time 't' needs >= 2 samples")
    if not np.all(np.diff(t) > 0):
        raise ValueError("time 't' must be strictly increasing")
    return t


def _max_dev_nonuniform(V, Vref, t, eps_V):
    """Interpolation-based band-check for possibly non-uniform time grids."""
    t_grid = np.linspace(t[0], t[-1], max(len(t) * 10, 1001))
    Vg = np.column_stack([np.interp(t_grid, t, V[i, :]) for i in range(V.shape[0])])
    Vrg = np.column_stack([np.interp(t_grid, t, Vref[i, :]) for i in range(Vref.shape[0])])
    return np.nanmax(np.abs(Vg - Vrg), axis=0)


# --------------------------------------------------------------------------- #
# specification and report dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class Spec:
    """Benchmark / acceptance specification carried by the metric harness.

    Defaults mirror the consensus spec (δV/δω integral saturation bounds ±0.10 pu,
    ±π rad/s, εV = ±0.5%, predefined grid Δt = 500 ms, T_max = 5 s) -- values that
    should be carried over from the FBS/consensus calibration done in Part 2.
    """

    eps_V: float = 0.005          # voltage steady-state band, pu (±eps_V)
    eps_freq: float = 0.02
    eps_sq_vq: float = 1e-6       # MSE of S_VQ below which "zero error" is declared
    q_headroom: float = 1.20      # accepted reactive-cost ratio (cost_q ≤ headroom)
    q_norm_base: float = 1.0e3    # base kVar per node used in cost_q normalization
    message_window: float = 1.0   # s, sliding window for burst message rate
    minimal_rate: float = 1e-3    # messages/s/agent below which comm is "dead"
    delay_critical: float = 0.0   # margin must be > this to pass (s)
    T_max: float = 5.0            # fixed-time settling bound, s
    seed: int = 0                 # reserved for stochastic checks


@dataclass
class MetricsReport:
    """Aggregated metrics for one scenario (baseline gate or otherwise)."""

    name: str
    spec: Spec
    settling_time_s: float = np.nan
    settling_bounded: bool = False
    mse_s_vq: float = np.nan
    cost_q: float = np.nan
    msg_sustained: float = np.nan
    msg_burst: float = np.nan
    delay_margin_s: float = np.nan
    nominal_delay_s: float = np.nan
    admissible_delay_s: float = np.nan
    drop_count: int = 0
    drop_max_duration_s: float = np.nan
    drop_total_duration_s: float = np.nan
    recovery_times_s: list[float] = field(default_factory=list)
    passed: bool = False
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    def __bool__(self) -> bool:
        return bool(self.passed)


# --------------------------------------------------------------------------- #
# metric implementations
# --------------------------------------------------------------------------- #
def settling_time(trace: dict[str, np.ndarray], spec: Spec) -> tuple[float, bool]:
    """First time after which |V - V_ref| ≤ eps_V at *every* node, for the rest of the run.

    Returns (t_settle, bounded). Use `np.inf` when the band is never maintained.
    """
    t = _check_time(trace["t"])
    V = _as_matrix1(trace["V"])
    Vref = _as_matrix1(trace["V_ref"])
    if V.shape != Vref.shape:
        raise ValueError("V and V_ref must have the same shape")
    if V.size == 0:
        raise ValueError("V/V_ref must be non-empty")

    dt = np.diff(t)
    if np.all(dt > 0):
        max_dev = np.nanmax(np.abs(V - Vref), axis=0)          # (n_time,)
    else:
        max_dev = _max_dev_nonuniform(V, Vref, t, spec.eps_V)
    exceeds = max_dev > spec.eps_V
    if not exceeds.any():
        return float(t[0]), True
    last_exceed = int(np.flatnonzero(exceeds)[-1])
    if last_exceed + 1 >= V.shape[1]:
        # still exceeding at the very last sample -> never settles
        return float(np.inf), False
    # everything strictly after last_exceed stays in band -> settle at that next sample
    return float(t[last_exceed + 1]), True


def mse_s_vq(trace: dict[str, np.ndarray], spec: Spec) -> float:
    """Mean squared error of the S_VQ consensus variable about its consensus limit."""
    V = _as_matrix1(trace["S_VQ"])
    ref = _as_matrix1(trace["S_VQ_ref"])
    if V.shape != ref.shape:
        if ref.ndim == 1 and V.shape[0] != 1 and ref.size == V.shape[0]:
            ref = np.broadcast_to(ref[:, None], V.shape)
        elif ref.ndim == 2 and ref.shape[1] == 1 and V.shape[1] > 1:
            # e.g. per-node scalar limit replicated over time
            ref = np.broadcast_to(ref, V.shape)
        else:
            raise ValueError("S_VQ and S_VQ_ref must have matching shapes")
    n_time = V.shape[1]
    if n_time == 0:
        return float("nan")
    return float(np.mean((V - ref) ** 2))


def cost_q(trace: dict[str, np.ndarray], spec: Spec) -> float:
    """Normalized total reactive-power exchange, cost_Q = ∫Σ|Q_i|/(n·T·Q_base).

    A ratio ~ cost of servicing reactive power; larger = more loss/feed-in penalty.
    """
    Q = _as_matrix1(trace["Q"])
    t = _check_time(trace["t"])
    n_nodes, n_time = Q.shape
    if n_nodes == 0 or n_time == 0:
        return float("nan")
    integral = np.trapezoid(np.abs(Q).sum(axis=0), t)          # ∫ Σ|Q_i| dt
    denom = n_nodes * (t[-1] - t[0]) * spec.q_norm_base
    if denom <= 0:
        return float("nan")
    return float(integral / denom)


def message_rate(trace: dict[str, np.ndarray], spec: Spec) -> tuple[float, float]:
    """(sustained, burst) message rate per agent per second.

    `send_count` holds total messages per control step; divide by n_agents before
    converting from per-step to per-second. Burst over a sliding `message_window`.
    """
    send = np.asarray(trace.get("send_count", np.zeros_like(trace["t"])), dtype=float)
    t = _check_time(trace["t"])
    n_agents = int(trace.get("n_agents", 1))
    if n_agents <= 0:
        raise ValueError("n_agents must be a positive integer")
    if send.size != t.size:
        raise ValueError("send_count must align with time 't'")
    dt_step = float(np.median(np.diff(t))) if t.size > 1 else np.nan
    per_agent_per_step = send / n_agents
    sustained = float(np.mean(per_agent_per_step) / dt_step) if dt_step > 0 else float("nan")

    if send.size < 2:
        burst = sustained
    else:
        window_steps = max(int(round(spec.message_window / dt_step)), 1)
        window_steps = min(window_steps, send.size)
        rolling = np.convolve(per_agent_per_step, np.ones(window_steps) / window_steps,
                              mode="valid") / dt_step
        burst = float(np.max(rolling)) if rolling.size else sustained
    return sustained, burst


def delay_margin(
    *,
    spec: Spec,
    c1: float | None = None,
    c2: float | None = None,
    d_max: int | None = None,
    candidates: Sequence[tuple[float, dict[str, np.ndarray]]] | None = None,
    nominal_trace: dict[str, np.ndarray] | None = None,
) -> "DelayMarginReport":
    """Largest tolerable actuation/communication delay before closed-loop divergence.

    Two ways to evaluate it (pick one):

      * Analytic: supply the FxTS gains `c1`, `c2` and graph diameter `d_max`; the
        discrete CFL gate `δt·d_max·(c1+c2) < 1` yields the admissible delay
        `δt_max = 1/(d_max·(c1+c2))`. Requires control gains to exist.

      * Empirical: pass `candidates = [(delay_s, trace), ...]. Each trace is a plain
        benchmark trace (same schema as for the other metrics). The largest delay whose
        trace still settles (bounded settling_time, within eps_V) is the empirical
        delay margin.

    `nominal_trace` provides the measured per-step delay: its `nominal_delay` key
    becomes `nominal_delay_s` on the report.
    """
    if candidates is not None:
        return _delay_margin_empirical(candidates, spec, nominal_trace=nominal_trace)

    # analytic CFL-gate path
    if nominal_trace is None or c1 is None or c2 is None or d_max is None:
        missing = []
        if nominal_trace is None:
            missing.append("nominal_trace")
        if c1 is None:
            missing.append("c1")
        if c2 is None:
            missing.append("c2")
        if d_max is None:
            missing.append("d_max")
        raise ValueError(
            "analytic path requires (nominal_trace, c1, c2, d_max); empirical path "
            "requires (candidates,). Missing: " + ", ".join(missing)
        )
    nominal_delay = float(nominal_trace.get("nominal_delay", np.nan))
    admissible = _analytic_delay_margin(c1, c2, float(d_max))
    return DelayMarginReport(
        name="delay_margin",
        spec=spec,
        nominal_delay_s=nominal_delay,
        admissible_delay_s=admissible,
        delay_margin_s=(admissible - nominal_delay) if np.isfinite(admissible) else np.nan)


def _analytic_delay_margin(c1, c2, d_max) -> float:
    """δt_max = 1/(d_max·(c1+c2)) from the discrete CFL gate Δt·d_max(c1+c2) < 1."""
    c1 = float(c1); c2 = float(c2); d_max = float(d_max)
    if d_max <= 0 or (c1 + c2) <= 0:
        return float("nan")
    return 1.0 / (d_max * (c1 + c2))


def _delay_margin_empirical(
    candidates: Sequence[tuple[float, dict[str, np.ndarray]]],
    spec: Spec,
    nominal_trace: dict[str, np.ndarray] | None = None,
) -> "DelayMarginReport":
    """Empirical bracketing: largest candidate delay whose V trace stays in band."""
    cands = sorted([(float(d), tr) for d, tr in candidates], key=lambda x: x[0])
    if not cands:
        return DelayMarginReport(name="delay_margin", spec=spec,
                                  warnings=["no candidates supplied"])

    admissible = float("nan")
    for d, tr in cands:
        st, bounded = settling_time(tr, spec)
        if bounded and np.isfinite(st):
            admissible = d
        else:
            break

    # Refine across the bracketing pair if the coarse pass ended inside the list.
    if np.isnan(admissible) and len(cands) >= 2:
        for i in range(len(cands) - 1):
            st_hi, b_hi = settling_time(cands[i][1], spec)
            st_lo, b_lo = settling_time(cands[i + 1][1], spec)
            if b_hi and b_lo:
                admissible = max(cands[i][0], cands[i + 1][0])
            elif b_hi and not b_lo:
                lo_d, hi_d = cands[i][0], cands[i + 1][0]
                try:
                    if st_lo != st_hi:
                        frac = (spec.T_max - st_lo) / (st_lo - st_hi)
                        admissible = lo_d + frac * (hi_d - lo_d)
                    else:
                        admissible = hi_d
                except ZeroDivisionError:
                    admissible = lo_d
            else:
                continue

    nominal_delay = (
        float(nominal_trace.get("nominal_delay", np.nan)) if nominal_trace
        else (max(d for d, _ in cands) if cands else np.nan)
    )
    return DelayMarginReport(
        name="delay_margin",
        spec=spec,
        nominal_delay_s=nominal_delay,
        admissible_delay_s=admissible,
        delay_margin_s=(admissible - nominal_delay) if np.isfinite(admissible) else np.nan,
        warnings=[] if np.isfinite(admissible) else ["empirical margin: no settled candidate "
                                                      "found at or below the largest supplied delay"])


@dataclass
class DelayMarginReport:
    name: str
    spec: Spec
    nominal_delay_s: float = np.nan
    admissible_delay_s: float = np.nan
    delay_margin_s: float = np.nan
    warnings: list[str] = field(default_factory=list)


@dataclass
class DropRecoveryReport:
    name: str
    spec: Spec
    drop_count: int
    drop_max_duration_s: float
    drop_total_duration_s: float
    recovery_times_s: list[float] = field(default_factory=list)


def drop_recovery(trace: dict[str, np.ndarray], spec: Spec) -> "DropRecoveryReport":
    """Detect communication drops (recv_count → 0) and their recovery.

    Returns a DropRecoveryReport with drop_count, per-drop durations and the
    post-drop recovery settling time (time until |V-V_ref|≤eps_V holds again).
    """
    recv = np.asarray(trace.get("recv_count", np.zeros_like(trace["t"])), dtype=float)
    V = _as_matrix1(trace["V"])
    Vref = _as_matrix1(trace.get("V_ref", V * 0.0))
    t = _check_time(trace["t"])
    n_time = t.size
    if recv.size == 0:
        recv = np.zeros(n_time)
    if V.shape != Vref.shape:
        raise ValueError("V and V_ref mismatch in trace")

    # Drop Detection: recv stalls well below the nominal listening rate.
    threshold = max(float(np.percentile(recv, 99)) * 0.05, 1e-9) if recv.size else 0.0
    drop = recv < threshold

    intervals = _contiguous_intervals(drop)
    if not intervals:
        return DropRecoveryReport(name="drop_recovery", spec=spec,
                                   drop_count=0,
                                   drop_max_duration_s=0.0,
                                   drop_total_duration_s=0.0)

    dt = float(np.median(np.diff(t))) if n_time > 1 else 0.0
    recovery_times = []
    for start_idx, end_idx in intervals:
        # post-drop data: from end_idx (sample just after drop) to the end.
        sub_V = V[:, end_idx:]
        sub_Vref = Vref[:, end_idx:]
        sub_t = t[end_idx:]
        dt_sub = float(np.median(np.diff(sub_t))) if sub_V.shape[1] > 1 else 0.0
        st_s, bounded = _settling_sub(sub_V, sub_Vref, sub_t, spec.eps_V, dt_sub)
        recovery_times.append(st_s if bounded else np.inf)

    return DropRecoveryReport(
        name="drop_recovery", spec=spec,
        drop_count=len(intervals),
        drop_max_duration_s=float(max((end - start) * dt for start, end in intervals)),
        drop_total_duration_s=float(sum((end - start) * dt for start, end in intervals)),
        recovery_times_s=recovery_times)


def _contiguous_intervals(mask: np.ndarray) -> list[tuple[int, int]]:
    """Run-length encode a boolean mask into (start, end) half-open sample intervals."""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1) + 1
    starts = np.split(idx, breaks)
    ends = [int(s[-1]) + 1 for s in starts]
    return list(zip([int(s[0]) for s in starts], ends))


def _settling_sub(V, Vref, t, eps, dt_step):
    """Local settling helper for a slice of a trace (used by drop_recovery)."""
    if V.shape[0] == 0 or V.shape[1] == 0:
        return float("nan"), False
    if dt_step > 0 and np.all(np.diff(t) > 0):
        max_dev = np.nanmax(np.abs(V - Vref), axis=0)
    else:
        max_dev = _max_dev_nonuniform(V, Vref, t, eps)
    exceeds = max_dev > eps
    if not exceeds.any():
        return float(t[0]), True
    last_exceed = int(np.flatnonzero(exceeds)[-1])
    if last_exceed + 1 >= V.shape[1]:
        return float(np.inf), False
    return float(t[last_exceed + 1]), True


# --------------------------------------------------------------------------- #
# acceptance gate
# --------------------------------------------------------------------------- #
def baseline_gate(traces: Sequence[dict[str, np.ndarray]], spec: Spec) -> tuple[bool, MetricsReport]:
    """S0-gate: all criteria must pass on every trace.

    Criteria (with defaults):
      settling      ≤ spec.T_max
      mse_s_vq      ≤ spec.eps_sq_vq (zero-error in steady window)
      cost_q        ≤ spec.q_headroom
      message rate  > spec.minimal_rate
      delay margin  > spec.delay_critical
      drop/recover  drop_count == 0  (recovery_times purely inf → bounded)
    """
    rep = MetricsReport(name="baseline_gate", spec=spec)
    for i, tr in enumerate(traces):
        try:
            st, bounded = settling_time(tr, spec)
            rep.settling_time_s = st
            rep.settling_bounded = bounded
            rep.mse_s_vq = mse_s_vq(tr, spec)
            rep.cost_q = cost_q(tr, spec)
            su, b = message_rate(tr, spec)
            rep.msg_sustained, rep.msg_burst = su, b
            dm = delay_margin(nominal_trace=tr, spec=spec, c1=1.0, c2=1.0, d_max=5)
            rep.delay_margin_s = dm.delay_margin_s
            rep.nominal_delay_s = dm.nominal_delay_s
            rep.admissible_delay_s = dm.admissible_delay_s
            dr = drop_recovery(tr, spec)
            rep.drop_count = dr.drop_count
            rep.drop_max_duration_s = dr.drop_max_duration_s
            rep.drop_total_duration_s = dr.drop_total_duration_s
            rep.recovery_times_s.extend(dr.recovery_times_s)
        except Exception as exc:  # noqa: BLE001 - aggregate and report
            rep.warnings.append(f"trace[{i}] failed metric computation: {exc}")

    rep.passed = bool(
        np.isfinite(rep.settling_time_s) and rep.settling_time_s <= spec.T_max
        and np.isfinite(rep.mse_s_vq) and rep.mse_s_vq <= spec.eps_sq_vq
        and np.isfinite(rep.cost_q) and rep.cost_q <= spec.q_headroom
        and np.isfinite(rep.msg_sustained) and rep.msg_sustained > spec.minimal_rate
        and np.isfinite(rep.delay_margin_s) and rep.delay_margin_s > spec.delay_critical
        and rep.drop_count == 0
    )
    return rep.passed, rep


def analyze_scenario(
    traces: Sequence[dict[str, np.ndarray]], spec: Spec
) -> MetricsReport:
    """Run all six metrics over a scenario and bundle them into one report."""
    rep = MetricsReport(name="scenario", spec=spec)
    for i, tr in enumerate(traces):
        try:
            st, bounded = settling_time(tr, spec)
            rep.settling_time_s = st
            rep.settling_bounded = rep.settling_bounded or bounded
            rep.mse_s_vq = mse_s_vq(tr, spec)
            rep.cost_q = cost_q(tr, spec)
            su, b = message_rate(tr, spec)
            rep.msg_sustained, rep.msg_burst = su, b
            dm = delay_margin(nominal_trace=tr, spec=spec, c1=1.0, c2=1.0, d_max=5)
            rep.delay_margin_s = dm.delay_margin_s
            rep.nominal_delay_s = dm.nominal_delay_s
            rep.admissible_delay_s = dm.admissible_delay_s
            dr = drop_recovery(tr, spec)
            rep.drop_count += dr.drop_count
            rep.drop_max_duration_s = max(rep.drop_max_duration_s, dr.drop_max_duration_s)
            rep.drop_total_duration_s += dr.drop_total_duration_s
            rep.recovery_times_s.extend(dr.recovery_times_s)
        except Exception as exc:  # noqa: BLE001
            rep.warnings.append(f"trace[{i}] failed metric computation: {exc}")
    rep.passed = (
        np.isfinite(rep.settling_time_s) and rep.settling_time_s <= spec.T_max
        and np.isfinite(rep.mse_s_vq) and rep.mse_s_vq <= spec.eps_sq_vq
        and np.isfinite(rep.cost_q) and rep.cost_q <= spec.q_headroom
        and np.isfinite(rep.msg_sustained) and rep.msg_sustained > spec.minimal_rate
        and np.isfinite(rep.delay_margin_s) and rep.delay_margin_s > spec.delay_critical
        and rep.drop_count == 0
    )
    return rep


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Deterministic synthetic probe (no RNG in metrics).
    np.random.seed(0)
    n_nodes, n_time = 6, 200
    t = np.linspace(0, 10, n_time)
    V_true = np.repeat((1.0 + 0.005 * np.exp(-t[:, None] * 0.5)), n_nodes, axis=1).T  # (200,1)->(200,6)->(6,200)
    V_ref = np.repeat((1.0 + 0.001 * np.sin(t))[:, None], n_nodes, axis=1).T  # (200,6)->(6,200)
    V = V_true + 1e-4 * np.random.randn(n_nodes, n_time)
    S_VQ = 0.5 * np.ones((n_nodes, n_time)); S_VQ_ref = 0.5 * np.ones((n_nodes, 1))
    Q = 0.02 * np.abs(np.sin(t))[None, :] * np.ones((n_nodes, n_time))
    send = np.full(n_time, 10.0); recv = np.full(n_time, 10.0)
    recv[120:140] = 0.0  # artificial drop
    nominal_delay = 0.05

    tr = {
        "t": t, "V": V, "V_ref": V_ref,
        "S_VQ": S_VQ, "S_VQ_ref": S_VQ_ref,
        "Q": Q, "send_count": send, "recv_count": recv,
        "n_agents": 6, "nominal_delay": nominal_delay, "d_max": 5,
    }
    spec = Spec(T_max=5.0, eps_V=0.005, q_headroom=1.2, eps_sq_vq=1e-6, message_window=1.0)
    print("settling_time:", settling_time(tr, spec))
    print("mse_s_vq     :", mse_s_vq(tr, spec))
    print("cost_q       :", cost_q(tr, spec))
    print("msg_rate     :", message_rate(tr, spec))
    print("drop_recovery:", drop_recovery(tr, spec).__dict__)
    try:
        dm = delay_margin(spec=spec, c1=1.0, c2=1.0, d_max=5,
                          nominal_trace=tr)
        print("delay_margin :", dm.__dict__)
    except Exception as e:  # pragma: no cover
        print("delay_margin ERROR:", e)
