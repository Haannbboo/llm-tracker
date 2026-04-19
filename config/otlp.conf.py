import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(
    os.path.expanduser("~/.llm-tracker/config.yaml"), encoding="utf-8"
) as config_file:
    cfg = yaml.safe_load(config_file) or {}
server = cfg.get("server", {})
proxy_port = int(server.get("port", 4000))
api_port = int(server.get("api_port", proxy_port + 1))

bind = f"{server.get('host', '0.0.0.0')}:{int(server.get('otlp_port', api_port + 1))}"
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
