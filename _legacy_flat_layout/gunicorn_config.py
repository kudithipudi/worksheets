"""
Gunicorn configuration for Texas Worksheet Generator.
Binds to a Unix socket consumed by Nginx.
"""

import multiprocessing

# ── Binding ────────────────────────────────────────────────────────────────────
bind = "unix:/var/www/worksheets/worksheets.sock"

# ── Worker processes ───────────────────────────────────────────────────────────
# UvicornWorker enables async request handling required by FastAPI
worker_class = "uvicorn.workers.UvicornWorker"
workers = 1
worker_connections = 1000

# ── Timeouts ───────────────────────────────────────────────────────────────────
# Must exceed the 90-second LLM API timeout in main.py
timeout = 120
graceful_timeout = 30
keepalive = 5

# ── Stability ──────────────────────────────────────────────────────────────────
max_requests = 1000
max_requests_jitter = 100
preload_app = True

# ── Logging ────────────────────────────────────────────────────────────────────
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'
