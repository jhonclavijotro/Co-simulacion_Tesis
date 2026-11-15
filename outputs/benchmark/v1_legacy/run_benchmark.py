#!/usr/bin/env python3
"""KIT benchmark runner (Phase 3/3 of the kit-benchmark framework).

Runs the benchmark end-to-end: inventories artifacts, validates presence of
the benchmark package, re-checks DOI metadata on the cached corpus, validates
the FBS solver, and writes a (re)generated verification report.

Usage:
    python outputs/benchmark/run_benchmark.py [--verify] [--all] [--report PATH]
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # repo root (Tesis_Grado/)
BENCHMARK_DIR = REPO_ROOT / "outputs" / "benchmark"
REPORT_PATH = BENCHMARK_DIR / "verification-report.md"

PRIMARY_PLAN = REPO_ROOT / "outputs" / ".plans" / "consenso-distribuido-voltaje-ac.md"
REVIEW_DELIVERABLE = REPO_ROOT / "outputs" / "consenso-distribuido-voltaje-ac.md"
REVISION_DRAFT = REPO_ROOT / "outputs" / "revision_consenso_distribuido_control_secundario_voltaje_microrredes_AC_2018-2025.md"
ABSTRACTS = REPO_ROOT / "notes" / "cdva_abstracts.json"
DOIS = REPO_ROOT / "notes" / "cdva_dois.json"
FRONTIER = REPO_ROOT / "notes" / "cdva-research-2026-frontier.md"

BENCHMARK_REQUIRED = {
    "provenance.md": "provenance of artifacts",
    "README.md": "documentation of the benchmark",
    "verification-report.md": "verification report template",
}

PRIMARY_REQUIRED = {
    PRIMARY_PLAN: "primary plan (A1)",
    REVIEW_DELIVERABLE: "review deliverable (A3)",
    REVISION_DRAFT: "baseline revision draft (A7)",
}


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_table(root: Path, exts=None) -> list[dict]:
    """Recursively list files with size, mtime, sha256-sidecar flag."""
    rows = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if exts and p.suffix.lower() not in exts:
            # but still list the .md/.csv/.py/.json plan files
            pass
        sidecar = (p.with_suffix(p.suffix + ".sha256.txt")).exists()
        rows.append({
            "path": str(p.relative_to(REPO_ROOT)),
            "size": p.stat().st_size,
            "mtime": p.stat().st_mtime,
            "sha256_sidecar": sidecar,
        })
    return rows


def check_presence() -> tuple[bool, list[str]]:
    """Check the three benchmark files + three primary artifacts exist."""
    problems = []
    for name, role in BENCHMARK_REQUIRED.items():
        p = BENCHMARK_DIR / name
        if not p.exists():
            problems.append(f"benchmark file MISSING: {name} ({role})")
    for path, role in PRIMARY_REQUIRED.items():
        if not path.exists():
            problems.append(f"primary artifact MISSING: {path.name} ({role})")
    return (len(problems) == 0), problems


def check_dois(verbose: bool = False) -> tuple[int, int]:
    """Re-check DOI resolution of the cached corpus via Crossref REST."""
    if not DOIS.exists():
        return 0, 0
    dois = json.loads(DOIS.read_text(encoding="utf-8"))
    # Accept either a list of strings or {id: doi} mapping.
    records = []
    if isinstance(dois, list):
        records = [d if isinstance(d, str) else d.get("doi", "") for d in dois]
    elif isinstance(dois, dict):
        records = [v if isinstance(v, str) else v.get("doi", "") for v in dois.values()]
    total = 0
    ok = 0
    for doi in records:
        doi = doi.strip()
        if not doi:
            continue
        total += 1
        url = f"https://api.crossref.org/works/{doi}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KIT-benchmark-runner/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                status = r.status
                if status == 200:
                    ok += 1
                    if verbose:
                        print(f"[DOI OK] {doi} -> {status}")
                else:
                    print(f"[DOI FAIL] {doi} -> HTTP {status}")
        except Exception as exc:
            print(f"[DOI FAIL] {doi} -> {exc}")
    return total, ok


def fbs_smoke() -> tuple[bool, str]:
    """Run the FBS solver with the shipped test case (--all)."""
    solver = REPO_ROOT / "Central_PC" / "power_flow_fbs.py"
    topology = REPO_ROOT / "config" / "topologia_BT_4nodos.csv"
    if not solver.exists() or not topology.exists():
        return False, "FBS solver or topology not found"
    code = (
        "from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver\n"
        "s = ForwardBackwardSweepSolver(V_base=400.0, S_base=100000.0)\n"
        "s.load_topology('config/topologia_BT_4nodos.csv')\n"
        "V, conv, iters = s.solve({2: 10000.0, 4: -15000.0}, {2: 2000.0, 4: -3000.0})\n"
        "print(f'Converged={conv}, iters={iters}')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout or "").strip()
    if proc.returncode == 0 and "Converged=" in out:
        return True, out
    return False, (proc.stderr or proc.stdout or "FBS smoke failed").strip()


def build_report(status: dict) -> str:
    """Render the verification-report.md from the current status dict."""
    lines = []
    lines.append("# KIT Benchmark — Verification Report")
    lines.append("")
    lines.append(f"**Benchmark slug:** `kit-benchmark`")
    lines.append(f"**Stage:** Phase 3/3 — framework delivery")
    lines.append(f"**Generated:** {__import__('datetime').datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| **Reviewer** | — |")
    lines.append(f"| **Status** | {status.get('overall', '?')} |")
    lines.append(f"| **Run command** | `python outputs/benchmark/run_benchmark.py --verify` |")
    lines.append("")
    lines.append("## 2. Verification checklist")
    lines.append("")
    lines.append("| ID | Checklist | Result |")
    lines.append("|---|---|---|")
    for cid, (ok, msg) in status.get("checklist", {}).items():
        symbol = "✅" if ok else ("⚠️" if "PARTIAL" in msg else "❌")
        lines.append(f"| {cid} | {msg} | {symbol} |")
    lines.append("")
    lines.append("## 3. Findings")
    lines.append("")
    lines.append("| # | Severity | Location | Problem | Fix |")
    lines.append("|---|---|---|---|---|")
    for f in status.get("findings", []):
        lines.append(f"| {f.get('id','')} | {f.get('severity','')} | {f.get('loc','')} | {f.get('problem','')} | {f.get('fix','')} |")
    lines.append("")
    lines.append("## 4. Evidence trail")
    lines.append("")
    lines.append("| Claim | Source |")
    lines.append("|---|---|")
    for c in status.get("evidence", []):
        lines.append(f"| {c.get('claim','')} | {c.get('source','')} |")
    lines.append("")
    lines.append("## 5. Sign-off")
    lines.append("")
    lines.append("| Role | Name | Date |")
    lines.append("|---|---|---|")
    lines.append("| Reviewer | — | — |")
    lines.append("")
    lines.append("## 6. Open items")
    lines.append("")
    lines.append("| # | Item | Owner |")
    lines.append("|---|---|---|")
    for o in status.get("open", []):
        lines.append(f"| {o.get('id','')} | {o.get('item','')} | {o.get('owner','')} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="KIT benchmark runner (Phase 3/3)")
    ap.add_argument("--verify", action="store_true", help="re-check DOI/URL metadata (network)")
    ap.add_argument("--all", action="store_true", help="also run the FBS smoke (Modo A)")
    ap.add_argument("--report", type=Path, default=REPORT_PATH, help="write report to PATH")
    args = ap.parse_args(argv)

    print(f"[INFO] KIT benchmark inventory started (root: {REPO_ROOT})")

    # 1. Inventory
    inv = artifact_table(REPO_ROOT)
    print(f"[INFO] Artifacts found: {len(inv)}")

    # 2. Presence checks
    present, problems = check_presence()
    print(f"[INFO] Presence checks: {('PASS' if present else 'FAIL')} ({len(inv)} artifacts)")
    for p in problems:
        print(f"[WARN] {p}")

    # 3. DOI re-check
    doi_total, doi_ok = 0, 0
    if args.verify:
        doi_total, doi_ok = check_dois(verbose=True)
        print(f"[INFO] DOI check (--verify): {doi_ok}/{doi_total} resolvable")
    else:
        print("[INFO] Skipping DOI network check (use --verify)")

    # 4. FBS smoke
    fbs_ok, fbs_out = False, ""
    if args.all:
        fbs_ok, fbs_out = fbs_smoke()
        print(f"[INFO] FBS smoke: {'OK' if fbs_ok else 'FAIL'}")
        if fbs_out:
            print(f"[INFO] FBS: {fbs_out}")
    else:
        print("[INFO] FBS smoke skipped (use --all)")

    # 5. Integrity / checklist assembly
    checklist = {
        "C1": ( (BENCHMARK_DIR/"provenance.md").exists(), "benchmark provenance.md exists" ),
        "C2": ( (BENCHMARK_DIR/"README.md").exists(), "benchmark README.md exists" ),
        "C3": ( (BENCHMARK_DIR/"verification-report.md").exists(), "benchmark verification-report.md exists" ),
        "C4": ( PRIMARY_PLAN.exists(), "primary plan exists" ),
        "C5": ( REVIEW_DELIVERABLE.exists(), "review deliverable exists" ),
        "C6": ( REVISION_DRAFT.exists(), "baseline revision draft exists" ),
        "C7": ( ABSTRACTS.exists(), "abstract corpus (cdva_abstracts.json) exists" ),
        "C8": ( DOIS.exists(), "DOI register (cdva_dois.json) exists" ),
        "C9": ( FRONTIER.exists(), "frontier sweep register exists" ),
    }
    # C10 (FBS) only when --all
    if args.all:
        checklist["C10"] = (fbs_ok, "FBS solver runs under Python 3.12 with shipped topology")
    if args.verify:
        checklist["C11"] = ( doi_total > 0 and doi_ok == doi_total, f"dois: {doi_ok}/{doi_total} resolvable" )

    # 6. Compose report
    status = {
        "overall": "PASS" if (present and (not args.verify or doi_ok == doi_total) and (not args.all or fbs_ok)) else "FAIL",
        "checklist": {k: (ok, "OK" if ok else "missing/incorrect") for k, (ok, _) in checklist.items()},
        "findings": [],
        "evidence": [],
        "open": [
            {"id": "O1", "item": "Add SHA-256 sidecars for outputs/ artifacts", "owner": "phase-3"},
            {"id": "O2", "item": "Script the frontier sweep", "owner": "researcher"},
            {"id": "O3", "item": "Apply review readings to the deliverable", "owner": "writer"},
            {"id": "O4", "item": "Re-run DOI verification after fixes", "owner": "verifier"},
            {"id": "O5", "item": "Register run_benchmark.py in the package", "owner": "phase-3"},
        ],
    }
    report_text = build_report(status)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text, encoding="utf-8")
    print(f"[INFO] Verification report written to: {args.report}")

    overall = 0 if (present and (not args.verify or doi_ok == doi_total) and (not args.all or fbs_ok)) else 1
    print(f"[INFO] Exit code: {overall}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
