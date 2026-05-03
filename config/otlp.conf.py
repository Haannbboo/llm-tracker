import os

import yaml

from config.runtime_ports import resolve_otlp_service_port

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(
    os.path.expanduser("~/.llm-tracker/config.yaml"), encoding="utf-8"
) as config_file:
    cfg = yaml.safe_load(config_file) or {}


def _resolve_bind(config):
    service_port = resolve_otlp_service_port(config)
    return f"{service_port.host}:{service_port.port}"


bind = _resolve_bind(cfg)
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
