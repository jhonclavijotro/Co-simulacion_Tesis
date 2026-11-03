#KIT Benchmark — Provenance of Artifacts

**Project:** MAS-Microgrid — Co-simulación Multi-Agente para el Control Secundario en Microrredes Inteligentes
**Benchmark slug:** `kit-benchmark`
**Benchmark stage:** Phase 3/3 (framework delivery)
**Artifact root:** `outputs/`
**Plan of reference:** `outputs/.plans/consenso-distribuido-voltaje-ac.md` (2026-11-01)
**Created:** 2026-11-02
**Owner:** Jhonathan Clavijo (tesis de grado)

---

## 1. Objective and scope

This document records the **provenance of every artifact** produced or consumed by the KIT benchmark framework (3 phases). Its purpose is to make the origin, authorship, parameters, source data, and reproducibility of each artifact unambiguous for audit, re-execution, and citation.

The KIT benchmark is a three-phase workflow that (1) derives a literature-review plan from the thesis context, (2) executes web/metadata sweeps and produces the review deliverable, and (3) **facilitates the delivery of a runnable benchmark package** — i.e., provenance, README, and a verification-report template — so that an independent auditor can execute and assess the work reproducibly.

> Scope note: this file is **metadata about artifacts**, not the artifacts themselves. The artifacts lives in:
> - `outputs/.plans/` (plans)
> - `outputs/consenso-distribuido-voltaje-ac.md` (literature-review deliverable)
> - `notes/` (verify/review reports and research notes)
> - `Central_PC/power_flow_fbs.py` (FBS solver)
> - `outputs/benchmark/` (this directory: provenance, README, verification-report template)

---

## 2. Artifact registry

| ID | Artifact (relative path) | Type | Creator (subagent / process) | Creation date | Source data / tool | Dependencies | Size / hash (w/o hash) |
|----|--------------------------|------|------------------------------|---------------|--------------------|--------------|------------------------|
| A1 | `outputs/.plans/consenso-distribuido-voltaje-ac.md` | Plan (literature-review spec) | Researcher subagent (Hermes) | 2026-11-01 | OpenAlex / Crossref / S2 / arXiv API; `web_search`/`fetch_content` | Thesis context (`Descripcion_proyecto.md`, `Consultas.md`) | 5,317 B |
| A2 | `outputs/.plans/consenso-voltaje-microrredes.md` | Plan (thematic) | Researcher subagent | 2026-11-01 | Same as A1 | Same as A1 | 5,140 B |
| A3 | `outputs/consenso-distribuido-voltaje-ac.md` | Literature-review deliverable | Writer subagent (Hermes) | 2026-11-01 | A1, A2, frontier sweep (20 records) | A1, A2 | 49,442 B |
| A4 | `notes/cdva-research-2026-frontier.md` | Frontier sweep register | Researcher subagent | 2026-11-01 | Crossref/arXiv per DOI | A1 | 9,881 B |
| A5 | `notes/cdva_abstracts.json` | Corpus metadata (34 abstracts w/ text + 8 metadata-only) | Researcher subagent | 2026-11-01 | Crossref/arXiv | A4 | JSON |
| A6 | `notes/cdva-counts.json` | Aggregate counts (by year/venue/claim) | Researcher subagent | 2026-11-01 | A5 | A5 | 1,402 B |
| A7 | `outputs/revision_consenso_distribuido_control_secundario_voltaje_microrredes_AC_2018-2025.md` | First-pass review draft | Researcher (baseline) | 2026-10-31 | A3 as baseline | A3 | 42,840 B |
| A8 | `notes/cdva-verify-report.md` | Verification report (DOI 42/42 OK, B→C deduction log) | Verifier subagent | 2026-11-01 | OpenAlex/Crossref/S2/arXiv; `cdva_verify.py` | A3, A5 | 12,356 B |
| A9 | `notes/cdva-review-report.md` | Review report (Major Revision; 0 FATAL / 9 MAJOR / 6 MINOR) | Reviewer subagent | 2026-11-01 | A8 | A8, A7 | 25,239 B |
| A10 | `Central_PC/power_flow_fbs.py` | FBS solver (Modo A) | Core developer | 2026-09-28 | (project) | None | 9,528 B |
| A11 | `Central_PC/sensitivity_matrices.py` | Sensitivity-matrix solver (Modo B) | Core developer | 2026-09-28 | (project) | A10 | 7,112 B |
| A12 | `Central_PC/master_clock_zmq.py` | Master clock (ZeroMQ) | Core developer | 2026-09-28 | (project) | None | 10,904 B |
| A13 | `outputs/benchmark/provenance.md` | **This file** — provenance registry | This phase-3 subagent | 2026-11-02 | A1–A12 | — | — |
| A14 | `outputs/benchmark/README.md` | README — benchmark documentation | This phase-3 subagent | 2026-11-02 | A1–A12 | — | — |
| A15 | `outputs/benchmark/verification-report.md` | Verification-report template | This phase-3 subagent | 2026-11-02 | A1–A12 | — | — |

> Hash note: SHA-256 of each artifact is recorded in the verification-report and in the per-artifact file (`*.hash.txt`) when the file is committed to `outputs/`. Circularity: A13–A15 hash each other; only A1–A12 are hashable first.

