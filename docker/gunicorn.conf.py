"""Gunicorn configuration for production deployment."""

import multiprocessing
import os

# Bind to port from environment (Digital Ocean uses 8080)
bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"

# Workers: (2 * CPU cores) + 1 is a good starting point
# For Digital Ocean Apps, use a fixed number based on dyno size
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker class: sync is fine for most Django apps
worker_class = "sync"

# Threads per worker (for I/O bound workloads)
threads = int(os.getenv("GUNICORN_THREADS", 2))

# Timeout for worker processes (seconds)
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))

# Keep-alive connections (seconds)
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# Maximum requests per worker before restart (prevents memory leaks)
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 100))

# Graceful timeout for worker shutdown
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Preload app for faster worker startup (but uses more memory at startup)
preload_app = True

# Forward X-Forwarded-* headers (important behind load balancer)
forwarded_allow_ips = "*"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None
