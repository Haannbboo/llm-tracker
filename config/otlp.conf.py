import os

from config.server_config import load_server_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_server = load_server_config()
bind = f"{_server.otlp_host}:{_server.otlp_port}"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
accesslog = os.path.join(ROOT, "logs/otlp.access.log")
errorlog = os.path.join(ROOT, "logs/otlp.error.log")
capture_output = True
graceful_timeout = 30
timeout = 300


def post_fork(server, worker):
    import logging
    from uvicorn.logging import AccessFormatter

    formatter = AccessFormatter(
        fmt='%(asctime)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=False,
    )
    for handler in logging.getLogger("uvicorn.access").handlers:
        handler.setFormatter(formatter)
