"""Pydantic document section models for structured LLM output validation.

These models are used by the LangGraph agent workflow for structured output
from LLM calls in both GENERATE and UPDATE modes. They must remain unchanged
to preserve compatibility with the agent output parsing pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentSectionStatus(str, Enum):
    """Status indicating whether a document section has changed during an update."""

    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"


class DocumentSection(BaseModel):
    """A single section of a generated Technical Specification document."""

    title: str = Field(description="The title of the document section")
    content: str = Field(description="The markdown content of the document section")
    status: DocumentSectionStatus = Field(
        default=DocumentSectionStatus.CHANGED,
        description=(
            "Whether this section has changed (CHANGED) or remains the same "
            "(UNCHANGED) compared to the previous version"
        ),
    )


class DocumentSections(BaseModel):
    """Container for multiple document sections with change status classification."""

    sections: List[DocumentSection] = Field(
        description="List of document sections with their change status"
    )
