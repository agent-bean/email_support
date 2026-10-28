"""Subprocess fixture: terminate immediately after canonical briefing commit."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from email_support.agents.email_interpretation import EmailInterpretationAgent
from email_support.agents.web_research import ApprovedResearch
from email_support.models.email_interpretation import NormalizedInputCreate
from email_support.services.briefing_attempts import BriefingAttemptJournal
from email_support.services.briefing_ownership import acquire_run_ownership
from email_support.storage.postgres.checkpoints import checkpoint_saver
from email_support.storage.postgres.persistence.database import create_database_engine
from email_support.tools.execution import RunBudget, ToolExecutor
from email_support.tools.research import build_research_tools
from email_support.workflows.company_briefing.graph import create_graph
from email_support.workflows.company_briefing.runtime import ProductionRuntime
from tests.database.workflows.test_production_graph import Fetch, Gateway, Search


class ExitBeforePause(ProductionRuntime):
    async def validate_binding(self, run_id: str, binding: dict[str, Any]) -> None:
        os._exit(73)


async def run(path: Path) -> None:
    data = json.loads(path.read_text())
    db_url = os.environ["EMAIL_SUPPORT_DATABASE_URL"]
    engine = create_database_engine(db_url)
    public = ApprovedResearch.model_validate(data["public"])
    run_id = UUID(data["run_id"])
    async with acquire_run_ownership(engine, run_id) as owner:
        async with checkpoint_saver(db_url) as saver:
            tools, _ = build_research_tools(
                Search(), Fetch(), approved_companies=frozenset({public.company})
            )
            executor = ToolExecutor(
                tools,
                RunBudget(
                    max_calls=5, max_attempts=1, max_concurrency=1, deadline_seconds=10
                ),
                journal=BriefingAttemptJournal(owner, 5),
            )
            gateway = Gateway()
            runtime = ExitBeforePause(
                owner=owner,
                input_value=NormalizedInputCreate.model_validate(data["input"]),
                config_hash="a" * 64,
                run_id=run_id,
                approved_company_id=UUID(data["company_id"]),
                interpreter=EmailInterpretationAgent(gateway, "model", executor),
                gateway=gateway,
                model="model",
                executor=executor,
            )
            graph = create_graph(runtime, saver)
            await owner.supervise(
                graph.ainvoke(
                    {
                        "run_id": str(run_id),
                        "input_id": data["input_id"],
                        "public_request": public.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": str(run_id)}},
                    durability="sync",
                )
            )
    raise RuntimeError("fixture did not reach the pause")


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1])))
