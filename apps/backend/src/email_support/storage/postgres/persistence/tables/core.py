"""SQLAlchemy mappings for canonical inputs, evidence and briefings."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProviderAccountRow(Base):
    __tablename__ = "provider_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_account_id", name="uq_provider_accounts_external"
        ),
        CheckConstraint(
            "length(btrim(provider)) > 0", name="ck_provider_accounts_provider_nonblank"
        ),
        CheckConstraint(
            "length(btrim(external_account_id)) > 0",
            name="ck_provider_accounts_external_id_nonblank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompanyRow(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_companies_name_nonblank"),
        CheckConstraint(
            "domain IS NULL OR length(btrim(domain)) > 0",
            name="ck_companies_domain_nonblank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContactRow(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint("length(btrim(email)) > 0", name="ck_contacts_email_nonblank"),
        Index(
            "uq_contacts_email_domain_lower",
            text(
                "((split_part(email, '@'::text, 1) || '@'::text) || "
                "lower(split_part(email, '@'::text, 2)))"
            ),
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", name="fk_contacts_company_id", ondelete="RESTRICT"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MailMessageRow(Base):
    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "external_message_id",
            name="uq_mail_messages_account_external",
        ),
        CheckConstraint(
            "length(btrim(external_message_id)) > 0",
            name="ck_mail_messages_external_id_nonblank",
        ),
        CheckConstraint(
            "length(btrim(sender_email)) > 0", name="ck_mail_messages_sender_nonblank"
        ),
        CheckConstraint(
            "recipient_emails IS NULL OR (jsonb_typeof(recipient_emails) = 'array' "
            "AND NOT jsonb_path_exists(recipient_emails, "
            "'$[*] ? (@.type() != \"string\")'))",
            name="ck_mail_messages_recipient_array",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "provider_accounts.id",
            name="fk_mail_messages_account_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    external_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_emails: Mapped[list[str] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "companies.id", name="fk_mail_messages_company_id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "contacts.id", name="fk_mail_messages_contact_id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MeetingRow(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "external_calendar_id",
            "external_event_id",
            name="uq_meetings_account_calendar_event",
        ),
        CheckConstraint(
            "length(btrim(external_calendar_id)) > 0 AND "
            "length(btrim(external_event_id)) > 0",
            name="ck_meetings_external_keys_nonblank",
        ),
        CheckConstraint(
            "(time_kind = 'timed' AND starts_at IS NOT NULL AND ends_at IS NOT NULL "
            "AND starts_at < ends_at AND start_date IS NULL AND end_date IS NULL) OR "
            "(time_kind = 'all_day' AND starts_at IS NULL AND ends_at IS NULL "
            "AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND start_date < end_date)",
            name="ck_meetings_time_shape",
        ),
        CheckConstraint(
            "attendee_emails IS NULL OR (jsonb_typeof(attendee_emails) = 'array' "
            "AND NOT jsonb_path_exists(attendee_emails, "
            "'$[*] ? (@.type() != \"string\")'))",
            name="ck_meetings_attendee_array",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "provider_accounts.id", name="fk_meetings_account_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    external_calendar_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organizer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    attendee_emails: Mapped[list[str] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    time_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", name="fk_meetings_company_id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'mail' AND mail_message_id IS NOT NULL AND meeting_id IS NULL "
            "AND source_url IS NULL) OR "
            "(kind = 'meeting' AND mail_message_id IS NULL AND meeting_id IS NOT NULL "
            "AND source_url IS NULL) OR "
            "(kind = 'web' AND mail_message_id IS NULL AND meeting_id IS NULL "
            "AND source_url IS NOT NULL)",
            name="ck_evidence_source_matches_kind",
        ),
        CheckConstraint(
            "length(btrim(source_text)) > 0", name="ck_evidence_source_text_nonblank"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    mail_message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "mail_messages.id", name="fk_evidence_mail_message_id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    meeting_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("meetings.id", name="fk_evidence_meeting_id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BriefingRow(Base):
    __tablename__ = "briefings"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", name="fk_briefings_company_id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BriefingVersionRow(Base):
    __tablename__ = "briefing_versions"
    __table_args__ = (
        UniqueConstraint(
            "briefing_id", "version_number", name="uq_briefing_versions_number"
        ),
        UniqueConstraint(
            "briefing_id", "id", name="uq_briefing_versions_briefing_id_id"
        ),
        CheckConstraint(
            "version_number > 0", name="ck_briefing_versions_positive_number"
        ),
        CheckConstraint(
            "length(btrim(markdown)) > 0", name="ck_briefing_versions_markdown_nonblank"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    briefing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "briefings.id", name="fk_briefing_versions_briefing_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    sealed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BriefingVersionEvidenceRow(Base):
    __tablename__ = "briefing_version_evidence"

    briefing_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "briefing_versions.id",
            name="fk_briefing_version_evidence_version_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "evidence.id",
            name="fk_briefing_version_evidence_evidence_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
