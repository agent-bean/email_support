#!/usr/bin/env python3
"""Explicitly exercise configured research providers and write private evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx2
from pydantic import BaseModel, ValidationError

from email_support.integrations.llm_gateway import GatewayClient
from email_support.integrations.openrouter_embeddings import OpenRouterEmbeddings
from email_support.integrations.provider_http import ProviderCallError
from email_support.integrations.tavily import TavilySearch
from email_support.integrations.web_fetch import WebFetcher
from email_support.models.research import (
    ApprovedCompany,
    ChatCompletionRequest,
    ChatCompletionResult,
    ChatMessage,
    ChatRole,
    EmbeddingBatch,
    ProviderUsage,
    PublicResearchRequest,
    ResearchRole,
    SearchTopic,
    ToolExecutionEvent,
    WebSearchResult,
)
from email_support.research_config import ResearchConfigurationError, ResearchSettings
from email_support.tools.execution import RunBudget, ToolExecutor
from email_support.tools.research import build_research_tools, request_public_research


class _StructuredOutput(BaseModel):
    status: Literal["ok"]


def _revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()[:40]


def _working_tree_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def _usage(usage: ProviderUsage | None) -> dict[str, int | str | None]:
    return {
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "cost_usd": str(usage.cost_usd)
        if usage and usage.cost_usd is not None
        else None,
        "provider_units": usage.provider_units if usage else None,
    }


def _write_private_report(path: Path, report: dict[str, object]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        raise


async def _run_live(settings: ResearchSettings) -> dict[str, object]:
    evidence: dict[str, object] = {
        "gateway_tool_call": {"status": "unsupported"},
        "structured_output": {"status": "unsupported"},
        "gateway_usage": {"status": "unknown", "usage": _usage(None)},
        "embeddings": {"status": "unsupported", "usage": _usage(None)},
        "search": {"status": "unsupported", "usage": _usage(None)},
    }
    timeout = httpx2.Timeout(settings.request_timeout_seconds)
    async with (
        httpx2.AsyncClient(
            timeout=timeout, follow_redirects=False, trust_env=False
        ) as gateway_http,
        httpx2.AsyncClient(
            timeout=timeout, follow_redirects=False, trust_env=False
        ) as embedding_http,
        httpx2.AsyncClient(
            timeout=timeout, follow_redirects=False, trust_env=False
        ) as search_http,
    ):
        gateway = GatewayClient(settings, gateway_http)
        search = TavilySearch(settings, search_http)
        fetcher = WebFetcher(
            max_bytes=settings.max_fetch_bytes,
            timeout_seconds=settings.request_timeout_seconds,
        )
        tools, _registry = build_research_tools(
            search,
            fetcher,
            approved_companies=frozenset({ApprovedCompany.MICROSOFT}),
        )
        budget = RunBudget(
            max_calls=settings.max_tool_calls,
            max_attempts=settings.max_attempts,
            max_concurrency=settings.max_concurrency,
            deadline_seconds=settings.total_deadline_seconds,
        )
        events: list[ToolExecutionEvent] = []
        executor = ToolExecutor(tools, budget, events=events)
        run_id = uuid4()
        try:
            completion = await request_public_research(
                gateway,
                settings.gateway_model,
                PublicResearchRequest(
                    company=ApprovedCompany.MICROSOFT,
                    topic=SearchTopic.COMPANY_OVERVIEW,
                ),
                executor,
                run_id=run_id,
            )
            evidence["gateway_usage"] = {
                "status": "passed" if completion.usage is not None else "unknown",
                "usage": _usage(completion.usage),
            }
            if completion.completion.tool_calls:
                call = completion.completion.tool_calls[0]
                tool_result = await executor.execute(
                    call.name,
                    ResearchRole.WEB_RESEARCH,
                    call.arguments,
                    run_id=run_id,
                )
                if not isinstance(tool_result, WebSearchResult):
                    raise ValueError("search tool returned an unexpected contract")
                evidence["gateway_tool_call"] = {"status": "passed"}
                evidence["search"] = {
                    "status": "passed" if tool_result.sources else "failed",
                    "usage": _usage(events[-1].usage),
                    "sources": len(tool_result.sources),
                }
            else:
                evidence["gateway_tool_call"] = {"status": "failed"}
        except ProviderCallError as error:
            evidence["gateway_tool_call"] = {
                "status": "failed",
                "category": error.category.value,
            }
        except Exception:
            evidence["gateway_tool_call"] = {
                "status": "failed",
                "category": "unexpected",
            }

        try:
            schema = {
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["ok"]}},
                "required": ["status"],
                "additionalProperties": False,
            }
            structured_request = ChatCompletionRequest(
                model=settings.gateway_model,
                messages=[
                    ChatMessage(
                        role=ChatRole.USER,
                        content='Return exactly {"status":"ok"}.',
                    )
                ],
                response_schema=schema,
                max_output_tokens=64,
            )
            structured_result = await executor.execute_provider_call(
                lambda: gateway.complete(structured_request),
                role=ResearchRole.WEB_RESEARCH,
                provider="gateway",
                model=settings.gateway_model,
                run_id=run_id,
            )
            if not isinstance(structured_result, ChatCompletionResult):
                raise ValueError("gateway returned an unexpected contract")
            structured = structured_result
            _StructuredOutput.model_validate_json(structured.completion.content or "")
            evidence["structured_output"] = {"status": "passed"}
            if structured.usage is not None:
                evidence["gateway_usage"] = {
                    "status": "passed",
                    "usage": _usage(structured.usage),
                }
        except (ProviderCallError, ValidationError):
            evidence["structured_output"] = {"status": "failed"}
        except Exception:
            evidence["structured_output"] = {"status": "failed"}

        try:
            embeddings_result = await executor.execute_provider_call(
                lambda: OpenRouterEmbeddings(settings, embedding_http).embed(
                    ["Public company overview smoke test."]
                ),
                role=ResearchRole.WEB_RESEARCH,
                provider="openrouter",
                model=settings.embedding_model,
                run_id=run_id,
            )
            if not isinstance(embeddings_result, EmbeddingBatch):
                raise ValueError("embedding provider returned an unexpected contract")
            embeddings = embeddings_result
            evidence["embeddings"] = {
                "status": "passed",
                "dimensions": len(embeddings.vectors[0].values),
                "usage": _usage(embeddings.usage),
            }
        except ProviderCallError as error:
            evidence["embeddings"] = {
                "status": "failed",
                "category": error.category.value,
            }
        except Exception:
            evidence["embeddings"] = {"status": "failed", "category": "unexpected"}

        search_evidence = evidence["search"]
        if (
            not isinstance(search_evidence, dict)
            or search_evidence.get("status") != "passed"
        ):
            try:
                result = await executor.execute(
                    "web_search",
                    ResearchRole.WEB_RESEARCH,
                    {
                        "company": ApprovedCompany.MICROSOFT.value,
                        "topic": SearchTopic.COMPANY_OVERVIEW.value,
                    },
                    run_id=run_id,
                )
                if not isinstance(result, WebSearchResult):
                    raise ValueError("search tool returned an unexpected contract")
                evidence["search"] = {
                    "status": "passed" if result.sources else "failed",
                    "usage": _usage(result.usage),
                    "sources": len(result.sources),
                }
            except ProviderCallError as error:
                evidence["search"] = {
                    "status": "failed",
                    "category": error.category.value,
                }
            except Exception:
                evidence["search"] = {"status": "failed", "category": "unexpected"}
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="make real provider requests"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new private JSON evidence file"
    )
    args = parser.parse_args()
    if not args.live:
        parser.error(
            "--live is required; this command never simulates provider results"
        )
    now = datetime.now(UTC).isoformat()
    try:
        settings = ResearchSettings.from_environment(os.environ)
    except ResearchConfigurationError as error:
        report: dict[str, object] = {
            "status": "unsupported",
            "reason": str(error),
            "checked_at_utc": now,
            "revision": _revision(),
            "working_tree_dirty": _working_tree_dirty(),
            "capabilities": {},
        }
        _write_private_report(args.output, report)
        print("research provider smoke: unsupported (configuration missing)")
        return 2
    try:
        capabilities = asyncio.run(_run_live(settings))
    except Exception:
        capabilities = {"smoke": {"status": "failed", "category": "unexpected"}}
    required = [
        "gateway_tool_call",
        "structured_output",
        "gateway_usage",
        "embeddings",
        "search",
    ]
    complete = True
    for name in required:
        capability = capabilities.get(name)
        if not isinstance(capability, dict) or capability.get("status") != "passed":
            complete = False
            break
    report = {
        "status": "passed" if complete else "incomplete",
        "checked_at_utc": now,
        "revision": _revision(),
        "working_tree_dirty": _working_tree_dirty(),
        "models": {
            "gateway": settings.gateway_model,
            "embeddings": settings.embedding_model,
        },
        "capabilities": capabilities,
    }
    _write_private_report(args.output, report)
    print(f"research provider smoke: {report['status']}")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
