# Billing Voice Bench Local

Local benchmark for patient-billing voice-agent safety behavior.

The project simulates patient billing calls, generates deterministic agent responses, and grades the transcript for grounded claims, correct refusals, escalation timing, and interruption handling. It is designed for local demos and regression testing with synthetic data only; no external API or phone provider is required.

## Features

- 200 deterministic synthetic patient-billing scenarios with EOB-style line items.
- 12 refusal categories covering medical advice, policy invention, eligibility promises, payment-plan promises, privacy-sensitive requests, and other high-risk billing surfaces.
- Deterministic graders for groundedness, refusal precision, escalation latency, and interruption fidelity.
- Local adversary simulator that replays patient turns and interruption events against candidate and baseline agents.
- JSONL tool loop, loopback HTTP API, benchmark, verifier, demo-pack export, and static dashboard.

## Quickstart

```bash
uv sync --extra dev
uv run billing-bench init-demo --force
uv run billing-bench run-scenario scenario-0047
uv run billing-bench run-suite
uv run billing-bench verify
uv run billing-bench dashboard
```

HTTP API:

```bash
uv run billing-bench serve --host 127.0.0.1 --port 8793
```

JSONL tool loop:

```bash
printf '{"tool":"run_scenario","arguments":{"scenario_id":"scenario-0047"}}\n' | uv run billing-bench tool-loop
```

## Validation

```bash
uv run ruff check .
uv run pytest -q
uv run billing-bench run-suite
uv run billing-bench benchmark --iterations 100
uv run billing-bench verify
```

Generated runtime data is excluded from git.
