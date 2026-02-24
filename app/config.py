"""
Flask configuration classes for the Reverse Document Generator service.

This module defines environment-specific configuration classes that load and organize
the 20+ environment variables across 6 categories (LLM keys, platform services,
graph database, observability, Pub/Sub, storage) into structured Flask configuration
objects. Replaces the direct os.environ.get() calls from the original Cloud Run Job
main.py entry point with Flask configuration best practices.

Configuration is loaded via the Application Factory pattern — create_app() uses
config_by_name to select the appropriate class based on the FLASK_CONFIG env var.

Usage:
    from app.config import config_by_name
    app.config.from_object(config_by_name['development'])
"""

import os

from dotenv import load_dotenv

# Load environment variables from .env file at module import time.
# This ensures all os.environ.get() calls in the configuration classes
# have access to .env values during class definition. In production,
# environment variables are injected by the container runtime (Cloud Run)
# and this call is a safe no-op when no .env file exists.
load_dotenv()


class BaseConfig:
    """Base configuration shared across all environments.

    Organizes 20+ environment variables from the original Cloud Run Job
    architecture into 6 logical categories plus Flask core settings and
    application-level settings. All secrets default to empty strings to
    prevent accidental exposure of example or placeholder values.

    Categories:
        1. LLM API Keys — Anthropic, OpenAI, Voyage AI
        2. Platform Services — Admin, Secret Manager, Markdown
        3. Graph Database — Neo4j connection parameters
        4. Observability — LangChain/LangSmith tracing
        5. Pub/Sub — Google Cloud Pub/Sub messaging
        6. Storage — Google Cloud Storage
    """

    # -------------------------------------------------------------------------
    # Flask Core Settings
    # -------------------------------------------------------------------------
    SECRET_KEY: str = os.environ.get(
        "FLASK_SECRET_KEY", "dev-secret-key-change-in-production"
    )
    JSON_SORT_KEYS: bool = False

    # -------------------------------------------------------------------------
    # Category 1: LLM API Keys
    # -------------------------------------------------------------------------
    # Anthropic Claude Opus 4.6 — primary LLM for document generation
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    # OpenAI GPT-5 Mini — secondary LLM for structured output
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    # Voyage AI — embedding model for semantic search
    VOYAGE_API_KEY: str = os.environ.get("VOYAGE_API_KEY", "")

    # -------------------------------------------------------------------------
    # Category 2: Platform Services
    # -------------------------------------------------------------------------
    # archie-service-admin — repository metadata and storage operations
    ADMIN_SERVICE_URL: str = os.environ.get("ADMIN_SERVICE_URL", "")
    # archie-secret-manager — centralized secret retrieval
    SECRET_MANAGER_URL: str = os.environ.get("SECRET_MANAGER_URL", "")
    # archie-service-markdown — Mermaid diagram validation endpoint
    MARKDOWN_SERVICE_URL: str = os.environ.get("MARKDOWN_SERVICE_URL", "")

    # -------------------------------------------------------------------------
    # Category 3: Graph Database (Neo4j)
    # -------------------------------------------------------------------------
    # Neo4j Bolt connection URI for code graph queries
    NEO4J_URI: str = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
    # Neo4j authentication credentials
    NEO4J_USERNAME: str = os.environ.get("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = os.environ.get("NEO4J_PASSWORD", "")
    # Neo4j target database name
    NEO4J_DATABASE: str = os.environ.get("NEO4J_DATABASE", "neo4j")

    # -------------------------------------------------------------------------
    # Category 4: Observability (LangChain / LangSmith)
    # -------------------------------------------------------------------------
    # Enable LangChain tracing v2 for LLM execution monitoring
    LANGCHAIN_TRACING_V2: str = os.environ.get("LANGCHAIN_TRACING_V2", "true")
    # LangSmith API key for trace submission
    LANGCHAIN_API_KEY: str = os.environ.get("LANGCHAIN_API_KEY", "")
    # LangSmith project name for trace organization
    LANGSMITH_PROJECT: str = os.environ.get("LANGSMITH_PROJECT", "")

    # -------------------------------------------------------------------------
    # Category 5: Pub/Sub (Google Cloud Pub/Sub)
    # -------------------------------------------------------------------------
    # GCP project ID for Pub/Sub operations
    PUBSUB_PROJECT_ID: str = os.environ.get("PUBSUB_PROJECT_ID", "")
    # Pub/Sub topic for document generation status notifications
    PUBSUB_TOPIC: str = os.environ.get("PUBSUB_TOPIC", "")

    # -------------------------------------------------------------------------
    # Category 6: Storage (Google Cloud Storage)
    # -------------------------------------------------------------------------
    # GCS bucket for document persistence (progressive section uploads)
    GCS_BUCKET_NAME: str = os.environ.get("GCS_BUCKET_NAME", "")
    # GCP project ID for GCS operations
    GCS_PROJECT_ID: str = os.environ.get("GCS_PROJECT_ID", "")

    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    # Logging verbosity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    # Current deployment environment identifier
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    # Service name for structured logging and tracing identification
    SERVICE_NAME: str = os.environ.get("SERVICE_NAME", "reverse-document-generator")


class DevelopmentConfig(BaseConfig):
    """Development environment configuration.

    Enables Flask debug mode for auto-reload and interactive debugger.
    Uses default values from BaseConfig which are suitable for local
    development with a .env file providing actual service credentials.
    """

    DEBUG: bool = True
    TESTING: bool = False
    ENV: str = "development"


class StagingConfig(BaseConfig):
    """Staging environment configuration.

    Mirrors production settings with debug mode disabled. Used for
    pre-production validation with real service integrations against
    staging instances of Anthropic, Neo4j, GCS, and Pub/Sub.
    """

    DEBUG: bool = False
    TESTING: bool = False
    ENV: str = "staging"


class ProductionConfig(BaseConfig):
    """Production environment configuration.

    Enforces strict security requirements: SECRET_KEY must be set via
    environment variable (no fallback default), debug mode is disabled,
    and all API keys are expected to be injected by the Cloud Run
    container runtime or secret manager.

    Credential Security (AAP Section 0.7.2):
        - API keys and database credentials must NEVER be exposed in
          error traces, logs, or API responses.
        - The SECRET_KEY override below ensures no default dev key is
          used in production, which would compromise session security.
    """

    DEBUG: bool = False
    TESTING: bool = False
    ENV: str = "production"

    # Override SECRET_KEY to require an actual environment variable in
    # production. An empty string fallback ensures the app can start
    # (for health checks) but will not have a functional session secret
    # until properly configured — this is intentional to prevent the
    # dev default from being used in production.
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "")


