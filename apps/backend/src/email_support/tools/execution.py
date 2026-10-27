"""Permission-checked tool execution with one per-run budget and safe events."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import (
    ProviderErrorCategory,
    ProviderUsage,
    ResearchRole,
    ToolExecutionEvent,
    ToolMetadata,
    ToolName,
    ToolOutcome,
)

ToolFunction = Callable[[BaseModel], Awaitable[BaseModel]]


@dataclass(frozen=True, slots=True)
class ResearchTool:
    name: ToolName
    description: str
    provider: str
    model: str | None
    allowed_roles: frozenset[ResearchRole]
    argument_model: type[BaseModel]
    result_model: type[BaseModel]
    function: ToolFunction

    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.name,
            description=self.description,
            arguments_schema=self.argument_model.model_json_schema(),
            result_schema=self.result_model.model_json_schema(),
        )


@dataclass(slots=True)
class RunBudget:
    max_calls: int
    max_attempts: int
    max_concurrency: int
    deadline_seconds: float
    calls_used: int = 0
    attempts_used: int = 0
    _started: float = field(default_factory=time.monotonic, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _semaphore: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        if min(self.max_calls, self.max_attempts, self.max_concurrency) < 1:
            raise ValueError("research budget counts must be positive")
        if self.deadline_seconds <= 0:
            raise ValueError("research deadline must be positive")
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    @property
    def remaining_seconds(self) -> float:
        return self.deadline_seconds - (time.monotonic() - self._started)

    async def reserve_call(self) -> None:
        async with self._lock:
            if self.calls_used >= self.max_calls or self.remaining_seconds <= 0:
                raise ProviderCallError(ProviderErrorCategory.BUDGET_EXHAUSTED)
            self.calls_used += 1

    async def reserve_attempt(self) -> None:
        async with self._lock:
            run_attempt_limit = self.max_calls * self.max_attempts
            if self.attempts_used >= run_attempt_limit or self.remaining_seconds <= 0:
                raise ProviderCallError(ProviderErrorCategory.BUDGET_EXHAUSTED)
            self.attempts_used += 1

    async def acquire(self) -> asyncio.Semaphore:
        return self._semaphore


Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[], float]


class ToolExecutor:
    def __init__(
        self,
        tools: Iterable[ResearchTool],
        budget: RunBudget,
        *,
        events: list[ToolExecutionEvent] | None = None,
        sleep: Sleep = asyncio.sleep,
        jitter: Jitter = random.random,
    ) -> None:
        self._tools: dict[ToolName, ResearchTool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError("duplicate research tool name")
            self._tools[tool.name] = tool
        self._budget = budget
        self.events = events if events is not None else []
        self._sleep = sleep
        self._jitter = jitter

    def metadata(self, role: ResearchRole) -> list[ToolMetadata]:
        return [
            tool.metadata()
            for tool in self._tools.values()
            if role in tool.allowed_roles
        ]

    async def execute(
        self,
        name: str,
        role: ResearchRole,
        arguments: object,
        *,
        run_id: UUID,
        parent_execution_id: UUID | None = None,
    ) -> BaseModel:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        event_id = uuid4()
        tool: ResearchTool | None = None
        attempts = 0
        try:
            try:
                tool_name = ToolName(name)
            except ValueError:
                raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST) from None
            tool = self._tools.get(tool_name)
            if tool is None:
                raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
            if role not in tool.allowed_roles:
                raise ProviderCallError(ProviderErrorCategory.PERMISSION)
            try:
                parsed_arguments = tool.argument_model.model_validate(arguments)
            except ValidationError:
                raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST) from None
            await self._budget.reserve_call()
            async with asyncio.timeout(self._budget.remaining_seconds):
                semaphore = await self._budget.acquire()
                async with semaphore:
                    while True:
                        await self._budget.reserve_attempt()
                        attempts += 1
                        try:
                            result = await tool.function(parsed_arguments)
                            if not isinstance(result, tool.result_model):
                                raise ProviderCallError(
                                    ProviderErrorCategory.MALFORMED_RESPONSE
                                )
                            self._record(
                                event_id,
                                run_id,
                                parent_execution_id,
                                role,
                                tool,
                                started_at,
                                started,
                                ToolOutcome.SUCCEEDED,
                                None,
                                _usage(result),
                                attempts,
                            )
                            return result
                        except ProviderCallError as error:
                            if not self._can_retry(error, attempts):
                                raise
                            await self._sleep(self._retry_delay(error, attempts))
        except asyncio.CancelledError:
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                tool,
                started_at,
                started,
                ToolOutcome.FAILED,
                ProviderErrorCategory.CANCELLED,
                None,
                attempts,
            )
            raise
        except TimeoutError:
            timeout_error = ProviderCallError(ProviderErrorCategory.TIMEOUT)
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                tool,
                started_at,
                started,
                ToolOutcome.FAILED,
                timeout_error.category,
                None,
                attempts,
            )
            raise timeout_error from None
        except ProviderCallError as provider_error:
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                tool,
                started_at,
                started,
                ToolOutcome.FAILED,
                provider_error.category,
                None,
                attempts,
            )
            raise
        except Exception:
            tool_error = ProviderCallError(ProviderErrorCategory.TOOL_FAILURE)
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                tool,
                started_at,
                started,
                ToolOutcome.FAILED,
                tool_error.category,
                None,
                attempts,
            )
            raise tool_error from None

    async def execute_provider_call(
        self,
        call: Callable[[], Awaitable[BaseModel]],
        *,
        role: ResearchRole,
        provider: str,
        model: str | None,
        run_id: UUID,
        parent_execution_id: UUID | None = None,
    ) -> BaseModel:
        """Budget and trace one non-retried provider request in this run."""
        started_at = datetime.now(UTC)
        started = time.monotonic()
        event_id = uuid4()
        attempts = 0
        try:
            await self._budget.reserve_call()
            async with asyncio.timeout(self._budget.remaining_seconds):
                async with await self._budget.acquire():
                    await self._budget.reserve_attempt()
                    attempts += 1
                    result = await call()
                    if not isinstance(result, BaseModel):
                        raise ProviderCallError(
                            ProviderErrorCategory.MALFORMED_RESPONSE
                        )
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                None,
                started_at,
                started,
                ToolOutcome.SUCCEEDED,
                None,
                _usage(result),
                attempts,
                provider=provider,
                model=model,
            )
            return result
        except asyncio.CancelledError:
            category = ProviderErrorCategory.CANCELLED
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                None,
                started_at,
                started,
                ToolOutcome.FAILED,
                category,
                None,
                attempts,
                provider=provider,
                model=model,
            )
            raise
        except TimeoutError:
            error = ProviderCallError(ProviderErrorCategory.TIMEOUT)
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                None,
                started_at,
                started,
                ToolOutcome.FAILED,
                error.category,
                None,
                attempts,
                provider=provider,
                model=model,
            )
            raise error from None
        except ProviderCallError as provider_error:
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                None,
                started_at,
                started,
                ToolOutcome.FAILED,
                provider_error.category,
                None,
                attempts,
                provider=provider,
                model=model,
            )
            raise
        except Exception:
            error = ProviderCallError(ProviderErrorCategory.TOOL_FAILURE)
            self._record(
                event_id,
                run_id,
                parent_execution_id,
                role,
                None,
                started_at,
                started,
                ToolOutcome.FAILED,
                error.category,
                None,
                attempts,
                provider=provider,
                model=model,
            )
            raise error from None

    def _can_retry(self, error: ProviderCallError, attempts: int) -> bool:
        return (
            attempts < self._budget.max_attempts
            and error.category
            in {
                ProviderErrorCategory.RATE_LIMITED,
                ProviderErrorCategory.PROVIDER_UNAVAILABLE,
            }
            and self._budget.remaining_seconds > 0
        )

    def _retry_delay(self, error: ProviderCallError, attempts: int) -> float:
        ceiling = float(min(0.25 * (2 ** (attempts - 1)), 2.0))
        jitter = min(max(float(self._jitter()), 0.0), 1.0)
        backoff = ceiling * (0.5 + jitter * 0.5)
        retry_after = error.retry_after_seconds
        if retry_after is not None:
            backoff = max(backoff, min(max(retry_after, 0.0), 5.0))
        return min(backoff, max(self._budget.remaining_seconds, 0.0))

    def _record(
        self,
        event_id: UUID,
        run_id: UUID,
        parent_execution_id: UUID | None,
        role: ResearchRole,
        tool: ResearchTool | None,
        started_at: datetime,
        started: float,
        outcome: ToolOutcome,
        error_category: ProviderErrorCategory | None,
        usage: ProviderUsage | None,
        attempts: int,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.events.append(
            ToolExecutionEvent(
                id=event_id,
                run_id=run_id,
                parent_execution_id=parent_execution_id,
                role=role,
                tool=tool.name if tool is not None else None,
                provider=tool.provider if tool is not None else provider or "executor",
                model=tool.model if tool is not None else model,
                started_at=started_at,
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                outcome=outcome,
                error_category=error_category,
                usage=usage,
                attempt_count=attempts,
            )
        )


def _usage(result: BaseModel) -> ProviderUsage | None:
    usage = getattr(result, "usage", None)
    return usage if isinstance(usage, ProviderUsage) else None
