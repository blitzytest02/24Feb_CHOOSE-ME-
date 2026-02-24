"""ReverseDocumentState TypedDict for LangGraph StateGraph workflow.

Defines the core workflow state container used by the LangGraph StateGraph
to manage document generation and update operations. Contains 37 fields
organized into 5 categories: Execution Context, Document State, Agent State,
Infrastructure, and Configuration.

This TypedDict is consumed by ``langgraph.graph.StateGraph(ReverseDocumentState)``
and all agent node methods receive and return partial state updates using it.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import add_messages


class ReverseDocumentState(TypedDict):
    """Core workflow state for the Reverse Document Generator LangGraph graph.

    All agent nodes (setup, gather_context, process_section, document_section,
    create_agent_action_plan, identify_changes, update_section,
    copy_old_tech_spec_section) read from and write partial updates to this
    state container during graph execution.
    """

    # ── Category 1: Execution Context ───────────────────────────────────
    project_id: str
    """Unique project identifier."""

    job_id: str
    """Unique job execution identifier."""

    tech_spec_id: str
    """Technical specification document identifier."""

    mode: str
    """Operation mode — ``'GENERATE'`` or ``'UPDATE'``."""

    repository_url: str
    """URL of the target repository to analyse."""

    repository_branch: str
    """Branch name to analyse."""

    repository_path: str
    """Local filesystem path where the repository is cloned."""

    head_commit_hash: str
    """HEAD commit hash of the analysed repository."""

    # ── Category 2: Document State ──────────────────────────────────────
    sections: list
    """Section definitions sourced from ``TECHNICAL_SECTION_PROMPTS``."""

    current_section_index: int
    """Zero-based index of the section currently being processed."""

    current_section: dict
    """The current section definition being worked on."""

    completed_sections: list
    """Accumulated list of completed section outputs (Markdown content)."""

    total_sections: int
    """Total number of sections to process."""

    document_output: str
    """Final assembled document output."""

    previous_tech_spec: str
    """Previous Technical Specification content (used in UPDATE mode)."""

    section_content: str
    """Current section's generated Markdown content."""

    section_title: str
    """Current section's title."""

    # ── Category 3: Agent State ─────────────────────────────────────────
    messages: Annotated[list, add_messages]
    """LangGraph message history with ``add_messages`` reducer for automatic
    message accumulation across agent node invocations."""

    search_results: list
    """Results from the Context Searcher Agent's repository exploration."""

    intermediate_results: list
    """Intermediate processing results passed between agent steps."""

    agent_action_plan: str
    """Generated Agent Action Plan (AAP) for UPDATE mode."""

    identified_changes: list
    """Changes identified during UPDATE mode (list of DocumentSections)."""

    current_section_status: str
    """Status of the current section — ``'CHANGED'`` or ``'UNCHANGED'``."""

    # ── Category 4: Infrastructure ──────────────────────────────────────
    gcs_client: Any
    """Google Cloud Storage client instance."""

    pubsub_publisher: Any
    """Google Cloud Pub/Sub publisher client instance."""

    neo4j_builder: Any
    """Neo4j ``CodeGraphBuilder`` instance for code-graph queries."""

    admin_service_client: Any
    """Admin-service HTTP client (``ServiceClient``)."""

    notification_data: dict
    """Notification configuration for Pub/Sub events."""

    gcs_bucket_name: str
    """GCS bucket name used for document storage."""

    # ── Category 5: Configuration ───────────────────────────────────────
    llm_primary: Any
    """Primary LLM client (Anthropic Claude Opus 4.6)."""

    llm_secondary: Any
    """Secondary LLM client (OpenAI GPT-5 Mini)."""

    embeddings_client: Any
    """Embedding client (Voyage AI)."""

    search_tools: list
    """Eight search tools for the Context Searcher Agent (``rd_search_tools``)."""

    author_tools: list
    """Five author tools for the Author Agent (``rd_author_tools``)."""

    attachment_base64_cache: dict
    """Cache mapping attachment identifiers to their base64-encoded data."""

    figma_url: str
    """Optional Figma design file URL."""

    config: dict
    """Additional configuration overrides."""
