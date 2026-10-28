"""Production roles for a company briefing, with canonical dependency checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from email_support.agents.email_interpretation import EmailInterpretationAgent
from email_support.agents.report_generation import (
    Gateway,
    SynthesisEvidence,
    SynthesisInput,
    generate_report,
)
from email_support.agents.web_research import (
    ApprovedResearch,
    ResearchOutput,
    research_public,
)
from email_support.models.email_interpretation import (
    CompanyIdentityStatus,
    EmailRelevance,
    NormalizedInputCreate,
)
from email_support.models.persistence import EvidenceCreate, EvidenceKind
from email_support.models.persistence.briefing_runs import (
    BriefingRunCreate,
    KnowledgeDependency,
)
from email_support.services.briefing_ownership import RunOwnership
from email_support.services.company_identity import CompanyIdentityService
from email_support.storage.postgres.persistence.briefing_runs import (
    bind_briefing,
    current_run,
    resolve_run,
    stop_run,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    create_evidence,
)
from email_support.storage.postgres.persistence.decisions import list_eligible_knowledge
from email_support.storage.postgres.persistence.identity import get_normalized_input
from email_support.tools.execution import ToolExecutor
from email_support.workflows.company_briefing.report import BriefingReport


class ProductionRuntime:
    def __init__(
        self,
        *,
        owner: RunOwnership,
        input_value: NormalizedInputCreate,
        config_hash: str,
        run_id: UUID,
        approved_company_id: UUID,
        interpreter: EmailInterpretationAgent,
        gateway: Gateway,
        model: str,
        executor: ToolExecutor,
    ) -> None:
        self.owner = owner
        self.input = input_value
        self.config_hash = config_hash
        self.approved_company_id = approved_company_id
        self.interpreter = interpreter
        self.gateway = gateway
        self.model = model
        self.executor = executor
        self.run_id = run_id

    async def resolve(self, run_id: str, input_id: str) -> dict[str, Any]:
        run = UUID(run_id)
        if run != self.run_id:
            raise PersistenceConflict("run identity differs from request")
        interpretation = await self.interpreter.interpret(self.input, run_id=run)
        async with self.owner.transaction() as session:
            source = await get_normalized_input(session, UUID(input_id))
            if source.content_hash != self.input.content_hash:
                raise PersistenceConflict("input content changed")
            identity = await CompanyIdentityService(session).resolve(
                source, interpretation
            )
            reason = ""
            if interpretation.relevance is not EmailRelevance.RELEVANT:
                reason = interpretation.relevance.value
            elif identity.status is not CompanyIdentityStatus.RESOLVED:
                reason = identity.status.value
            elif identity.company_id != self.approved_company_id:
                reason = "public_research_company_mismatch"
            if reason:
                await stop_run(session, run, reason)
                return {
                    "stop_reason": reason,
                    "identity": identity.model_dump(mode="json"),
                    "interpretation": interpretation.model_dump(mode="json"),
                }
            assert (
                identity.company_id
                and identity.contact_id
                and identity.identity_revision
            )
            knowledge = await list_eligible_knowledge(session, identity.company_id)
            dependencies = tuple(
                KnowledgeDependency(
                    knowledge_id=item.id,
                    briefing_version_id=item.briefing_version_id,
                    approval_id=item.approval_id,
                )
                for item in knowledge
            )
            await resolve_run(
                session,
                BriefingRunCreate(
                    id=run,
                    input_id=source.id,
                    company_id=identity.company_id,
                    contact_id=identity.contact_id,
                    identity_revision=identity.identity_revision,
                    input_hash=source.content_hash,
                    config_hash=self.config_hash,
                    dependencies=dependencies,
                ),
            )
            return {
                "identity": identity.model_dump(mode="json"),
                "interpretation": interpretation.model_dump(mode="json"),
            }

    def _run(self) -> UUID:
        return self.run_id

    async def context(self, resolution: dict[str, Any]) -> dict[str, Any]:
        async with self.owner.transaction() as session:
            row = await current_run(session, self._run())
            assert row.company_id is not None
            knowledge = await list_eligible_knowledge(session, row.company_id)
            captured = {str(item["knowledge_id"]) for item in row.dependencies}
            selected = [item for item in knowledge if str(item.id) in captured]
            if len(selected) != len(captured):
                raise PersistenceConflict("knowledge dependency is stale")
            return {"knowledge": [item.model_dump(mode="json") for item in selected]}

    async def research(self, public_request: dict[str, Any]) -> dict[str, Any]:
        value = ApprovedResearch.model_validate(public_request)
        result = await research_public(value, self.executor, self._run())
        return result.model_dump(mode="json")

    async def synthesize(
        self,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        fresh = await self.context(resolution)
        if fresh != context:
            raise PersistenceConflict("cached knowledge context changed")
        public = ResearchOutput.model_validate(research)
        evidence = [
            SynthesisEvidence(
                id="email", origin="email", content=self.input.payload.model_dump_json()
            )
        ]
        if self.input.payload.meeting is not None:
            evidence.append(
                SynthesisEvidence(
                    id="meeting",
                    origin="meeting",
                    content=self.input.payload.meeting.model_dump_json(),
                )
            )
        for source in public.sources:
            evidence.append(
                SynthesisEvidence(
                    id=str(source.source_id), origin="public", content=source.text
                )
            )
        for item in context["knowledge"]:
            if item["evidence_ids"]:
                evidence.append(
                    SynthesisEvidence(
                        id=str(item["id"]), origin="knowledge", content=item["content"]
                    )
                )
        report = await generate_report(
            self.gateway,
            self.model,
            self.executor,
            SynthesisInput(evidence=evidence, gaps=public.gaps),
            self._run(),
        )
        return report.model_dump(mode="json")

    async def persist(
        self,
        run_id: str,
        resolution: dict[str, Any],
        context: dict[str, Any],
        research: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        value = BriefingReport.model_validate(report)
        public = ResearchOutput.model_validate(research)
        async with self.owner.transaction() as session:
            run = await current_run(session, UUID(run_id))
            if run.briefing_version_id is not None:
                return {
                    "briefing_id": str(run.briefing_id),
                    "version_id": str(run.briefing_version_id),
                }
            assert run.company_id is not None
            knowledge = await list_eligible_knowledge(session, run.company_id)
            captured = {str(item["knowledge_id"]) for item in run.dependencies}
            selected = [
                item.model_dump(mode="json")
                for item in knowledge
                if str(item.id) in captured
            ]
            if context != {"knowledge": selected}:
                raise PersistenceConflict("cached knowledge context changed")
            referenced = {ref for claim in value.claims for ref in claim.evidence_ids}
            links: dict[str, list[UUID]] = {}
            labels: dict[str, str] = {}
            now = datetime.now(UTC)
            for ref in ("email", "meeting"):
                if ref in referenced:
                    content = (
                        self.input.payload.model_dump_json()
                        if ref == "email"
                        else self.input.payload.meeting.model_dump_json()
                        if self.input.payload.meeting
                        else ""
                    )
                    item = await create_evidence(
                        session,
                        EvidenceCreate(
                            kind=EvidenceKind.NORMALIZED_INPUT,
                            mail_message_id=None,
                            meeting_id=None,
                            source_url=None,
                            normalized_input_id=run.input_id,
                            source_text=content,
                            retrieved_at=now,
                        ),
                    )
                    links[ref] = [item.id]
                    labels[ref] = f"normalized input {item.id}"
            for source in public.sources:
                ref = str(source.source_id)
                if ref in referenced:
                    item = await create_evidence(
                        session,
                        EvidenceCreate(
                            kind=EvidenceKind.WEB,
                            mail_message_id=None,
                            meeting_id=None,
                            source_url=source.url,
                            source_text=source.text,
                            retrieved_at=public.retrieved_at,
                        ),
                    )
                    links[ref] = [item.id]
                    labels[ref] = str(source.url)
            for item in context["knowledge"]:
                ref = str(item["id"])
                if ref in referenced:
                    links[ref] = [UUID(value) for value in item["evidence_ids"]]
                    labels[ref] = f"approved knowledge {ref}"
            if referenced != set(links):
                raise PersistenceConflict("missing source for generated claim")
            markdown = (
                value.render()
                + "\n## Source gaps\n"
                + (
                    "".join(f"- {gap}\n" for gap in public.gaps)
                    if public.gaps
                    else "- No source gaps reported during research.\n"
                )
                + "\n## Sources\n"
                + "".join(f"- [{ref}]: {labels[ref]}\n" for ref in sorted(referenced))
            )
            result = await bind_briefing(
                session,
                UUID(run_id),
                markdown,
                sorted({item for values in links.values() for item in values}, key=str),
            )
            return {
                "briefing_id": str(result.briefing_id),
                "version_id": str(result.briefing_version_id),
            }

    async def validate_binding(self, run_id: str, binding: dict[str, Any]) -> None:
        async with self.owner.transaction() as session:
            run = await current_run(session, UUID(run_id))
            if run.status != "pending_review" or binding != {
                "briefing_id": str(run.briefing_id),
                "version_id": str(run.briefing_version_id),
            }:
                raise PersistenceConflict("briefing binding is stale")
