from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class EobLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_id: str
    description: str
    cpt_code: str
    amount: int
    coverage_status: str
    allowed_answer: str


class PatientTurn(BaseModel):
    text: str
    interrupt: bool = False
    distress: bool = False


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    category: str
    language: str
    patient_turns: tuple[PatientTurn, ...]
    eob_lines: tuple[EobLine, ...]
    gold_action: str
    refusal_category: str | None
    must_cite: tuple[str, ...]
    distress_turn: int | None = None
    expected_escalation_within: int = 2


class AgentTurn(BaseModel):
    turn_index: int
    text: str
    cited_line_ids: tuple[str, ...] = ()
    escalated: bool = False
    refused: bool = False
    yielded_to_interrupt: bool = True


class ScenarioScore(BaseModel):
    scenario_id: str
    category: str
    groundedness: float
    refusal_correct: bool
    escalation_latency: int | None
    interruption_fidelity: bool
    score: float
    failures: list[str] = Field(default_factory=list)


class SuiteSummary(BaseModel):
    scenario_count: int
    refusal_categories: int
    groundedness: float
    refusal_precision: float
    escalation_latency_p95: int
    interruption_fidelity: float
    candidate_score: float
    baseline_score: float
    pass_gates: bool
