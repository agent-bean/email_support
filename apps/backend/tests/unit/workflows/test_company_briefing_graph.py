from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from email_support.workflows.company_briefing.graph import create_graph


class Runtime:
    def __init__(self, stop: bool = False) -> None:
        self.stop = stop
        self.steps: list[str] = []

    async def resolve(self, run_id: str, input_id: str) -> dict[str, Any]:
        self.steps.append("resolve")
        return {"stop_reason": "irrelevant" if self.stop else "", "private": "CANARY"}

    async def context(self, resolution: dict[str, Any]) -> dict[str, Any]:
        self.steps.append("context")
        return {"private": "CANARY"}

    async def research(self, public_request: dict[str, Any]) -> dict[str, Any]:
        self.steps.append("research")
        assert "CANARY" not in str(public_request)
        return {"source": "public"}

    async def synthesize(
        self,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        self.steps.append("synthesize")
        return {"draft": "draft"}

    async def persist(
        self,
        run_id: str,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        self.steps.append("persist")
        return {"briefing_id": "briefing", "version_id": "version"}

    async def validate_binding(self, run_id: str, binding: dict[str, Any]) -> None:
        self.steps.append("validate")


@pytest.mark.asyncio
async def test_stop_does_not_invoke_research_or_persist() -> None:
    runtime = Runtime(stop=True)
    graph = create_graph(runtime, InMemorySaver())
    result = await graph.ainvoke(
        {"run_id": "r", "input_id": "i", "public_request": {}},
        {"configurable": {"thread_id": "r"}},
        durability="sync",
    )
    assert result["stop_reason"] == "irrelevant"
    assert runtime.steps == ["resolve"]


@pytest.mark.asyncio
async def test_public_research_is_separate_and_pause_follows_binding() -> None:
    runtime = Runtime()
    graph = create_graph(runtime, InMemorySaver())
    result = await graph.ainvoke(
        {"run_id": "r", "input_id": "i", "public_request": {"company": "approved"}},
        {"configurable": {"thread_id": "r"}},
        durability="sync",
    )
    assert runtime.steps == [
        "resolve",
        "context",
        "research",
        "synthesize",
        "persist",
        "validate",
    ]
    assert result["__interrupt__"][0].value == {
        "run_id": "r",
        "briefing_id": "briefing",
        "version_id": "version",
    }
