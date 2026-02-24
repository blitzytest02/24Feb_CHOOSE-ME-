"""
Gunicorn WSGI Server Configuration
===================================

Production-grade Gunicorn configuration for the Flask Reverse Document Generator
application (archie-job-reverse-document-generator). This configuration is optimized
for deployment on Google Cloud Run Service.

Key Design Decisions:
    - Extended timeout (300s) for API request handling. The actual document generation
      (which can run up to 24 hours) executes in background threads and does NOT block
      the Gunicorn request/response cycle. API endpoints return immediately with a job
      identifier for status polling.
    - Dynamic worker count based on available CPU cores ensures optimal resource
      utilization across different deployment environments (local dev, Cloud Run, GKE).
    - Logging directed to stdout/stderr for compatibility with container orchestration
      platforms (Cloud Run, Kubernetes) that capture container stdout/stderr.
    - Worker recycling via max_requests prevents memory leaks in long-running processes,
      with jitter to avoid thundering herd restarts.
    - Application preloading (preload_app=True) reduces memory footprint by sharing
      application code across forked worker processes via copy-on-write semantics.

Usage:
    Production:
        gunicorn --config gunicorn.conf.py wsgi:app

    Override settings via environment or CLI:
        gunicorn --config gunicorn.conf.py --workers 2 --timeout 600 wsgi:app

References:
    - Gunicorn Settings: https://docs.gunicorn.org/en/stable/settings.html
    - Cloud Run Container Contract: https://cloud.google.com/run/docs/reference/container-contract
"""

import multiprocessing
import os

# =============================================================================
# Server Binding
# =============================================================================
# Bind to all network interfaces on port 8080, which is the default port
# expected by Google Cloud Run. The PORT environment variable can override
# this for flexibility across deployment environments.

bind = "0.0.0.0:{port}".format(port=os.environ.get("PORT", "8080"))

# =============================================================================
# Worker Configuration
# =============================================================================
# Dynamic worker count based on available CPU cores. The formula
# (cpu_count * 2 + 1) is the Gunicorn-recommended default for I/O-bound
# applications. For CPU-bound workloads, use cpu_count + 1 instead.
# The GUNICORN_WORKERS environment variable allows runtime override for
# constrained environments (e.g., Cloud Run instances with limited vCPUs).
#
# In Cloud Run, the available CPU count reflects the allocated vCPUs for
# the service revision, so this scales automatically with the configured
# resource limits.

workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Synchronous worker class is appropriate for Flask (WSGI) applications.
# Flask does not natively support async/await, so the 'sync' worker type
# is the correct choice. For async frameworks (e.g., Quart), use 'uvicorn'
# or 'gevent' workers instead.

worker_class = "sync"

# Threads per worker process. Each worker can handle this many concurrent
# requests using Python threads. Combined with the worker count, total
# concurrent request capacity = workers * threads. For this application,
# API endpoints return quickly (job ID response), so 2 threads per worker
# provides sufficient concurrency without excessive thread overhead.

threads = int(os.environ.get("GUNICORN_THREADS", "2"))

# =============================================================================
# Timeout Configuration (CRITICAL)
# =============================================================================
# Extended timeout of 300 seconds (5 minutes) for request handling.
#
# IMPORTANT: This timeout governs how long a Gunicorn worker may spend
# processing a single HTTP request before being forcefully killed.
# It does NOT need to cover the full document generation duration (up to
# 24 hours) because:
#   1. The POST /api/v1/documents/generate endpoint launches document
#      generation in a background thread and returns immediately with a
#      job identifier (< 1 second typical response time).
#   2. The background thread runs independently of the Gunicorn worker
#      lifecycle and communicates progress via Pub/Sub notifications.
#   3. Clients poll GET /api/v1/documents/<id>/status for progress.
#
# The 300-second timeout accommodates:
#   - Complex request validation and state initialization
#   - LLM client and external service connectivity checks during startup
#   - Health/readiness probe responses under load
#   - Any unexpectedly slow synchronous operations in the request path

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))

# Graceful shutdown timeout in seconds. When Gunicorn receives SIGTERM
# (e.g., during Cloud Run scaling down or deployment rollover), workers
# have this many seconds to finish processing in-flight requests before
# being forcefully terminated. 120 seconds allows ample time for request
# completion and connection draining.

graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "120"))

# HTTP keep-alive timeout in seconds. Controls how long an idle connection
# is kept open waiting for new requests from the same client. Cloud Run's
# load balancer has its own connection timeout, so 5 seconds is a
# conservative default that prevents resource exhaustion from idle
# connections while supporting HTTP/1.1 connection reuse.

keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

# =============================================================================
# Logging Configuration
# =============================================================================
# Access and error logs are directed to stdout ("-") and stderr ("-")
# respectively, following the twelve-factor app methodology. Container
# orchestration platforms (Cloud Run, Kubernetes) capture stdout/stderr
# and route them to centralized logging services (e.g., Cloud Logging).
#
# Setting logs to "-" ensures:
#   - No log files accumulate inside the container filesystem
#   - Logs are immediately available in Cloud Logging / Stackdriver
#   - Container image remains stateless and ephemeral

accesslog = "-"

errorlog = "-"

# Log level for Gunicorn's internal error log. Valid levels:
# debug, info, warning, error, critical. The GUNICORN_LOGLEVEL
# environment variable allows runtime adjustment without redeployment.

loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")

# Access log format following the Combined Log Format convention.
# Fields:
#   %(h)s  — Remote address (client IP)
#   %(l)s  — '-' (ident, not used)
#   %(u)s  — '-' (user, not used in this API)
#   %(t)s  — Date and time of the request
#   %(r)s  — Status line (e.g., "GET /health HTTP/1.1")
#   %(s)s  — HTTP status code
#   %(b)s  — Response content length in bytes
#   %(f)s  — Referrer header
#   %(a)s  — User-Agent header
#
# This format is compatible with standard log analysis tools and provides
# sufficient detail for request tracing and performance monitoring.

access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# =============================================================================
# Process Naming
# =============================================================================
# Sets the Gunicorn process title visible in system process listings
# (e.g., `ps aux`, `htop`). This aids in identifying the application
# when multiple Gunicorn instances run on the same host.

proc_name = "reverse-document-generator"

# =============================================================================
# Server Mechanics
# =============================================================================
# Preload the Flask application before forking worker processes. This has
# two key benefits:
#   1. Memory efficiency: The application code is loaded once in the master
#      process and shared across workers via copy-on-write (COW) memory
#      pages, reducing total memory footprint.
#   2. Faster worker spawning: Workers don't need to individually import
#      and initialize the application, reducing startup time.
#
# Trade-off: Code changes require a full Gunicorn restart (not just worker
# reload). This is acceptable for production deployments where rolling
# restarts are managed by the container orchestrator.

preload_app = True

# Worker recycling: Automatically restart each worker after processing
# this many requests. This is a safeguard against gradual memory leaks
# in long-running Python processes (e.g., from LLM client libraries,
# graph database drivers, or GCS client caching). A value of 1000
# provides a good balance between stability and restart overhead.

max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))

# Jitter added to max_requests to prevent all workers from restarting
# simultaneously (thundering herd problem). Each worker's actual restart
# threshold is max_requests + random(0, max_requests_jitter). This
# ensures staggered restarts, maintaining continuous request handling
# capacity during worker recycling.

max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))
