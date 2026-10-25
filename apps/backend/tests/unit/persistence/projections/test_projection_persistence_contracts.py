from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_support.models.persistence import (
    ProjectionKind,
    ProjectionMetadataCreate,
)


def test_projection_contract_rejects_unknown_projection_kind_and_fields() -> None:
    values = {
        "knowledge_id": uuid4(),
        "source_version_id": uuid4(),
        "projected_version_id": None,
        "embedding_version": None,
    }
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {**values, "projection_kind": "neo_graph"}
        )
    valid = ProjectionMetadataCreate.model_validate(
        {**values, "projection_kind": ProjectionKind.NEO4J}
    )
    assert valid.embedding_version is None
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {**values, "projection_kind": ProjectionKind.NEO4J, "job_id": uuid4()}
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.NEO4J,
                "embedding_version": "embedding-v1",
            }
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.QDRANT,
                "projected_version_id": uuid4(),
                "embedding_version": "embedding-v1",
            }
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.QDRANT,
                "embedding_version": "embedding-v1",
            }
        )
