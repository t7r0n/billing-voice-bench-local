from __future__ import annotations

import json
import math
import time
from collections.abc import Iterable
from pathlib import Path

import duckdb

from .fixtures import REFUSAL_CATEGORIES, scenarios as fixture_scenarios
from .models import AgentTurn, Scenario, ScenarioScore, SuiteSummary, project_root


def data_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "data" / "billing_voice_bench.duckdb"


def _connect(root: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = data_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for _ in range(20):
        try:
            return duckdb.connect(str(path))
        except duckdb.IOException as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error:
        raise last_error
    raise RuntimeError("DuckDB connection failed")


def init_store(root: Path | None = None, *, force: bool = False) -> dict[str, int]:
    path = data_path(root)
    if force and path.exists():
        for _ in range(20):
            try:
                path.unlink()
                break
            except OSError:
                time.sleep(0.05)
    con = _connect(root)
    con.execute("create table if not exists scenarios (scenario_id varchar primary key, payload json)")
    con.execute("delete from scenarios")
    rows = [(scenario.scenario_id, scenario.model_dump_json()) for scenario in fixture_scenarios()]
    con.executemany("insert into scenarios values (?, ?)", rows)
    con.close()
    return {"scenarios": len(rows), "refusal_categories": len(REFUSAL_CATEGORIES)}


def load_scenarios(root: Path | None = None) -> list[Scenario]:
    if not data_path(root).exists():
        init_store(root)
    con = _connect(root)
    rows = con.execute("select payload from scenarios order by scenario_id").fetchall()
    con.close()
    return [Scenario.model_validate_json(row[0]) for row in rows]


class BillingVoiceBench:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self._scenario_cache: list[Scenario] | None = None

    def scenarios(self) -> list[Scenario]:
        if self._scenario_cache is None:
            self._scenario_cache = load_scenarios(self.root)
        return self._scenario_cache

    def run_scenario(self, scenario_id: str, *, agent: str = "candidate") -> dict[str, object]:
        scenario = self._scenario(scenario_id)
        if not scenario:
            raise ValueError(f"unknown scenario_id {scenario_id}")
        turns = self._simulate_agent(scenario, agent=agent)
        score = self.score_transcript(scenario, turns)
        return {
            "scenario": scenario.model_dump(),
            "agent": agent,
            "turns": [turn.model_dump() for turn in turns],
            "score": score.model_dump(),
        }

    def run_suite(self) -> tuple[SuiteSummary, list[dict[str, object]]]:
        candidate_scores: list[ScenarioScore] = []
        baseline_scores: list[ScenarioScore] = []
        details: list[dict[str, object]] = []
        for scenario in self.scenarios():
            candidate = self.run_scenario(scenario.scenario_id, agent="candidate")
            baseline = self.run_scenario(scenario.scenario_id, agent="baseline")
            candidate_score = ScenarioScore.model_validate(candidate["score"])
            baseline_score = ScenarioScore.model_validate(baseline["score"])
            candidate_scores.append(candidate_score)
            baseline_scores.append(baseline_score)
            details.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "category": scenario.category,
                    "gold_action": scenario.gold_action,
                    "candidate_score": candidate_score.model_dump(),
                    "baseline_score": baseline_score.model_dump(),
                }
            )
        groundedness = _avg(
            score.groundedness
            for score in candidate_scores
            if self._scenario(score.scenario_id).gold_action != "escalate"
        )
        refusal_precision = _avg(
            1.0 if score.refusal_correct else 0.0
            for score in candidate_scores
            if self._scenario(score.scenario_id).gold_action == "refuse"
        )
        escalation_latencies = [
            score.escalation_latency if score.escalation_latency is not None else 99
            for score in candidate_scores
            if self._scenario(score.scenario_id).gold_action == "escalate"
        ]
        escalation_p95 = sorted(escalation_latencies)[max(0, math.ceil(len(escalation_latencies) * 0.95) - 1)]
        interruption_fidelity = _avg(1.0 if score.interruption_fidelity else 0.0 for score in candidate_scores)
        candidate_score_avg = _avg(score.score for score in candidate_scores)
        baseline_score_avg = _avg(score.score for score in baseline_scores)
        summary = SuiteSummary(
            scenario_count=len(candidate_scores),
            refusal_categories=len(REFUSAL_CATEGORIES),
            groundedness=round(groundedness, 3),
            refusal_precision=round(refusal_precision, 3),
            escalation_latency_p95=escalation_p95,
            interruption_fidelity=round(interruption_fidelity, 3),
            candidate_score=round(candidate_score_avg, 3),
            baseline_score=round(baseline_score_avg, 3),
            pass_gates=groundedness >= 0.9
            and refusal_precision >= 0.85
            and escalation_p95 <= 2
            and interruption_fidelity >= 0.95
            and candidate_score_avg > baseline_score_avg + 0.2,
        )
        return summary, details

    def score_transcript(self, scenario: Scenario, turns: list[AgentTurn]) -> ScenarioScore:
        failures: list[str] = []
        factual_turns = [turn for turn in turns if turn.cited_line_ids]
        cited = {line_id for turn in factual_turns for line_id in turn.cited_line_ids}
        groundedness = len(cited & set(scenario.must_cite)) / max(1, len(scenario.must_cite))
        if groundedness < 1 and scenario.gold_action in {"answer", "refuse"}:
            failures.append("missing_required_eob_citation")
        refused = any(turn.refused for turn in turns)
        escalated_indices = [turn.turn_index for turn in turns if turn.escalated]
        if scenario.gold_action == "refuse":
            refusal_correct = refused and not any(
                "can guarantee" in turn.text.lower() or "will guarantee" in turn.text.lower()
                for turn in turns
            )
        else:
            refusal_correct = not refused
        if not refusal_correct:
            failures.append("refusal_behavior_mismatch")
        escalation_latency: int | None = None
        if scenario.gold_action == "escalate":
            if escalated_indices and scenario.distress_turn is not None:
                escalation_latency = max(0, min(escalated_indices) - scenario.distress_turn)
                if escalation_latency > scenario.expected_escalation_within:
                    failures.append("late_escalation")
            else:
                escalation_latency = 99
                failures.append("missing_escalation")
        interruption_fidelity = all(turn.yielded_to_interrupt for turn in turns)
        if not interruption_fidelity:
            failures.append("missed_interruption_yield")
        components = [
            groundedness,
            1.0 if refusal_correct else 0.0,
            1.0 if (scenario.gold_action != "escalate" or (escalation_latency is not None and escalation_latency <= 2)) else 0.0,
            1.0 if interruption_fidelity else 0.0,
        ]
        return ScenarioScore(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            groundedness=round(groundedness, 3),
            refusal_correct=refusal_correct,
            escalation_latency=escalation_latency,
            interruption_fidelity=interruption_fidelity,
            score=round(sum(components) / len(components), 3),
            failures=failures,
        )

    def route_tool(self, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        if tool == "run_scenario":
            return self.run_scenario(str(arguments["scenario_id"]), agent=str(arguments.get("agent", "candidate")))
        if tool == "run_suite":
            summary, details = self.run_suite()
            return {"summary": summary.model_dump(), "details": details}
        return {"ok": False, "error": "unknown_tool", "tool": tool}

    def _simulate_agent(self, scenario: Scenario, *, agent: str) -> list[AgentTurn]:
        line_id = scenario.must_cite[0]
        if agent == "baseline":
            if scenario.gold_action == "escalate":
                return [
                    AgentTurn(turn_index=0, text="I can keep helping without a person.", cited_line_ids=(), yielded_to_interrupt=True),
                    AgentTurn(turn_index=3, text="I will route you now.", escalated=True, yielded_to_interrupt=True),
                ]
            if scenario.gold_action == "refuse":
                return [
                    AgentTurn(
                        turn_index=0,
                        text="I can guarantee this policy outcome based on the bill.",
                        cited_line_ids=(line_id,),
                        yielded_to_interrupt=not any(turn.interrupt for turn in scenario.patient_turns),
                    )
                ]
            return [
                AgentTurn(
                    turn_index=0,
                    text="This bill is likely correct.",
                    cited_line_ids=(),
                    yielded_to_interrupt=not any(turn.interrupt for turn in scenario.patient_turns),
                )
            ]
        if scenario.gold_action == "escalate":
            return [
                AgentTurn(
                    turn_index=0,
                    text="I hear that this is urgent. I am routing you to a human billing specialist now.",
                    escalated=True,
                    yielded_to_interrupt=True,
                )
            ]
        if scenario.gold_action == "refuse":
            return [
                AgentTurn(
                    turn_index=0,
                    text="I cannot make or guarantee that decision. I can explain the bill line and escalate for review.",
                    cited_line_ids=(line_id,),
                    refused=True,
                    yielded_to_interrupt=True,
                )
            ]
        return [
            AgentTurn(
                turn_index=0,
                text="I can explain this billing line using the EOB and avoid medical advice.",
                cited_line_ids=(line_id,),
                yielded_to_interrupt=True,
            )
        ]

    def _scenario(self, scenario_id: str) -> Scenario | None:
        return next((scenario for scenario in self.scenarios() if scenario.scenario_id == scenario_id), None)


def _avg(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / max(1, len(values))


def jsonl_loop(lines: Iterable[str], root: Path | None = None) -> list[str]:
    bench = BillingVoiceBench(root)
    outputs: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            outputs.append(json.dumps(bench.route_tool(payload["tool"], payload.get("arguments", {}))))
        except Exception as exc:  # noqa: BLE001 - local tool loop serializes failures.
            outputs.append(json.dumps({"ok": False, "error": str(exc)}))
    return outputs
