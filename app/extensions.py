"""
Flask extension initialization for the Reverse Document Generator.

This module centralizes the initialization of Flask extensions and shared
service objects that need to be accessible across the application. It follows
the Flask extension pattern where extensions are instantiated at module level
and later initialized with the app via ``init_extensions()``.

Service modules (``llm_service``, ``storage_service``, ``notification_service``,
etc.) register their instances in the ``services`` dictionary during
``create_app()``.  Route handlers and background tasks retrieve them at runtime
through ``get_service()`` which reads from the current application context.

Exports:
    init_extensions  – Binds extensions to a Flask application instance.
    services         – Module-level dict holding registered service objects.
    get_service      – Convenience helper for looking up a service by name.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, current_app

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared service registry
# ---------------------------------------------------------------------------
# This dictionary is populated by service initializers during create_app()
# and subsequently stored on ``app.extensions['services']`` so that each
# request context can access them via ``current_app``.
services: dict[str, Any] = {}


def init_extensions(app: Flask) -> None:
    """Initialise Flask extensions and bind the shared service registry.

    This function is called once by :func:`app.create_app` after the
    application configuration has been loaded.  It performs the following:

    1. Configures the root Python logger to the level specified by the
       ``LOG_LEVEL`` configuration key (defaults to ``INFO``).
    2. Stores a reference to the module-level ``services`` dictionary in
       ``app.extensions['services']`` so that it is reachable through
       ``current_app.extensions['services']`` inside request contexts.
    3. Logs a confirmation message upon successful initialisation.

    Args:
        app: The Flask application instance to initialise against.
    """
    # ------------------------------------------------------------------
    # 1.  Configure logging from application config
    # ------------------------------------------------------------------
    log_level_name: str = app.config.get("LOG_LEVEL", "INFO")
    numeric_level: int = getattr(logging, log_level_name.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Also ensure the root logger respects the configured level so that
    # third-party library loggers are captured correctly.
    logging.getLogger().setLevel(numeric_level)

    # ------------------------------------------------------------------
    # 2.  Bind the services registry to the Flask app
    # ------------------------------------------------------------------
    app.extensions["services"] = services

    # ------------------------------------------------------------------
    # 3.  Log successful initialisation
    # ------------------------------------------------------------------
    logger.info(
        "Flask extensions initialised successfully (log_level=%s)",
        log_level_name.upper(),
    )


def get_service(name: str) -> Any:
    """Retrieve a registered service instance by name.

    The lookup is performed against the ``services`` dictionary stored in
    ``current_app.extensions['services']``.  This ensures that every call
    resolves within the correct Flask application context, which is critical
    for test isolation and multi-app scenarios.

    Args:
        name: The key under which the service was registered (e.g.
              ``'llm_service'``, ``'storage_service'``).

    Returns:
        The service instance associated with *name*.

    Raises:
        KeyError: If no service is registered under *name*.  The error
            message lists all currently available service names to aid
            debugging.
    """
    svc_registry: dict[str, Any] = current_app.extensions.get("services", {})
    if name not in svc_registry:
        available = ", ".join(sorted(svc_registry.keys())) or "(none)"
        raise KeyError(
            f"Service '{name}' is not registered. "
            f"Available services: {available}"
        )
    return svc_registry[name]
