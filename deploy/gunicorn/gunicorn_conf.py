#!/usr/bin/env python3
"""Gunicorn configuration file for safefamily."""
# TODOdd: not using this yet

import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"

# Process naming
proc_name = "safefamily"

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn/safefamily.pid"
user = "safefamily"
group = "safefamily"
tmp_upload_dir = None
