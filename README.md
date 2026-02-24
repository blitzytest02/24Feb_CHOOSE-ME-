# Reverse Document Generator — Flask API Server

An AI-powered Technical Specification generator service built on **Flask 3.1.3**, **LangGraph 1.0.9**, and **Python 3.12**. This application orchestrates a multi-agent workflow using three specialized AI agents — **Context Searcher**, **Author**, and **Architect** — to produce comprehensive Technical Specification documents from source code repositories.

## Table of Contents

- [Overview](#overview)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Installation and Setup](#installation-and-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Deployment](#deployment)
- [External Service Integrations](#external-service-integrations)
- [License](#license)

---

## Overview

The Reverse Document Generator is a backend API service that analyzes source code repositories and produces detailed Technical Specification documents using large language models. It operates in two modes:

- **GENERATE** — Full document creation from scratch by analyzing the entire repository structure, code patterns, integrations, and architecture.
- **UPDATE** — Incremental document updates that identify changes since the last specification and selectively update only the affected sections.

The system preserves all 13 features (F-001 through F-013) from the original architecture, including:

| Feature ID | Feature Name |
|-----------|-------------|
| F-001 | Full Technical Specification Generation |
| F-002 | Incremental Document Updates |
| F-003 | Agent Action Plan Generation |
| F-004 | Change Identification (UPDATE mode) |
| F-005 | Multi-Tool Repository Exploration |
| F-006 | Cross-Section Context Referencing |
| F-007 | Attachment Processing (images, diagrams) |
| F-008 | Mermaid Diagram Validation |
| F-009 | Progressive Section Upload |
| F-010 | Status Notifications via Pub/Sub |
| F-011 | Error Recovery with Exponential Retry |
| F-012 | Figma Design Integration (optional) |
| F-013 | Stateless Event-Driven Execution |

---

## Architecture Overview

The application follows the **Flask Application Factory** pattern with **Blueprint-based routing**, a dedicated **service layer** for business logic, and **background task execution** for long-running document generation workflows.

### Key Architectural Patterns

- **Application Factory** — `create_app()` in `app/__init__.py` accepts a configuration class, initializes Flask extensions, registers Blueprints, and returns a configured Flask application instance. This enables multiple configurations for testing, staging, and production.
- **Blueprint Routing** — Routes are organized into domain-specific Blueprints:
  - `document_bp` — Document generation and update API endpoints
  - `health_bp` — Health check and readiness probe endpoints
  - `notifications_bp` — Notification status query endpoints
- **Service Layer** — Business logic is encapsulated in service classes that are independent of the Flask request context:
  - `DocumentService` — Document generation orchestration and background task management
  - `ReverseDocumentHelper` — Core LangGraph `StateGraph` workflow with agent node definitions
  - `NotificationService` — Pub/Sub notification lifecycle management
  - `StorageService` — Google Cloud Storage document persistence
  - `AttachmentService` — Attachment download, base64 encoding, and caching
  - `LLMService` — LLM client initialization and management (Anthropic, OpenAI, Voyage AI)
- **Background Task Execution** — Document generation takes up to 24 hours and runs in background threads. API endpoints return immediately with a job identifier that clients use to poll for status updates.
- **Dependency Injection** — Service instances are passed through Flask's application context (`current_app.config` / `current_app.extensions`) rather than global singletons, enabling test isolation.

### Project Directory Structure

```
/
├── app/
│   ├── __init__.py              # Flask application factory — create_app()
│   ├── config.py                # Configuration classes (Dev, Stage, Prod, Testing)
│   ├── extensions.py            # Flask extension initialization and service registry
│   ├── routes/
│   │   ├── __init__.py          # Blueprint registration utilities
│   │   ├── document.py          # Document generation/update API endpoints
│   │   ├── health.py            # Health check and readiness probe endpoints
│   │   └── notifications.py     # Notification status query endpoints
│   ├── services/
│   │   ├── __init__.py          # Service layer exports
│   │   ├── document_service.py  # Document generation orchestration
│   │   ├── reverse_document_helper.py  # LangGraph StateGraph and agent nodes
│   │   ├── notification_service.py     # Pub/Sub notification management
│   │   ├── storage_service.py          # GCS document persistence
│   │   ├── attachment_service.py       # Attachment download and caching
│   │   └── llm_service.py             # LLM client initialization and management
│   ├── models/
│   │   ├── __init__.py          # Model module exports
│   │   ├── state.py             # ReverseDocumentState TypedDict (30+ fields)
│   │   ├── document_models.py   # Pydantic models (DocumentSection, etc.)
│   │   └── request_models.py    # API request/response Pydantic schemas
│   ├── prompts/
│   │   ├── __init__.py          # Prompt template exports
│   │   ├── search_prompts.py    # Context Searcher Agent prompts
│   │   ├── author_prompts.py    # Author Agent prompts and rules
│   │   ├── architect_prompts.py # Architect Agent prompts (UPDATE mode)
│   │   └── action_plan_prompts.py  # Agent Action Plan generation prompts
│   ├── utils/
│   │   ├── __init__.py          # Utility module exports
│   │   ├── retry.py             # Exponential retry decorator (tenacity)
│   │   ├── token_counter.py     # GPT-2 tokenizer-based token counting
│   │   └── validators.py        # Mermaid diagram validation client
│   └── tasks/
│       ├── __init__.py          # Background task module exports
│       └── generation_tasks.py  # Background document generation workers
├── tests/
│   ├── __init__.py              # Test package initialization
│   ├── conftest.py              # Pytest fixtures, Flask test client, mock services
│   ├── test_routes/             # API endpoint tests
│   ├── test_services/           # Service layer unit tests
│   └── test_models/             # Data model validation tests
├── requirements.txt             # Python dependencies with pinned versions
├── pyproject.toml               # Project metadata, tool settings (Black, isort, Ruff, pytest)
├── wsgi.py                      # WSGI entry point for Gunicorn
├── gunicorn.conf.py             # Gunicorn WSGI server configuration
├── Dockerfile                   # Flask/Gunicorn container build (Ubuntu 24.04)
├── docker-compose.yml           # Local development multi-service composition
├── Makefile                     # Build, test, and deploy automation
├── .env.example                 # Environment variable template (20+ variables)
├── .flaskenv                    # Flask CLI environment variables
├── .pre-commit-config.yaml      # Code quality hooks (Black, isort, Ruff)
├── .gitignore                   # Python/Flask gitignore patterns
└── .github/
    └── workflows/
        └── deploy.yml           # CI/CD pipeline for Cloud Run Service deployment
```

---

## Prerequisites

Before setting up the project, ensure the following tools and access are available:

- **Python 3.12+** — Primary runtime for the Flask application and LangGraph workflow
- **Node.js 20 LTS** — Required for MCP (Model Context Protocol) and optional Figma DevTools integration
- **Docker and Docker Compose** — For containerized local development and production builds
- **pip** — Python package manager (included with Python 3.12)
- **pre-commit** — Code quality hook runner (installed via pip)
- **Access to Google Artifact Registry** — Required for installing the private `blitzy-platform-shared` and `blitzy-utils` packages. Ensure `keyrings.google-artifactregistry-auth` is installed for authentication.

---

## Installation and Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd reverse-document-generator
```

### 2. Create and Activate a Python Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Open `.env` and fill in all required environment variables. See the [Configuration](#configuration) section for details on each variable.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** The `requirements.txt` includes a private registry URL for `blitzy-platform-shared` and `blitzy-utils`. Ensure your Google Artifact Registry credentials are configured before running the install command.

### 5. Set Up Pre-Commit Hooks

```bash
pre-commit install
```

This enables automatic code formatting (Black), import sorting (isort), and linting (Ruff) on every commit.

---

## Configuration

All application configuration is managed through environment variables, loaded via `python-dotenv` from a `.env` file. The variables are organized into six categories. Refer to `.env.example` for the complete template.

### Flask Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_APP` | Flask CLI entry point | `wsgi.py` |
| `FLASK_ENV` | Flask environment mode | `development` |
| `FLASK_SECRET_KEY` | Secret key for session management | *(required in production)* |
| `FLASK_CONFIG` | Configuration class selector | `development` |

### Category 1: LLM API Keys

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic Claude Opus 4.6 API key | *(required)* |
| `OPENAI_API_KEY` | OpenAI GPT-5 Mini API key | *(required)* |
| `VOYAGE_API_KEY` | Voyage AI embeddings API key | *(required)* |

### Category 2: Platform Services

| Variable | Description | Default |
|----------|-------------|---------|
| `ADMIN_SERVICE_URL` | `archie-service-admin` REST API URL | *(required)* |
| `SECRET_MANAGER_URL` | `archie-secret-manager` service URL | *(required)* |
| `MARKDOWN_SERVICE_URL` | `archie-service-markdown` URL for Mermaid validation | *(required)* |

### Category 3: Graph Database

| Variable | Description | Default |
|----------|-------------|---------|
| `NEO4J_URI` | Neo4j Bolt connection URI | `neo4j://localhost:7687` |
| `NEO4J_USERNAME` | Neo4j authentication username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j authentication password | *(required)* |
| `NEO4J_DATABASE` | Neo4j database name | `neo4j` |

### Category 4: Observability

| Variable | Description | Default |
|----------|-------------|---------|
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing | `true` |
| `LANGCHAIN_API_KEY` | LangSmith API key | *(required)* |
| `LANGSMITH_PROJECT` | LangSmith project name for trace grouping | *(required)* |

### Category 5: Pub/Sub

| Variable | Description | Default |
|----------|-------------|---------|
| `PUBSUB_PROJECT_ID` | Google Cloud project ID for Pub/Sub | *(required)* |
| `PUBSUB_TOPIC` | Pub/Sub topic name for notifications | *(required)* |

### Category 6: Storage

| Variable | Description | Default |
|----------|-------------|---------|
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket for document persistence | *(required)* |
| `GCS_PROJECT_ID` | GCS project ID | *(required)* |

### Additional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Application log level | `INFO` |
| `ENVIRONMENT` | Environment identifier (development, staging, production) | `development` |
| `SERVICE_NAME` | Service name for logging and monitoring | `reverse-document-generator` |

### Flask Configuration Classes

The application provides four environment-specific configuration classes in `app/config.py`:

| Class | Purpose |
|-------|---------|
| `DevelopmentConfig` | Local development — `DEBUG=True`, verbose logging |
| `StagingConfig` | Staging environment — `DEBUG=False`, production-like |
| `ProductionConfig` | Production — `DEBUG=False`, requires all secrets to be set |
| `TestingConfig` | Test execution — `TESTING=True`, mock service values |

Select the configuration by setting `FLASK_CONFIG` to one of: `development`, `staging`, `production`, or `testing`.

---

## Running the Application

### Development Mode

Using Flask's built-in development server with auto-reload:

```bash
flask run --host=0.0.0.0 --port=8080
```

Or using the Makefile shortcut:

```bash
make run
```

### Production Mode

Using Gunicorn as the WSGI server:

```bash
gunicorn --config gunicorn.conf.py wsgi:app
```

Or using the Makefile shortcut:

```bash
make run-gunicorn
```

### Docker

Build and run using Docker Compose:

```bash
docker-compose up
```

Or build and run the Docker image directly:

```bash
docker build -t reverse-document-generator .
docker run -p 8080:8080 --env-file .env reverse-document-generator
```

---

## API Reference

All API endpoints return JSON responses. Document generation and update operations run **asynchronously in background threads** — the API returns immediately with a job identifier that can be used to poll for status.

### `POST /api/v1/documents/generate`

Trigger full Technical Specification document generation.

**Request Body:**

```json
{
  "project_id": "proj-abc-123",
  "tech_spec_id": "ts-def-456",
  "job_id": "job-ghi-789",
  "repository_url": "https://github.com/org/repo",
  "repository_branch": "main",
  "mode": "GENERATE",
  "notification_data": {
    "project_id": "proj-abc-123",
    "job_id": "job-ghi-789",
    "tech_spec_id": "ts-def-456"
  },
  "sections": null,
  "config": {},
  "attachments": [],
  "figma_url": null
}
```

**Response (202 Accepted):**

```json
{
  "job_id": "job-ghi-789",
  "status": "PENDING",
  "message": "Document generation started",
  "tech_spec_id": "ts-def-456",
  "project_id": "proj-abc-123"
}
```

### `POST /api/v1/documents/update`

Trigger incremental document update based on repository changes.

**Request Body:**

```json
{
  "project_id": "proj-abc-123",
  "tech_spec_id": "ts-def-456",
  "job_id": "job-ghi-789",
  "repository_url": "https://github.com/org/repo",
  "repository_branch": "main",
  "mode": "UPDATE",
  "previous_tech_spec": "# Previous Technical Specification\n\n## 1.1 Executive Summary\n...",
  "notification_data": {
    "project_id": "proj-abc-123",
    "job_id": "job-ghi-789",
    "tech_spec_id": "ts-def-456"
  },
  "sections": null,
  "config": {},
  "attachments": [],
  "figma_url": null
}
```

**Response (202 Accepted):**

```json
{
  "job_id": "job-ghi-789",
  "status": "PENDING",
  "message": "Document update started",
  "tech_spec_id": "ts-def-456",
  "project_id": "proj-abc-123"
}
```

### `GET /api/v1/documents/<id>/status`

Query the current status of a document generation or update job.

**Response (200 OK):**

```json
{
  "job_id": "job-ghi-789",
  "status": "IN_PROGRESS",
  "current_section": 5,
  "total_sections": 13,
  "completed_sections": 4,
  "mode": "GENERATE"
}
```

### `GET /api/v1/notifications/<job_id>`

Query the notification status for a specific job.

**Response (200 OK):**

```json
{
  "job_id": "job-ghi-789",
  "notifications": [
    {
      "type": "IN_PROGRESS",
      "section_index": 4,
      "total_sections": 13,
      "timestamp": "2026-02-24T12:00:00Z"
    }
  ]
}
```

### `GET /health`

Health check endpoint for container orchestration platforms.

**Response (200 OK):**

```json
{
  "status": "healthy",
  "service": "reverse-document-generator",
  "version": "1.0.0"
}
```

### `GET /readiness`

Readiness probe endpoint to verify the application is ready to accept traffic.

**Response (200 OK):**

```json
{
  "status": "ready",
  "checks": {
    "configuration": true,
    "services_initialized": true
  }
}
```

---

## Testing

The test suite is built with **pytest 8.3.5**, **pytest-flask 1.3.0**, and **pytest-cov 6.1.1**.

### Run All Tests

```bash
pytest
```

Or using the Makefile:

```bash
make test
```

### Run Tests with Coverage Report

```bash
pytest --cov=app --cov-report=html
```

Or using the Makefile:

```bash
make test-cov
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures: Flask test client, mock services, sample data
├── test_routes/
│   ├── test_document.py     # Document generation/update API endpoint tests
│   ├── test_health.py       # Health check endpoint tests
│   └── test_notifications.py # Notification endpoint tests
├── test_services/
│   ├── test_document_service.py           # Document orchestration tests
│   ├── test_reverse_document_helper.py    # LangGraph workflow tests
│   ├── test_notification_service.py       # Pub/Sub notification tests
│   └── test_storage_service.py            # GCS storage tests
└── test_models/
    ├── test_state.py                      # ReverseDocumentState validation tests
    └── test_document_models.py            # Pydantic model serialization tests
```

All tests use the Flask test client with mock external services (LLM clients, GCS, Pub/Sub, Neo4j) to ensure tests run without requiring real external connections.

---

## Deployment

### Docker Build

```bash
docker build -t reverse-document-generator .
```

The Dockerfile uses **Ubuntu 24.04** as the base image with **Python 3.12**, **Node.js 20 LTS**, and **Chrome/Chromium** pre-installed. The container runs the Flask application via **Gunicorn**:

```dockerfile
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
```

### Cloud Run Service Deployment

The application is designed for deployment on **Google Cloud Run Service** (adapted from the original Cloud Run Job model). The CI/CD pipeline is defined in `.github/workflows/deploy.yml` and handles:

1. Building the Docker image
2. Pushing to Google Artifact Registry
3. Deploying to Cloud Run Service with OIDC authentication
4. Configuring secret injection for all API keys and credentials
5. Setting up VPC egress with a dedicated subnet for outbound API traffic

### VPC Egress Configuration

All outbound API traffic (LLM providers, Neo4j, platform services) routes through a VPC egress with a dedicated subnet. This is configured at the Cloud Run Service level and must be set up in the Google Cloud project before deployment.

### Makefile Deployment Shortcut

```bash
make deploy
```

---

## External Service Integrations

The application integrates with 11 external services, all of which are preserved from the original architecture:

| # | Service | Protocol | Purpose |
|---|---------|----------|---------|
| 1 | **Anthropic API** (Claude Opus 4.6) | HTTPS/JSON | Primary LLM for document section generation and context analysis |
| 2 | **OpenAI API** (GPT-5 Mini) | HTTPS/JSON | Secondary LLM for structured output validation and lightweight tasks |
| 3 | **Voyage AI API** (Embeddings) | HTTPS/JSON | Vector embeddings for semantic code search and context retrieval |
| 4 | **Neo4j Code Graph** | Bolt (`neo4j://`) | Read-only code graph queries via `CodeGraphBuilder` (35+ methods) |
| 5 | **Google Cloud Storage** | GCS API (HTTPS) | Progressive section upload and final document assembly persistence |
| 6 | **Google Cloud Pub/Sub** | gRPC | `IN_PROGRESS` and `DONE` notification event publishing |
| 7 | **archie-service-admin** | REST/HTTPS | Administrative operations via `ServiceClient` from `blitzy_utils` |
| 8 | **archie-secret-manager** | HTTPS | Runtime secret retrieval for API keys and credentials |
| 9 | **archie-service-markdown** | HTTPS POST | Mermaid diagram validation via `/v1/mermaid/validate` endpoint |
| 10 | **LangSmith** | HTTPS/JSON | LLM execution tracing, monitoring, and debugging |
| 11 | **Figma API** (optional) | Chrome DevTools / MCP | Design data extraction for UI-related specification sections |

### Internal Shared Libraries

| Library | Version | Key Components |
|---------|---------|----------------|
| `blitzy-platform-shared` | 0.0.616 | `CodeGraphBuilder`, `AdminStorageService`, `TECHNICAL_SECTION_PROMPTS`, `@archie_exponential_retry()`, LLM configurations, tools, MCP manager |
| `blitzy-utils` | 0.0.516 | `publish_notification`, `logger`, `download_repository_to_disk`, `get_head_commit_hash`, `ServiceClient`, Figma utilities, enums |

---

## License

This project is proprietary software developed for the Blitzy Platform. All rights reserved.
