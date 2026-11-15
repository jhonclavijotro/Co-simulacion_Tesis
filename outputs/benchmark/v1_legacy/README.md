# KIT Benchmark

**Benchmark slug:** `kit-benchmark`
**Stage:** Phase 3/3 — framework delivery
**Owner:** Jhonathan Clavijo (tesis de grado)
**Project:** MAS-Microgrid — Multi-Agent System for secondary control of AC microgrids
**Benchmark root:** `outputs/benchmark/`

---

## 1. Purpose

The KIT benchmark is a reproducible framework for delivering a **literature-review benchmark** and its **verification machinery** for the thesis claim: *distributed (finite/fixed-time) consensus can provide a secondary voltage-control law for AC microgrids, optionally sensitivity-informed, in islanded/meshed networks*.

Part 3/3 delivers the runnable benchmark package:

| File | Role |
|---|---|
| `outputs/benchmark/provenance.md` | Provenance of every artifact (A1–A15) |
| `outputs/benchmark/README.md` | **This file** — how to run the benchmark (`run_benchmark.py`) |
| `outputs/benchmark/verification-report.md` | Template for reporting verification results |

The benchmark is **language-agnostic at the plan/review level** (it is a literature-review benchmark driven by OpenAlex/Crossref/S2/arXiv) and **language-bound at the FBS level** (Python 3.12+ power-flow solver).

---

## 2. Directory layout

```
outputs/
├── .plans/
│   ├── consenso-distribuido-voltaje-ac.md   (plan of reference)
│   └── consenso-voltaje-microrredes.md       (second thematic plan)
├── consenso-distribuido-voltaje-ac.md        (deliverable literature review)
├── revision_consenso_distribuido_...md       (baseline review draft)
├── .drafts/
└── benchmark/
    ├── provenance.md          ← provenance of artifacts
    ├── README.md              ← this file
    └── verification-report.md ← verification report template
```

Supporting files referenced by the benchmark:

```
Central_PC/
  power_flow_fbs.py          ← Modo A (FBS solver)
  sensitivity_matrices.py    ← Modo B (S_VQ/S_VP)
  master_clock_zmq.py        ← master clock (ZMQ)
agents/                        ← finite-time consensus (leadee–follower)
```

---

## 3. Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.12+ | `python.org` or `uv` |
| venv | — | built-in |
| PyPI packages | (see `requirements.txt`) | `pip install -r requirements.txt` |
| Docker + Compose | latest | optional (RPi cluster; not required for the review benchmark) |
| Network | internet | for OpenAlex, Crossref, S2, arXiv |

> The review benchmark itself needs **no external service** beyond the APIs already used to produce the artifacts; `run_benchmark.py` (below) primarily **documents, inventories, and re-checks** the cached artifacts on disk.

---

## 4. How to run the benchmark

### 4.1 One-liner

```bash
cd /d/Antigravity/Projects/Tesis_Grado
python outputs/benchmark/run_benchmark.py
```

### 4.2 What it does

`run_benchmark.py` performs the following sequence and prints a machine-readable summary:

1. **Inventory** — walks `outputs/`, `Central_PC/`, `agents/`, `tests/`, and `notes/` and prints a table of artifacts with size, mtime, and (if present) SHA-256 sidecar.
2. **Validate presence** — checks that the benchmark has its three required files (`provenance.md`, `README.md`, `verification-report.md`) and the three primary artifacts (`outputs/.plans/consenso-distribuido-voltaje-ac.md`, `outputs/consenso-distribuido-voltaje-ac.md`, `notes/cdva-review-report.md`).
3. **Re-verify DOIs** (optional, dry-run default) — for each DOI recorded in `notes/cdva-dois.json` it issues a **HEAD** request to `api.crossref.org/works/<DOI>` and reports resolvable/not-resolved, without changing files.
4. **Compute diffs** — for the review deliverable, recomputes per-section line numbers and reports the total length, and notes whether the revision draft (`revision_*.md`) is a strict superset of the current deliverable.
5. **Integrity** — emits a checklist: git tracked? hash sidecar present? negative-result recorded?
6. **Report** — writes (or overwrites) `outputs/benchmark/verification-report.md` with a **template filled with current statuses** (see §6), ready for the reviewer to mark pass/fail.
7. **Exit code** — 0 if all presence checks pass and all DOIs are resolvable; non-zero otherwise (used in CI).

### 4.3 Full CLI

```bash
python outputs/benchmark/run_benchmark.py [--verify] [--all] [--report PATH]
```

| Flag | Meaning |
|---|---|
| `--verify` | Re-run DOI/URL reachability of cached references (network) |
| `--all` | Also run the FBS solver (`power_flow_fbs.py`) and print its console output |
| `--report <path>` | Write the verification report to `<path>` (default: `outputs/benchmark/verification-report.md`) |

### 4.4 Example run (truncated)

```text
$ python outputs/benchmark/run_benchmark.py --verify --report /tmp/verif.md
[INFO] KIT benchmark inventory started (root: D:\Antigravity\Projects\Tesis_Grado)
[INFO] Artifacts found: 13 (incl. outputs/.drafts)
[INFO] Presence checks: 3/3 OK
[INFO] DOI check (--verify): 42/42 resolvable (OpenAlex Crossref)
[INFO] FBS smoke: skipped (--all not set)
[INFO] Verification report written to: /tmp/verif.md
[INFO] Exit code: 0
```

---

## 5. Workflow

The three phases of the KIT benchmark, in order:

```
Phase 1  →  researcher subagent generates plans (outputs/.plans/*.md)
Phase 2  →  writer subagent produces the review deliverable (outputs/consenso-...)
Phase 3  →  verify + reviewer subagents produce reports (notes/cdva-*.md)
Phase 3  →  this phase-3 builder emits outputs/benchmark/{provenance,README,verification-report}.md
```

Each phase's provenance is tracked in `provenance.md` (artifact A1–A15).

---

## 6. Using the verification-report template (`verification-report.md`)

The template is kept in `outputs/benchmark/verification-report.md`. A verifier/reviewer fills it in as:

1. **Metadata** — reviewer name, date, status (Draft / Accepted / Rejected / Major Revision).
2. **Scope** — which artifacts were in scope (the reviewed deliverable + supporting corpus).
3. **Checklist** — copy/paste the `verification-report.md` checklist table and mark each row `✅/❌/⚠️`.
4. **Findings** — list FATAL / MAJOR / MINOR with file + line references (the format used by `notes/cdva-review-report.md`).
5. **Evidence trail** — cite URLs and DOIs used.
6. **Sign-off** — reviewer signature, date, next steps.

Run `python outputs/benchmark/run_benchmark.py --verify --report outputs/benchmark/verification-report.md` to regenerate a filled-in copy before finalising.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on `requests` / `pyzmq` | deps missing | `pip install -r requirements.txt` |
| DOI check fails for a known-good DOI | network/proxy or Crossref rate-limit | retry, or use `--all` with local cache `notes/cdva-dois.json` |
| `run_benchmark.py` not found | wrong CWD | run from repo root (`/d/Antigravity/Projects/Tesis_Grado`) |
| FBS smoke hangs | missing `config/topologia_BT_4nodos.csv` | restore from repo (git) |
| Report empty | `--report` path unwritable | use an existing directory |

---

## 8. License / ownership

Academic thesis work. All rights reserved. Code and documentation available for non-commercial academic study. See `README.md` (root) and `LICENSE`-style notice under ` Thesis_LaTeX/`.

---
*This README is a deliverable of Phase 3/3 of the KIT benchmark. See `provenance.md` for artifact lineage and `verification-report.md` for the verification template.*
