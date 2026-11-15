# KIT Benchmark — Spec v1 (Part 1/3)

**Benchmark name:** `benchmark-consenso-voltaje-secundario-ac`
**Stage:** Part 1/3 — definition of the benchmark spec and metrics harness.
**Product of the benchmark:** `benchmark-spec.md` (this document) + `metrics.py` (metrics harness).
**Reference roadmaps:**
- `outputs/.plans/consenso-distribuido-voltaje-ac.md` (§12.2 consensus-block wiring, §9.2 secondary-control ledger),
- `Central_PC/power_flow_fbs.py` (gold function-building state + power-flow backbone),
- `finite_time_consensus.py` / `distributed_node_runner.py` (FxTS consensus + distributed runner, see project plan).

---

## 1. Objective

Build and validate a **benchmark that tests fixed-time consensus in the secondary voltage loop
of an AC microgrid**. The benchmark runs a *gold function-building state (FBS)* that is faithful to the
reference model `Central_PC/power_flow_fbs.py`, drives it with a **radial 6-node, 13.8 kV AC microgrid**,
and measures the closed-loop behavior of a **fixed-time (FxTS) distributed secondary voltage controller**.
The benchmark's success criterion is that the controller settles voltages **fixed-time** —
i.e., within a bound that does **not** depend on initial conditions or network topology — while
maintaining agreed quality/durability metrics.

The benchmark is the **gold** reference for later parts of the KIT suite: Part 2 wires the agent
implementation to the FBS + metrics; Part 3 deploys the closed-loop agent-in-the-loop over hardware.

---

## 2. Gold FBS

The gold FBS (`Central_PC/power_flow_fbs.py`) is an executable *function-building state* that
encapsulates the physical/network layer used by every agent and by the harness. In this benchmark the
FBS is treated as the **oracle / reference trajectory** against which the agents' closed-loop output
is compared, and as the source of the system parameters (topology, parameters, dispatch).

The FBS must expose, at minimum, the following interface:

| Export | Shape / kind | Semantics |
|---|---|---|
| `admittance_matrix(nodes)` | `n×n` complex, `n = 6` | Network node admittance (branch R+X, shunt G+B, transformer) |
| `topology_6nodal()` | `n×n` adjacency / connectivity dict | Radial 6-node connectivity; rooted at the PCC |
| `nominal_voltage_kV()` | float | 13.8 (nominal 13.8 kV line-to-ground at PCC) |
| `node_base_kv()` | `n` float | Per-node base voltages (kV), used to scale pu values |
| `load_profile(t)` | `n`-vec per time `t` | Active/reactive load at each node as function of time |
| `pv_or_inf_source(node)` | `n`-vec | PV/diesel/BESS available active power at each node |
| `reference_voltage_pu(t, node)` | `n`-vec | Gold reference secondary-voltage setpoint trajectory at each node |
| `reference_frequency_pu(t)` | float | Gold reference frequency setpoint trajectory |

The FBS doubles as the static "power-flow backbone": any scenario that changes topology,
dispatch, or load recomputes a reference trajectory through the FBS before the discrete-time
closed-loop simulation starts. In the gold run, no agent output modifies the FBS; the FBS output is
fixed so that the controlled loop is the *only* variable being measured.

---

## 3. Test system — AC radial 6-node microgrid, 13.8 kV

| Parameter | Value |
|---|---|
| Topology | Radial, 6 nodes (PCC + 5 DGs/loads) |
| Nominal voltage | 13.8 kV |
| Node count `n` | 6 |
| Reference model | `Central_PC/power_flow_fbs.py` (gold FBS) |
| Secondary-control channels | Voltage magnitude `V`, reactive-power quality `Q` (via `S_VQ`), frequency `ω` |
| Primary loop | Inverter droop + local voltage/frequency regulation |
| Secondary loop | Fixed-time (FxTS) consensus on `δV`, `δQ`, `δω` + integral action on `δV`, `δω` |

