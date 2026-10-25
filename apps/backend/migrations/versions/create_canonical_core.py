"""Create canonical inputs, source evidence and briefing history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a31f5e702c84"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(regexp_replace(provider, '[[:space:]]', '', 'g')) > 0",
            name="ck_provider_accounts_provider_nonblank",
        ),
        sa.CheckConstraint(
            "length(regexp_replace(external_account_id, '[[:space:]]', '', 'g')) > 0",
            name="ck_provider_accounts_external_id_nonblank",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_accounts"),
        sa.UniqueConstraint(
            "provider", "external_account_id", name="uq_provider_accounts_external"
        ),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(regexp_replace(name, '[[:space:]]', '', 'g')) > 0",
            name="ck_companies_name_nonblank",
        ),
        sa.CheckConstraint(
            "domain IS NULL OR "
            "length(regexp_replace(domain, '[[:space:]]', '', 'g')) > 0",
            name="ck_companies_domain_nonblank",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
    )
    op.create_table(
        "briefings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_briefings_company_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_briefings"),
    )
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(regexp_replace(email, '[[:space:]]', '', 'g')) > 0",
            name="ck_contacts_email_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_contacts_company_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
    )
    op.create_index(
        "uq_contacts_email_domain_lower",
        "contacts",
        [
            sa.text(
                "(split_part(email, '@', 1) || '@' || lower(split_part(email, '@', 2)))"
            )
        ],
        unique=True,
    )
    op.create_table(
        "mail_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("external_message_id", sa.Text(), nullable=False),
        sa.Column("external_thread_id", sa.Text(), nullable=True),
        sa.Column("sender_email", sa.Text(), nullable=False),
        sa.Column(
            "recipient_emails", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(regexp_replace(external_message_id, '[[:space:]]', '', 'g')) > 0",
            name="ck_mail_messages_external_id_nonblank",
        ),
        sa.CheckConstraint(
            "length(regexp_replace(sender_email, '[[:space:]]', '', 'g')) > 0",
            name="ck_mail_messages_sender_nonblank",
        ),
        sa.CheckConstraint(
            "recipient_emails IS NULL OR (jsonb_typeof(recipient_emails) = 'array' "
            "AND NOT jsonb_path_exists(recipient_emails, "
            "'$[*] ? (@.type() != \"string\")'))",
            name="ck_mail_messages_recipient_array",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["provider_accounts.id"],
            name="fk_mail_messages_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_mail_messages_company_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name="fk_mail_messages_contact_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mail_messages"),
        sa.UniqueConstraint(
            "account_id",
            "external_message_id",
            name="uq_mail_messages_account_external",
        ),
    )
    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("external_calendar_id", sa.Text(), nullable=False),
        sa.Column("external_event_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organizer_email", sa.Text(), nullable=True),
        sa.Column(
            "attendee_emails", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("time_kind", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(regexp_replace(external_calendar_id, '[[:space:]]', '', 'g')) > 0 "
            "AND "
            "length(regexp_replace(external_event_id, '[[:space:]]', '', 'g')) > 0",
            name="ck_meetings_external_keys_nonblank",
        ),
        sa.CheckConstraint(
            "(time_kind = 'timed' AND starts_at IS NOT NULL AND ends_at IS NOT NULL "
            "AND starts_at < ends_at AND start_date IS NULL AND end_date IS NULL) OR "
            "(time_kind = 'all_day' AND starts_at IS NULL AND ends_at IS NULL "
            "AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND start_date < end_date)",
            name="ck_meetings_time_shape",
        ),
        sa.CheckConstraint(
            "attendee_emails IS NULL OR (jsonb_typeof(attendee_emails) = 'array' "
            "AND NOT jsonb_path_exists(attendee_emails, "
            "'$[*] ? (@.type() != \"string\")'))",
            name="ck_meetings_attendee_array",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["provider_accounts.id"],
            name="fk_meetings_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_meetings_company_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meetings"),
        sa.UniqueConstraint(
            "account_id",
            "external_calendar_id",
            "external_event_id",
            name="uq_meetings_account_calendar_event",
        ),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("mail_message_id", sa.Uuid(), nullable=True),
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'mail' AND mail_message_id IS NOT NULL AND meeting_id IS NULL "
            "AND source_url IS NULL) OR "
            "(kind = 'meeting' AND mail_message_id IS NULL AND meeting_id IS NOT NULL "
            "AND source_url IS NULL) OR "
            "(kind = 'web' AND mail_message_id IS NULL AND meeting_id IS NULL "
            "AND source_url IS NOT NULL)",
            name="ck_evidence_source_matches_kind",
        ),
        sa.CheckConstraint(
            "length(regexp_replace(source_text, '[[:space:]]', '', 'g')) > 0",
            name="ck_evidence_source_text_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["mail_message_id"],
            ["mail_messages.id"],
            name="fk_evidence_mail_message_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name="fk_evidence_meeting_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
    )
    op.create_table(
        "briefing_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("briefing_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "sealed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number > 0", name="ck_briefing_versions_positive_number"
        ),
        sa.CheckConstraint(
            "length(regexp_replace(markdown, '[[:space:]]', '', 'g')) > 0",
            name="ck_briefing_versions_markdown_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id"],
            ["briefings.id"],
            name="fk_briefing_versions_briefing_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_briefing_versions"),
        sa.UniqueConstraint(
            "briefing_id", "id", name="uq_briefing_versions_briefing_id_id"
        ),
        sa.UniqueConstraint(
            "briefing_id", "version_number", name="uq_briefing_versions_number"
        ),
    )
    op.create_table(
        "briefing_version_evidence",
        sa.Column("briefing_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["briefing_version_id"],
            ["briefing_versions.id"],
            name="fk_briefing_version_evidence_version_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_briefing_version_evidence_evidence_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "briefing_version_id", "evidence_id", name="pk_briefing_version_evidence"
        ),
    )

    op.execute(
        """
        CREATE FUNCTION reject_immutable_evidence() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'evidence snapshots are immutable';
        END;
        $$;
        CREATE TRIGGER evidence_reject_update_delete
        BEFORE UPDATE OR DELETE ON evidence
        FOR EACH ROW EXECUTE FUNCTION reject_immutable_evidence();
        CREATE TRIGGER evidence_reject_truncate
        BEFORE TRUNCATE ON evidence
        FOR EACH STATEMENT EXECUTE FUNCTION reject_immutable_evidence();
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_briefing_version_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.sealed OR NEW.sealed IS DISTINCT FROM TRUE
               OR (to_jsonb(NEW) - 'sealed') IS DISTINCT FROM
                  (to_jsonb(OLD) - 'sealed') THEN
                RAISE EXCEPTION 'briefing versions may only be sealed once';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE FUNCTION reject_briefing_version_delete() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'briefing versions are immutable';
        END;
        $$;
        CREATE FUNCTION require_final_briefing_version_sealed() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE final_sealed boolean;
        BEGIN
            SELECT sealed INTO final_sealed FROM briefing_versions WHERE id = NEW.id;
            IF NOT FOUND OR final_sealed IS DISTINCT FROM TRUE THEN
                RAISE EXCEPTION 'briefing version must be sealed before commit';
            END IF;
            RETURN NULL;
        END;
        $$;
        CREATE TRIGGER briefing_versions_guard_update
        BEFORE UPDATE ON briefing_versions
        FOR EACH ROW EXECUTE FUNCTION guard_briefing_version_update();
        CREATE TRIGGER briefing_versions_reject_delete
        BEFORE DELETE ON briefing_versions
        FOR EACH ROW EXECUTE FUNCTION reject_briefing_version_delete();
        CREATE TRIGGER briefing_versions_reject_truncate
        BEFORE TRUNCATE ON briefing_versions
        FOR EACH STATEMENT EXECUTE FUNCTION reject_briefing_version_delete();
        CREATE CONSTRAINT TRIGGER briefing_versions_require_seal
        AFTER INSERT OR UPDATE ON briefing_versions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION require_final_briefing_version_sealed();
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_briefing_version_evidence_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE parent_id uuid;
        DECLARE parent_sealed boolean;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                FOR parent_id IN
                    SELECT DISTINCT id
                    FROM unnest(ARRAY[NEW.briefing_version_id]) AS parent(id)
                    ORDER BY id
                LOOP
                    SELECT sealed INTO parent_sealed
                    FROM briefing_versions WHERE id = parent_id FOR UPDATE;
                    IF NOT FOUND OR parent_sealed THEN
                        RAISE EXCEPTION 'citation membership is sealed';
                    END IF;
                END LOOP;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                FOR parent_id IN
                    SELECT DISTINCT id
                    FROM unnest(ARRAY[OLD.briefing_version_id]) AS parent(id)
                    ORDER BY id
                LOOP
                    SELECT sealed INTO parent_sealed
                    FROM briefing_versions WHERE id = parent_id FOR UPDATE;
                    IF NOT FOUND OR parent_sealed THEN
                        RAISE EXCEPTION 'citation membership is sealed';
                    END IF;
                END LOOP;
                RETURN OLD;
            ELSE
                FOR parent_id IN
                    SELECT DISTINCT id
                    FROM unnest(ARRAY[OLD.briefing_version_id, NEW.briefing_version_id])
                    AS parent(id)
                    ORDER BY id
                LOOP
                    SELECT sealed INTO parent_sealed
                    FROM briefing_versions WHERE id = parent_id FOR UPDATE;
                    IF NOT FOUND OR parent_sealed THEN
                        RAISE EXCEPTION 'citation membership is sealed';
                    END IF;
                END LOOP;
                RETURN NEW;
            END IF;
        END;
        $$;
        CREATE FUNCTION reject_briefing_version_evidence_truncate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'briefing citations are immutable after construction';
        END;
        $$;
        CREATE TRIGGER briefing_version_evidence_guard
        BEFORE INSERT OR UPDATE OR DELETE ON briefing_version_evidence
        FOR EACH ROW EXECUTE FUNCTION guard_briefing_version_evidence_change();
        CREATE TRIGGER briefing_version_evidence_reject_truncate
        BEFORE TRUNCATE ON briefing_version_evidence
        FOR EACH STATEMENT EXECUTE FUNCTION reject_briefing_version_evidence_truncate();
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION guard_briefing_version_evidence_change() CASCADE")
    op.execute("DROP FUNCTION reject_briefing_version_evidence_truncate() CASCADE")
    op.execute("DROP FUNCTION require_final_briefing_version_sealed() CASCADE")
    op.execute("DROP FUNCTION reject_briefing_version_delete() CASCADE")
    op.execute("DROP FUNCTION guard_briefing_version_update() CASCADE")
    op.execute("DROP FUNCTION reject_immutable_evidence() CASCADE")
    op.drop_table("briefing_version_evidence")
    op.drop_table("briefing_versions")
    op.drop_table("evidence")
    op.drop_table("meetings")
    op.drop_table("mail_messages")
    op.drop_index("uq_contacts_email_domain_lower", table_name="contacts")
    op.drop_table("contacts")
    op.drop_table("briefings")
    op.drop_table("companies")
    op.drop_table("provider_accounts")
