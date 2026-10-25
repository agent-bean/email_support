"""Add immutable approval bindings, approved knowledge and metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "da3c8e14f627"
down_revision: str | None = "a31f5e702c84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("briefing_id", sa.Uuid(), nullable=False),
        sa.Column("briefing_version_id", sa.Uuid(), nullable=False),
        sa.Column("action_kind", sa.String(length=24), nullable=False),
        sa.Column("recipient_emails", postgresql.JSONB(), nullable=False),
        sa.Column("selected_knowledge", postgresql.JSONB(), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action_kind IN ('send_email', 'save_knowledge')",
            name="ck_approvals_action_kind",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(recipient_emails) = 'array'",
            name="ck_approvals_recipient_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(selected_knowledge) = 'array'",
            name="ck_approvals_knowledge_array",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id", "briefing_version_id"],
            ["briefing_versions.briefing_id", "briefing_versions.id"],
            name="fk_approvals_briefing_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approvals"),
        sa.UniqueConstraint(
            "id", "briefing_version_id", name="uq_approvals_id_version"
        ),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            name="fk_actions_approval_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_actions"),
        sa.UniqueConstraint("approval_id", name="uq_actions_approval_id"),
    )
    op.create_table(
        "knowledge",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("selection_index", sa.Integer(), nullable=False),
        sa.Column("briefing_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sealed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "selection_index >= 0", name="ck_knowledge_selection_index_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id", "briefing_version_id"],
            ["approvals.id", "approvals.briefing_version_id"],
            name="fk_knowledge_approval_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_knowledge_company_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge"),
        sa.UniqueConstraint(
            "approval_id", "selection_index", name="uq_knowledge_approval_selection"
        ),
        sa.UniqueConstraint(
            "id", "briefing_version_id", name="uq_knowledge_id_source_version"
        ),
    )
    op.create_table(
        "knowledge_evidence",
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_knowledge_evidence_evidence_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge.id"],
            name="fk_knowledge_evidence_knowledge_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "knowledge_id", "evidence_id", name="pk_knowledge_evidence"
        ),
    )
    op.create_table(
        "preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(key)) > 0", name="ck_preferences_key_nonblank"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_preferences"),
        sa.UniqueConstraint("key", name="uq_preferences_key"),
    )
    op.create_table(
        "projection_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("projection_kind", sa.String(length=16), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("projected_version_id", sa.Uuid(), nullable=True),
        sa.Column("embedding_version", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "projection_kind IN ('neo4j', 'qdrant')",
            name="ck_projection_metadata_kind",
        ),
        sa.CheckConstraint(
            "projected_version_id IS NULL OR projected_version_id = source_version_id",
            name="ck_projection_metadata_exact_version",
        ),
        sa.CheckConstraint(
            "(projection_kind = 'neo4j' AND embedding_version IS NULL) OR "
            "(projection_kind = 'qdrant' AND "
            "((projected_version_id IS NULL AND embedding_version IS NULL) OR "
            "(projected_version_id IS NOT NULL AND embedding_version IS NOT NULL "
            "AND length(btrim(embedding_version)) > 0)))",
            name="ck_projection_metadata_embedding_state",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id", "source_version_id"],
            ["knowledge.id", "knowledge.briefing_version_id"],
            name="fk_projection_metadata_knowledge_source",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projection_metadata"),
        sa.UniqueConstraint(
            "projection_kind",
            "knowledge_id",
            name="uq_projection_metadata_kind_knowledge",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION validate_approval_payload() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            recipient text;
            source_is_sealed boolean;
            recipient_count integer;
            distinct_recipient_count integer;
            canonical_recipients jsonb;
        BEGIN
            IF jsonb_typeof(NEW.recipient_emails) IS DISTINCT FROM 'array'
               OR jsonb_typeof(NEW.selected_knowledge) IS DISTINCT FROM 'array' THEN
                RAISE EXCEPTION 'approval arrays must be JSON arrays'
                    USING ERRCODE = 'P0001';
            END IF;

            IF EXISTS (
                SELECT 1
                  FROM jsonb_array_elements(NEW.selected_knowledge) AS item(value)
                WHERE jsonb_typeof(item.value) IS DISTINCT FROM 'string'
                   OR length(btrim(item.value #>> '{}')) = 0
            ) THEN
                RAISE EXCEPTION 'selected knowledge entries must be nonblank strings'
                    USING ERRCODE = 'P0001';
            END IF;

            recipient_count := jsonb_array_length(NEW.recipient_emails);
            SELECT count(DISTINCT item.value),
                   jsonb_agg(to_jsonb(item.value) ORDER BY item.value COLLATE "C")
              INTO distinct_recipient_count, canonical_recipients
              FROM jsonb_array_elements_text(NEW.recipient_emails) AS item(value);
            canonical_recipients := COALESCE(canonical_recipients, '[]'::jsonb);
            IF recipient_count <> distinct_recipient_count
               OR NEW.recipient_emails <> canonical_recipients THEN
                RAISE EXCEPTION 'recipients must be unique and canonically sorted'
                    USING ERRCODE = 'P0001';
            END IF;

            FOR recipient IN
                SELECT value
                  FROM jsonb_array_elements_text(NEW.recipient_emails)
            LOOP
                IF length(btrim(recipient)) = 0
                   OR recipient <> btrim(recipient)
                   OR recipient ~ '[[:space:]]'
                   OR length(recipient) - length(replace(recipient, '@', '')) <> 1
                   OR length(split_part(recipient, '@', 1)) = 0
                   OR length(split_part(recipient, '@', 2)) = 0
                   OR split_part(recipient, '@', 2)
                      <> lower(split_part(recipient, '@', 2)) THEN
                    RAISE EXCEPTION 'recipient address is not canonical'
                        USING ERRCODE = 'P0001';
                END IF;
            END LOOP;

            IF NEW.action_kind = 'send_email' THEN
                IF recipient_count = 0
                   OR jsonb_array_length(NEW.selected_knowledge) <> 0 THEN
                    RAISE EXCEPTION 'send approval requires recipients only'
                        USING ERRCODE = 'P0001';
                END IF;
            ELSIF NEW.action_kind = 'save_knowledge' THEN
                IF recipient_count <> 0
                   OR jsonb_array_length(NEW.selected_knowledge) = 0 THEN
                    RAISE EXCEPTION 'knowledge approval requires selected text only'
                        USING ERRCODE = 'P0001';
                END IF;
            ELSE
                RAISE EXCEPTION 'unknown approval action kind' USING ERRCODE = 'P0001';
            END IF;

            SELECT sealed INTO source_is_sealed
              FROM briefing_versions
             WHERE id = NEW.briefing_version_id
               AND briefing_id = NEW.briefing_id;
            IF source_is_sealed IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'approval must bind a sealed briefing version'
                    USING ERRCODE = 'P0001';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_approval_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'approval history is immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_action_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'action bindings are immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_history_truncate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'canonical history cannot be truncated'
                USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_knowledge_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            approved_action text;
            approved_selection jsonb;
            approved_company uuid;
            source_is_sealed boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'knowledge history is immutable'
                    USING ERRCODE = 'P0001';
            END IF;

            IF TG_OP = 'INSERT' THEN
                IF NEW.sealed OR NEW.invalidated_at IS NOT NULL THEN
                    RAISE EXCEPTION 'knowledge must be constructed before sealing'
                        USING ERRCODE = 'P0001';
                END IF;
                SELECT a.action_kind, a.selected_knowledge, b.company_id
                  INTO approved_action, approved_selection, approved_company
                  FROM approvals AS a
                  JOIN briefings AS b ON b.id = a.briefing_id
                 WHERE a.id = NEW.approval_id
                   AND a.briefing_version_id = NEW.briefing_version_id;
                IF approved_action IS DISTINCT FROM 'save_knowledge'
                   OR NEW.selection_index >= jsonb_array_length(approved_selection) THEN
                    RAISE EXCEPTION
                        'knowledge selection is not in its approval snapshot'
                        USING ERRCODE = 'P0001';
                END IF;
                IF NEW.company_id IS DISTINCT FROM approved_company THEN
                    RAISE EXCEPTION 'knowledge company must match its approved briefing'
                        USING ERRCODE = 'P0001';
                END IF;
                SELECT sealed INTO source_is_sealed
                  FROM briefing_versions
                 WHERE id = NEW.briefing_version_id;
                IF source_is_sealed IS DISTINCT FROM true THEN
                    RAISE EXCEPTION 'knowledge source version must be sealed'
                        USING ERRCODE = 'P0001';
                END IF;
                RETURN NEW;
            END IF;

            IF NOT OLD.sealed AND NEW.sealed
               AND NEW.id = OLD.id
               AND NEW.company_id IS NOT DISTINCT FROM OLD.company_id
               AND NEW.approval_id = OLD.approval_id
               AND NEW.selection_index = OLD.selection_index
               AND NEW.briefing_version_id = OLD.briefing_version_id
               AND NEW.created_at = OLD.created_at
               AND NEW.invalidated_at IS NULL THEN
                RETURN NEW;
            END IF;

            IF OLD.sealed AND NEW.sealed
               AND OLD.invalidated_at IS NULL
               AND NEW.invalidated_at IS NOT NULL
               AND NEW.id = OLD.id
               AND NEW.company_id IS NOT DISTINCT FROM OLD.company_id
               AND NEW.approval_id = OLD.approval_id
               AND NEW.selection_index = OLD.selection_index
               AND NEW.briefing_version_id = OLD.briefing_version_id
               AND NEW.created_at = OLD.created_at THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'knowledge provenance is immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_knowledge_evidence_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            parent_id uuid;
            parent_sealed boolean;
            source_version uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                parent_id := NEW.knowledge_id;
            ELSIF TG_OP = 'UPDATE' THEN
                FOR parent_id IN
                    SELECT DISTINCT candidate
                      FROM unnest(ARRAY[OLD.knowledge_id, NEW.knowledge_id])
                           AS ids(candidate)
                     ORDER BY candidate
                LOOP
                    SELECT sealed, briefing_version_id
                      INTO parent_sealed, source_version
                      FROM knowledge WHERE id = parent_id FOR UPDATE;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'knowledge citation parent does not exist'
                            USING ERRCODE = 'P0001';
                    END IF;
                END LOOP;
                RAISE EXCEPTION 'knowledge citations are immutable'
                    USING ERRCODE = 'P0001';
            ELSE
                parent_id := OLD.knowledge_id;
            END IF;

            SELECT sealed, briefing_version_id
              INTO parent_sealed, source_version
              FROM knowledge WHERE id = parent_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'knowledge citation parent does not exist'
                    USING ERRCODE = 'P0001';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF parent_sealed THEN
                    RAISE EXCEPTION 'cannot cite sealed knowledge'
                        USING ERRCODE = 'P0001';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM briefing_version_evidence
                     WHERE briefing_version_id = source_version
                       AND evidence_id = NEW.evidence_id
                ) THEN
                    RAISE EXCEPTION
                        'knowledge evidence must belong to its approved source version'
                        USING ERRCODE = 'P0001';
                END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'knowledge citations are immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION require_knowledge_sealed() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            final_sealed boolean;
        BEGIN
            SELECT sealed INTO final_sealed FROM knowledge WHERE id = NEW.id;
            IF final_sealed IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'knowledge must be sealed before commit'
                    USING ERRCODE = 'P0001';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        "CREATE TRIGGER trg_approvals_validate BEFORE INSERT ON approvals "
        "FOR EACH ROW EXECUTE FUNCTION validate_approval_payload()"
    )
    op.execute(
        "CREATE TRIGGER trg_approvals_immutable BEFORE UPDATE OR DELETE ON approvals "
        "FOR EACH ROW EXECUTE FUNCTION reject_approval_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_approvals_no_truncate BEFORE TRUNCATE ON approvals "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_history_truncate()"
    )
    op.execute(
        "CREATE TRIGGER trg_actions_immutable BEFORE UPDATE OR DELETE ON actions "
        "FOR EACH ROW EXECUTE FUNCTION reject_action_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_actions_no_truncate BEFORE TRUNCATE ON actions "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_history_truncate()"
    )
    op.execute(
        "CREATE TRIGGER trg_knowledge_change "
        "BEFORE INSERT OR UPDATE OR DELETE ON knowledge "
        "FOR EACH ROW EXECUTE FUNCTION validate_knowledge_change()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_knowledge_sealed "
        "AFTER INSERT OR UPDATE ON knowledge DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION require_knowledge_sealed()"
    )
    op.execute(
        "CREATE TRIGGER trg_knowledge_evidence_change "
        "BEFORE INSERT OR UPDATE OR DELETE ON knowledge_evidence "
        "FOR EACH ROW EXECUTE FUNCTION validate_knowledge_evidence_change()"
    )
    op.execute(
        "CREATE TRIGGER trg_knowledge_evidence_no_truncate "
        "BEFORE TRUNCATE ON knowledge_evidence "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_history_truncate()"
    )
    op.execute(
        "CREATE TRIGGER trg_knowledge_no_truncate BEFORE TRUNCATE ON knowledge "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_history_truncate()"
    )


def downgrade() -> None:
    op.drop_table("projection_metadata")
    op.drop_table("preferences")
    op.drop_table("knowledge_evidence")
    op.drop_table("knowledge")
    op.drop_table("actions")
    op.drop_table("approvals")
    for function in (
        "require_knowledge_sealed",
        "validate_knowledge_evidence_change",
        "validate_knowledge_change",
        "reject_history_truncate",
        "reject_action_mutation",
        "reject_approval_mutation",
        "validate_approval_payload",
    ):
        op.execute(f"DROP FUNCTION {function}()")
