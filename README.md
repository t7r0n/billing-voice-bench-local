# Billing Voice Bench Local

Local benchmark for patient-billing voice-agent safety behavior.

The project simulates patient billing calls, generates deterministic agent responses, and grades the transcript for grounded claims, correct refusals, escalation timing, and interruption handling. It is designed for local demos and regression testing with synthetic data only; no external API or phone provider is required.

## Why this exists

Local benchmark for patient-billing voice-agent safety behavior.

## System behavior

- 200 deterministic synthetic patient-billing scenarios with EOB-style line items.
- 12 refusal categories covering medical advice, policy invention, eligibility promises, payment-plan promises, privacy-sensitive requests, and other high-risk billing surfaces.
- Deterministic graders for groundedness, refusal precision, escalation latency, and interruption fidelity.
- Local adversary simulator that replays patient turns and interruption events against candidate and baseline agents.
- JSONL tool loop, loopback HTTP API, benchmark, verifier, demo-pack export, and static dashboard.

## Runbook

```bash
uv sync --extra dev
uv run billing-bench init-demo --force
uv run billing-bench run-scenario scenario-0047
uv run billing-bench run-suite
uv run billing-bench verify
uv run billing-bench dashboard
```

```bash
uv run billing-bench serve --host 127.0.0.1 --port 8793
```

## Inspection points

- `outputs/summary.json` for headline metrics and gate status
- `outputs/reports.json` for per-case results
- `outputs/dashboard.html` for visual inspection
- `outputs/demo-pack.zip` or `outputs/demo_pack/` for portable review

## Verification

```bash
uv run ruff check .
uv run pytest -q
uv run billing-bench run-suite
uv run billing-bench benchmark --iterations 100
uv run billing-bench verify
```

## Privacy model

The `billing-voice-bench-local` public surface is source, tests, lockfile, and docs. It does not need credentials, browser state, customer records, or hosted services.
