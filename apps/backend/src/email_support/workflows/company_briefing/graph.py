"""Shared sequential briefing graph with canonical persistence before review pause."""

from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class BriefingState(TypedDict, total=False):
    run_id: str
    input_id: str
    public_request: dict[str, Any]
    resolution: dict[str, Any]
    context: dict[str, Any]
    research: dict[str, Any]
    report: dict[str, Any]
    binding: dict[str, Any]
    stop_reason: str


class BriefingRuntime(Protocol):
    async def resolve(self, run_id: str, input_id: str) -> dict[str, Any]: ...
    async def context(self, resolution: dict[str, Any]) -> dict[str, Any]: ...
    async def research(self, public_request: dict[str, Any]) -> dict[str, Any]: ...
    async def synthesize(
        self,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def persist(
        self,
        run_id: str,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]: ...
    async def validate_binding(self, run_id: str, binding: dict[str, Any]) -> None: ...


def create_graph(runtime: BriefingRuntime, checkpointer: Any) -> Any:
    async def resolve(state: BriefingState) -> dict[str, Any]:
        result = await runtime.resolve(state["run_id"], state["input_id"])
        return {"resolution": result, "stop_reason": result.get("stop_reason", "")}

    def route(state: BriefingState) -> str:
        return "stop" if state.get("stop_reason") else "context"

    async def context(state: BriefingState) -> dict[str, Any]:
        return {"context": await runtime.context(state["resolution"])}

    async def research(state: BriefingState) -> dict[str, Any]:
        return {"research": await runtime.research(state["public_request"])}

    async def synthesize(state: BriefingState) -> dict[str, Any]:
        return {
            "report": await runtime.synthesize(
                state["resolution"], state["context"], state["research"]
            )
        }

    async def persist(state: BriefingState) -> dict[str, Any]:
        binding = await runtime.persist(
            state["run_id"],
            state["resolution"],
            state["context"],
            state["research"],
            state["report"],
        )
        return {"binding": binding}

    async def approval(state: BriefingState) -> dict[str, Any]:
        await runtime.validate_binding(state["run_id"], state["binding"])
        interrupt({"run_id": state["run_id"], **state["binding"]})
        return {}

    graph = StateGraph(BriefingState)
    for name, node in [
        ("resolve", resolve),
        ("context", context),
        ("research", research),
        ("synthesize", synthesize),
        ("persist", persist),
        ("approval", approval),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "resolve")
    graph.add_conditional_edges("resolve", route, {"stop": END, "context": "context"})
    graph.add_edge("context", "research")
    graph.add_edge("research", "synthesize")
    graph.add_edge("synthesize", "persist")
    graph.add_edge("persist", "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=checkpointer)


async def ensure_review_pause(
    graph: Any,
    config: dict[str, Any],
    *,
    run_id: str,
    input_id: str,
    public_request: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    """Repair only the review checkpoint after canonical binding is validated."""
    state = await graph.aget_state(config)
    if (
        state.values.get("run_id") == run_id
        and state.values.get("input_id") == input_id
        and state.values.get("public_request") == public_request
        and state.values.get("binding") == binding
        and state.next == ("approval",)
    ):
        return
    await graph.aupdate_state(
        config,
        {
            "run_id": run_id,
            "input_id": input_id,
            "public_request": public_request,
            "binding": binding,
        },
        as_node="persist",
    )
    result = await graph.ainvoke(None, config, durability="sync")
    if not result.get("__interrupt__") or result.get("binding") != binding:
        raise RuntimeError("review pause could not be restored")