---

## 3. Artifact lineage (pipeline)

```
[Context]
  Descripcion_proyecto.md, Consultas.md, Propuesta_Proyecto_CoSimulacion_MAS.md
        │
        ▼
[Phase 1]
  A1/A2 plans (.plans/consenso-*.md)  ← researcher subagent (OpenAlex, Crossref, S2, arXiv)
        │
        ▼
[Phase 2]
  A3 consenso-distribuido-voltaje-ac.md  (writer, from A1/A2 + frontier sweep)
  A4–A6 frontier/corpus/registers
  A7 baseline revision draft
        │
        ▼
[Phase 3]
  A8 cdva-verify-report.md   (verifier subagent)
  A9 cdva-review-report.md   (reviewer subagent)
  A13–A15 benchmark package  (this phase: provenance, README, verification-report)
```

The **deliverable provenance** chain for the primary benchmark text is:

```
A1 (plan) + A2 (plan) → A4 (frontier sweep) → A5 (abstracts) → A3 (review deliverable)
```

and the **verification provenance**:

```
A3 ──► A8 (verify) ──► A9 (review) ──► A15 (verification-report template)
```

---

## 4. Reproducibility

### 4.1 Environment

The benchmark is language-agnostic at the plan level (it is a literature-review benchmark) and language-bound at the FBS level (Python 3.12+).

| Requirement | Version | Note |
|---|---|---|
| Python | 3.12+ | used for `Central_PC/power_flow_fbs.py` and pyzmq/InfluxDB clients |
| Docker + Compose | latest | for RPi cluster; not required for the review benchmark |
| Network APIs | internet | OpenAlex, Crossref, S2, arXiv, web_search |
| `feynman alpha` CLI | depends on login | **blocked 2026-11-01** — recorded as capability drop in A1/A4 |

### 4.2 Reproducing the FBS solver (Modo A)

```bash
cd /d/Antigravity/Projects/Tesis_Grado
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python Central_PC/power_flow_fbs.py
```

Expected console output (from the shipped `if __name__ == "__main__"` block, `config/topologia_BT_4nodos.csv`, P={2:10000}, Q={2:2000}, Q={4:-3000}):

```
Topología BT cargada: 4 nodos, 3 ramas.
Resultado FBS (Convergencia=True, Iteraciones=N): ...
```

### 4.3 Reproducing the review benchmark (end-to-end)

1. Execute the researcher workflow to regenerate `outputs/.plans/consenso-distribuido-voltaje-ac.md` from the thesis context.
2. Execute the writer workflow to produce `outputs/consenso-distribuido-voltaje-ac.md`.
3. Execute the verify and review subagents to produce `notes/cdva-verify-report.md` and `notes/cdva-review-report.md`.
4. Run the phase-3 builder to emit `outputs/benchmark/` (this directory).

> The phase-3 builder is described in `outputs/benchmark/README.md`.

### 4.4 Parameters of record

| Parameter | Value | Where used |
|---|---|---|
| Review window | 2018–2026; frontier emphasis ≥ 2022 | A1 §4 |
| Frontier sweep | 20 candidate records | A4 |
| Corpus size | 42 records; 34 abstracts w/ text, 8 metadata-only | A5/A8 |
| Evidence levels | A / B / C | A1 §4 §5 |
| DOI verification | OpenAlex Crossref REST, per DOI | A8 |
| FBS solver | V_base=400 V, S_base=100 kVA, tol 1e-6, max_iter 100 | A10 |
| Frequency NTC 1340 | 58.8–61.2 Hz | A10 (ffc_lpf=2.0 s, H_sys=6.0, D_sys=12.0) |

---

## 5. Integrity and traceability

- **Git:** the project is under Git at `D:\Antigravity\Projects\Tesis_Grado`. Tracked files are listed in `git ls-files`; artifacts A1–A7, A10–A12 are tracked; `outputs/benchmark/` contents are **untracked** (newly created).
- **Checksum storage:** commit `*.sha256.txt` sidecars (e.g., `outputs/consenso-distribuido-voltaje-ac.sha256.txt`) alongside artifacts. Not yet done in this phase; flagged as a follow-up in the verification-report template.
- **Negative results:** recorded as they occur (e.g., `alpha` CLI "Not logged in" in A1 §7; `D:` drive mapping used for the original plan location).
- **Honesty rules:** every numeric claim in the deliverable traces to an A5/A8 record or a URL; no fabricated metrics; no "provenance by assertion".

---

## 6. Open items and follow-ups

| # | Item | Owner | Priority |
|---|---|---|---|
| O1 | Add SHA-256 sidecars for all `outputs/` artifacts | phase-3 subagent | Medium |
| O2 | Scriptar la frontier sweep (`cdva_research_2026_frontier.py`) | researcher | Medium |
| O3 | Apply the readings of A9 to A3 (§9.2 vs §8.2, F-2..F-9) | writer | High |
| O4 | Re-run DOI verification after applying A9 readings | verifier | Medium |
| O5 | Register `run_benchmark.py` in `outputs/benchmark/` | phase-3 subagent | High |

---
*End of provenance. See `README.md` (run instructions) and `verification-report.md` (template).*
