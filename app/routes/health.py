"""
Health check and readiness probe Flask Blueprint.

Provides ``/health`` and ``/readiness`` endpoints required by container
orchestration platforms such as Google Cloud Run Service and Kubernetes.

The ``/health`` endpoint is a lightweight liveness probe that always returns
HTTP 200 when the Flask process is running.  The ``/readiness`` endpoint
verifies that critical configuration keys (LLM API keys, GCS bucket, Pub/Sub
project) are present — returning HTTP 200 when all checks pass and HTTP 503
otherwise.

**Security:** Readiness checks expose only boolean presence flags for config
keys.  Actual API key values, database credentials, and connection strings are
NEVER included in any response (AAP Section 0.7.2).
"""

import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify

# ---------------------------------------------------------------------------
# Module-level logger — health check requests are logged at DEBUG level to
# avoid cluttering INFO-level output (health probes fire very frequently in
# container orchestration environments).
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blueprint definition — registered WITHOUT a URL prefix in the application
# factory (``app/__init__.py``) so that routes are available at the root:
#   GET /health
#   GET /readiness
# ---------------------------------------------------------------------------
health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Liveness probe — indicates that the Flask process is running.

    Used by Cloud Run Service and Kubernetes liveness probes.  The endpoint
    is intentionally lightweight: it performs **no** external service calls
    and always returns HTTP 200 with a minimal JSON payload.

    No authentication is required (AAP Section 0.3.2 — security is
    platform-delegated).

    Returns:
        tuple: A ``(response, status_code)`` pair where *response* is a JSON
        object containing ``status``, ``service``, and ``timestamp`` fields,
        and *status_code* is always ``200``.
    """
    logger.debug("Health check probe received")
    return jsonify(
        {
            "status": "healthy",
            "service": "reverse-document-generator",
            "timestamp": datetime.utcnow().isoformat(),
        }
    ), 200


@health_bp.route("/readiness", methods=["GET"])
def readiness_check():
    """Readiness probe — verifies that critical service dependencies are configured.

    Used by Kubernetes / Cloud Run readiness probes to determine whether the
    container can accept traffic.  The endpoint inspects Flask application
    configuration for the **presence** of required keys and returns boolean
    flags.

    **Credential security (AAP Section 0.7.2):** Only boolean flags are
    returned.  Actual API key values, database credentials, and connection
    strings are NEVER exposed.

    Returns:
        tuple: A ``(response, status_code)`` pair where *response* is a JSON
        object containing ``status``, ``checks``, ``service``, and
        ``timestamp`` fields.  *status_code* is ``200`` when all checks pass
        and ``503`` when any critical check fails.
    """
    logger.debug("Readiness probe received")

    try:
        # ---- Configuration presence checks (boolean only) ----------------
        checks = {
            "flask_app": True,
            "config_loaded": bool(current_app.config.get("SERVICE_NAME")),
            "anthropic_configured": bool(
                current_app.config.get("ANTHROPIC_API_KEY")
            ),
            "openai_configured": bool(
                current_app.config.get("OPENAI_API_KEY")
            ),
            "gcs_configured": bool(
                current_app.config.get("GCS_BUCKET_NAME")
            ),
            "pubsub_configured": bool(
                current_app.config.get("PUBSUB_PROJECT_ID")
            ),
        }

        all_ready = all(checks.values())
        status_code = 200 if all_ready else 503

        return jsonify(
            {
                "status": "ready" if all_ready else "not_ready",
                "checks": checks,
                "service": "reverse-document-generator",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ), status_code

    except Exception as exc:
        # Catch-all so that a misconfigured app context never crashes the
        # readiness probe with an unhandled 500 — instead we return a
        # structured 503 with a safe error message.
        logger.error("Readiness probe failed: %s", str(exc))
        return jsonify(
            {
                "error": "Service Unavailable",
                "message": "Readiness probe encountered an internal error",
            }
        ), 503
