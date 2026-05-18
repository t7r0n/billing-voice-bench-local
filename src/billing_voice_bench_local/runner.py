from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import duckdb

from .dashboard import render_dashboard
from .engine import BillingVoiceBench, data_path
from .models import SuiteSummary, project_root


def output_dir(root: Path | None = None) -> Path:
    path = (root or project_root()) / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_suite_and_write(root: Path | None = None) -> SuiteSummary:
    summary, details = BillingVoiceBench(root).run_suite()
    out = output_dir(root)
    (out / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (out / "scenario_scores.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    (out / "dashboard.html").write_text(render_dashboard(summary, details), encoding="utf-8")
    (out / "report.md").write_text(_report(summary), encoding="utf-8")
    _write_run_store(root, summary)
    return summary


def _write_run_store(root: Path | None, summary: SuiteSummary) -> None:
    runs = (root or project_root()) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(runs / "billing_voice_runs.duckdb"))
    con.execute(
        """
        create table if not exists runs (
            created_at double,
            scenario_count integer,
            groundedness double,
            refusal_precision double,
            candidate_score double,
            baseline_score double,
            pass_gates boolean
        )
        """
    )
    con.execute(
        "insert into runs values (?, ?, ?, ?, ?, ?, ?)",
        [
            time.time(),
            summary.scenario_count,
            summary.groundedness,
            summary.refusal_precision,
            summary.candidate_score,
            summary.baseline_score,
            summary.pass_gates,
        ],
    )
    con.close()


def _report(summary: SuiteSummary) -> str:
    return f"""# Billing Voice Bench Local Report

- Scenarios: {summary.scenario_count}
- Refusal categories: {summary.refusal_categories}
- Groundedness: {summary.groundedness:.3f}
- Refusal precision: {summary.refusal_precision:.3f}
- Escalation latency p95: {summary.escalation_latency_p95}
- Interruption fidelity: {summary.interruption_fidelity:.3f}
- Candidate score: {summary.candidate_score:.3f}
- Baseline score: {summary.baseline_score:.3f}
- Status: {"PASS" if summary.pass_gates else "FAIL"}
"""


def verify_outputs(root: Path | None = None) -> dict[str, bool]:
    root = root or project_root()
    out = output_dir(root)
    checks = {
        "store_exists": data_path(root).exists(),
        "summary_exists": (out / "summary.json").exists(),
        "scores_exists": (out / "scenario_scores.json").exists(),
        "dashboard_exists": (out / "dashboard.html").exists(),
        "report_exists": (out / "report.md").exists(),
    }
    if checks["summary_exists"]:
        summary = SuiteSummary.model_validate_json((out / "summary.json").read_text(encoding="utf-8"))
        checks.update(
            {
                "scenario_count_gate": summary.scenario_count == 200,
                "refusal_category_gate": summary.refusal_categories == 12,
                "groundedness_gate": summary.groundedness >= 0.9,
                "refusal_gate": summary.refusal_precision >= 0.85,
                "escalation_gate": summary.escalation_latency_p95 <= 2,
                "interruption_gate": summary.interruption_fidelity >= 0.95,
                "baseline_delta_gate": summary.candidate_score > summary.baseline_score + 0.2,
                "pass_gates": summary.pass_gates,
            }
        )
    return checks


def benchmark(root: Path | None = None, *, iterations: int = 100) -> dict[str, float | int | bool]:
    min_candidate = 1.0
    max_latency = 0
    all_pass = True
    for _ in range(iterations):
        summary, _details = BillingVoiceBench(root).run_suite()
        min_candidate = min(min_candidate, summary.candidate_score)
        max_latency = max(max_latency, summary.escalation_latency_p95)
        all_pass = all_pass and summary.pass_gates
    result = {
        "iterations": iterations,
        "min_candidate_score": min_candidate,
        "max_escalation_latency_p95": max_latency,
        "pass_gates": all_pass,
    }
    (output_dir(root) / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def export_demo_pack(root: Path | None = None) -> Path:
    root = root or project_root()
    out = output_dir(root)
    if not (out / "summary.json").exists():
        run_suite_and_write(root)
    archive = out / "demo-pack.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("summary.json", "scenario_scores.json", "dashboard.html", "report.md", "benchmark.json"):
            path = out / name
            if path.exists():
                zf.write(path, arcname=name)
    return archive