**Node layout (conceptual):**

- Node 0: Point of Common Coupling (PCC) — upstream 13.8 kV grid / UTMS.
- Node 1…5: distributed generation nodes, each with a PV+Diesel/BESS hybrid, inverter, and one agent
  running the fixed-time secondary controller.

**Communication graph:** a connected sparse graph over the 6 nodes (e.g., ring, line, or Voronoi-like
matching the physical topology). The benchmark sweeps `d_max` (graph diameter) since the FxTS
stability gate depends on `d_max`.

---

## 4. Secondary voltage control — fixed-time consensus (FxTS)

Each node `i` maintains local state `(V_i, Q_i, ω_i)` and runs a **discrete-time fixed-time
consensus** law on the three channels, plus an **integral** term that removes steady-state error on
`δV` and `δω`.

### 4.1 State variables (normalized)

- `x_Vi = δV_i` — voltage deviation (pu),
- `x_Qi = δQ_ratio_i` — reactive-power-quality deviation,
- `x_ωi = δω_i` — frequency deviation (rad/s),
- `x_Pi = P_ratio_i` — active-power ratio (consensus on `P` too, as in the nodal distribution).

### 4.2 FxTS consensus update (per control step `k`, step `Δt`)

```
u_V,i(k) = Σ_{j∈N_i} a_ij ( x_Vj(k) - x_Vi(k) )  +  c1·sign(x_Vi) |x_Vi|^p1 + c2·sign(x_Vi) |x_Vi|^p2
u_ω,i(k) = Σ_{j∈N_i} a_ij ( x_ωj(k) - x_ωi(k) )  +  c1·sign(x_ωi) |x_ωi|^p1 + c2·sign(x_ωi) |x_ωi|^p2
u_Q,i(k) = Σ_{j∈N_i} a_ij ( x_Qj(k) - x_Qi(k) )  +  c1·sign(x_Qi) |x_Qi|^p1 + c2·sign(x_Qi) |x_Qi|^p2
```

with `0 < p1 < 1 < p2` (double-power fractional terms), `c1, c2 > 0` gains. The **fixed-time**
property is guaranteed when

```
Δt · d_max (c1 + c2) < 1.0     (discrete CFL gate, H4)
```

and the settling time `T_f` is bounded by an explicit constant (`T_f ≤ T_max`) **independent of
initial conditions** — the canonical FxTS result.

### 4.3 Integral (restorative) action

A discrete accumulator with holding time `Δt = 500 ms` saturates the offsets to guarantee steady-state
accuracy:

```
δV_i(k+1) = sat_{[-0.10, +0.10]} ( δV_i(k) + Δt · u_V,i(k) )
δω_i(k+1) = sat_{[-π, +π]}  ( δω_i(k)  + Δt · u_ω,i(k) )
```

`δV_i` is injected into the inverter terminal voltage setpoint, and `δω_i` into the diesel/BESS power
reference (`delta_omega` channel), exactly as in the project plan's H3.

### 4.4 Anti-chattering / freshness buffer

A dead zone around zero removes chattering from the fractional term, and a *temporal-freshness buffer*
discards stale neighbor values (see plan H2/H4). The buffer is parameterized by `τ_fresh` (default
1 control step).

### 4.5 Test schedule

The consensus runs on a **time-fixed (fixed-time) grid**: every control step, all agents update
synchronously and exchange their state vector. The benchmark measures the cost of this scheduling in
message rate, delay, and drop/recovery, in addition to the electrical settling metrics.

---

## 5. Hypothesis

**H1 — Fixed-time settling.** Under the FxTS secondary voltage law with the discrete CFL gate
`Δt·d_max(c1+c2) < 1.0`, the closed-loop AC microgrid returns every node's voltage magnitude to within
`±ε_V` of its reference in a time `T_settle ≤ T_max` that is **independent of the initial offsets and
the specific graph topology**, for any connected graph over the 6 nodes.

