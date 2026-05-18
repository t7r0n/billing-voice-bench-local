from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .engine import BillingVoiceBench


def create_app() -> FastAPI:
    app = FastAPI(title="Billing Voice Bench Local", version="0.1.0")
    bench = BillingVoiceBench()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "scenarios": len(bench.scenarios())}

    @app.post("/tools/{tool_name}")
    def tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return bench.route_tool(tool_name, arguments)

    return app


app = create_app()