class TestingConfig(BaseConfig):
    """Testing environment configuration.

    Enables both DEBUG and TESTING flags for pytest-flask integration.
    Overrides sensitive configuration values with safe test defaults
    to prevent accidental interaction with real external services during
    automated test execution.
    """

    DEBUG: bool = True
    TESTING: bool = True
    ENV: str = "testing"

    # Override service URLs with safe test values to prevent tests from
    # accidentally hitting real services
    ADMIN_SERVICE_URL: str = "http://localhost:9999/mock-admin"
    SECRET_MANAGER_URL: str = "http://localhost:9999/mock-secrets"
    MARKDOWN_SERVICE_URL: str = "http://localhost:9999/mock-markdown"

    # Override Neo4j with localhost defaults for test isolation
    NEO4J_URI: str = "neo4j://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "test-password"
    NEO4J_DATABASE: str = "testdb"

    # Disable LangChain tracing during tests to avoid external calls
    LANGCHAIN_TRACING_V2: str = "false"

    # Use test-specific Pub/Sub and GCS values
    PUBSUB_PROJECT_ID: str = "test-project"
    PUBSUB_TOPIC: str = "test-topic"
    GCS_BUCKET_NAME: str = "test-bucket"
    GCS_PROJECT_ID: str = "test-project"


# ---------------------------------------------------------------------------
# Configuration Name Mapping
# ---------------------------------------------------------------------------
# Maps environment name strings to their corresponding configuration classes.
# Used by create_app() to select the appropriate configuration:
#   app.config.from_object(config_by_name[config_name])
config_by_name: dict = {
    "development": DevelopmentConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