**H2 — Zero steady-state error.** The integral action on `δV` (and `δω`) drives the voltage/frequency
offset to zero, so that post-transient the controlled voltage matches `V_ref` to numerical precision
(MSE `→ 0` over the steady window), whereas the pure consensus (no integral) leaves a bounded bias.

**H3 — Reactive-cost penalty is bounded.** The fixed-time consensus does not change the total
reactive-power cost in `Q` beyond the droop bound: `Cost_Q ≤ Q_droop_bound + ε_Q`. Excessive reserve
dispatch (`Q` above rating) is a failure indicator, not a permissible control mode.

**H4 — Fixed-time consensus is communication-adaptive.** Reducing the message rate (skip
generations) degrades settling time super-linearly once the inter-node reach falls below the graph
diameter; the delay margin (`δt_max`) shrinks monotonically with message-rate reduction. Hence the
benchmark reports message rate **together with** delay margin so that a fast/slow trade-off is visible.

**H5 — Drop-resilient.** A bounded communication-drop burst of duration `d` produces a voltage drop that
recovers to within `ε_V` in a time dominated by the FxTS settling constant `T_max`, not by the drop
duration — i.e., recovery time is predictable and predefined, which is the point of the benchmark.

---

## 6. Hardware with agents

### 6.1 Target hardware

| Element | Spec |
|---|---|
| Compute node | Raspberry Pi 5 (or equivalent developer board) |
| Network | Ethernet (primary), WiFi 5/6 (secondary, for drop experiments) |
| Control period | `Δt = 500 ms` (fixed-time grid) |
| Interfaces | GPIO/ADC (sensor read), PWM/dACS (actuator setpoint) |
| ROS/comm | DDS / custom UDP channel for P2P consensus exchange |

### 6.2 Agent software (per node)

The agent on node `i` is a thin wrapper around the consensus+controller code:

1. **Read sensors** via the FBS × hardware bridge (`V_i`, `Q_i`, `ω_i` at `Δt`).
2. **Run FxTS consensus** using the received neighbor states (temporal-freshness buffer).
3. **Apply integral restores** to produce `δV_i`, `δω_i`.
4. **Publish actuator setpoints** to the hardware bridge (inverter/DER).
5. **Log** the full state trajectory and the P2P message trace for metrics.

### 6.3 Hardware-in-the-loop (HIL) deployment

The benchmark is run as HIL: the FBS (gold) drives the physical plant model on the host; agents on the
real hardware receive the plant state and publish setpoints; a real-time data collector (RTIO / UDP
ring) streams the closed loop. The calibration target is: the HIL trace reproduces the gold FBS
trajectories for the baseline scenario within the tolerances of `metrics.py`'s `baseline_run()` gate.

---

## 7. Scenario matrix

| ID | Scenario | Manipulation | Acceptance check |
|---|---|---|---|
| S0 | Baseline (gold) | Nominal 13.8 kV, no drops, all agents online | settling ≤ `T_max`, MSE → 0, Cost_Q in bound, drop=0 |
| S1 | Mesh / graph sweep | Change topology `d_max` (ring, line, Voronoi) | settling `≤ T_max(d_max)` |
| S2 | Drop / recovery | Inject communication drop `d ∈ {0.5, 1, 2, 5 s}` | recovery `≤ T_max + f(d)` |
| S3 | Message-rate reduction | Skip `m` generations (`m=0,1,2,3`) | delay margin vs. settling trade-off |
| S4 | Noise / impairment | Measurement noise `σ`, packet loss `p` | settling within `T_max + ε_n` |
| S5 | Decay-of-initial-condition | Vary initial `δV_i(0)` | settling **independent** of `δV_i(0)` (fixed-time) |

---

## 8. Metrics (`outputs/benchmark/metrics.py`)

Six metric families are defined (implemented in `metrics.py`):

1. **settling time** — `t_settle`: time after which the voltage deviation stays within `±ε_V` for all
   remaining samples. (§8.1)
