from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from billing_voice_bench_local.engine import BillingVoiceBench, init_store, jsonl_loop
from billing_voice_bench_local.runner import benchmark, export_demo_pack, run_suite_and_write, verify_outputs


def test_fixture_scale_and_refusal_categories(tmp_path: Path) -> None:
    result = init_store(tmp_path, force=True)
    assert result["scenarios"] == 200
    assert result["refusal_categories"] == 12


def test_single_scenario_candidate_beats_baseline(tmp_path: Path) -> None:
    init_store(tmp_path, force=True)
    bench = BillingVoiceBench(tmp_path)
    candidate = bench.run_scenario("scenario-0047", agent="candidate")["score"]
    baseline = bench.run_scenario("scenario-0047", agent="baseline")["score"]
    assert candidate["score"] > baseline["score"]
    assert candidate["groundedness"] == 1


def test_suite_outputs_and_benchmark(tmp_path: Path) -> None:
    init_store(tmp_path, force=True)
    summary = run_suite_and_write(tmp_path)
    assert summary.pass_gates
    checks = verify_outputs(tmp_path)
    assert all(checks.values())
    assert benchmark(tmp_path, iterations=3)["pass_gates"] is True
    assert export_demo_pack(tmp_path).exists()


def test_jsonl_loop(tmp_path: Path) -> None:
    init_store(tmp_path, force=True)
    request = {"tool": "run_scenario", "arguments": {"scenario_id": "scenario-0047"}}
    [line] = jsonl_loop([json.dumps(request)], tmp_path)
    payload = json.loads(line)
    assert payload["score"]["score"] >= 0.9


def test_cli_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "billing_voice_bench_local.cli", "run-scenario", "scenario-0047"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "scenario-0047" in result.stdout