2. **MSE of S_VQ** — `mse_s_vq`: mean squared error of the reactive-power-quality consensus variable
   vs. its consensus limit. (§8.2)
3. **cost in Q** — `cost_q`: total reactive-power exchange, e.g., `∫Σ_i |Q_i| dt` or `∫Σ_i Q_i² dt`
   normalized by base. (§8.3)
4. **message rate** — `message_rate`: inter-agent communication rate (messages/s per agent),
   sustained and burst. (§8.4)
5. **delay margin** — `delay_margin`: the largest tolerated communication/actuation delay before loss
   of consensus/voltage stability; reported as `δt_max = delay_margin` in seconds. (§8.5)
6. **drop and recovery** — `drop_recovery`: count and duration of drops, plus post-drop recovery time.
   (§8.6)

All metrics accept plain arrays/traces (the same format the FBS × hardware collector emits) and return
a scalar (or structured scalar tuple). The module also provides:

- `baseline_gate(traces, specs) -> bool` — gates the whole benchmark on the S0 acceptance criteria.
- `analyze_scenario(traces, specs) -> MetricsReport` — computes all six metrics for one scenario.

### 8.1 `settling_time`

```
ε_V = 0.005 pu  (±0.5% nominal), configurable
t_settle = inf if deviation leaves the ε_V band after any time
           else the first t at which |V_i(t) − V_ref,i| ≤ ε_V for all i, all t' ≥ t
```

### 8.2 `mse_s_vq`

```
SSE = Σ_k Σ_i ( S_VQ_i(k) − S_VQ^*,k )^2
MSE  = SSE / (N_k · N_i)
S_VQ^* = consensus limit (reference / ideal reactive-quality point)
```

### 8.3 `cost_q`

```
Cost_Q = (∫_0^T Σ_i |Q_i(t)| dt) / (n · T · Q_base)
        (or the squared variant, per spec upscaling)
```

Failure if `Cost_Q > Q_headroom` (a bound derived from the droop rating).

### 8.4 `message_rate`

```
rate_sustained = total_sent_messages / (N_agents · T)          [messages · s^-1 · agent^-1]
rate_burst     = max over sliding windows of length W of (sent/W)
```

### 8.5 `delay_margin`

```
δt_max = largest δt such that the closed loop remains stable (no voltage/frequency divergence)
         verified by a linear-delay stability test (the FxTS CFL analog for delays, δt·d_max < 1).
δt_nominal is the measured real delay; the margin = δt_max − δt_nominal.
```

### 8.6 `drop_recovery`

```
drops = set of (start, end) intervals where msg-receive rate → 0
drop_count, drop_max_duration, drop_total_duration
recovery_time = t_settle(post-drop) − t_drop_end   (must be ≤ T_max per H5)
```

---

## 9. Reproduction / acceptance checklist

A run is accepted only if all of the following hold for the S0 baseline gate:

- [ ] FBS `Central_PC/power_flow_fbs.py` imports and exposes all exports of §2 with correct 13.8 kV nominal.
- [ ] `metrics.py` imports clean and all six metric functions are deterministic (seeded RNG, no side effects).
- [ ] Gold run S0: `settling_time` ≤ `T_max`, `mse_s_vq` → 0 in steady window, `cost_q` within headroom,
      `message_rate` > 0, `delay_margin > 0`, drop/recovery count = 0.
- [ ] Textile report is produced (`outputs/benchmark/reports/<scenario>_report.json` + `.csv`).
- [ ] All scenario matrix rows (S1–S5) execute and record their metrics.

---

## 10. Open items (resolved after part 1)

- Exact FBS API surface and output schema → to be read from `Central_PC/power_flow_fbs.py` in Part 2.
- FxTS parameters (`c1, c2, p1, p2, T_max`) → calibrated from the project plan number values in Part 2.
- Per-node base voltages and load profiles → from the FBS's power-flow data in Part 2.
- HIL timing offsets and clock sync → measurement setup in Part 3.
