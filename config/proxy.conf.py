import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(
    os.path.expanduser("~/.llm-tracker/config.yaml"), encoding="utf-8"
) as config_file:
    cfg = yaml.safe_load(config_file) or {}
server = cfg.get("server", {})

bind = f"{server.get('host', '127.0.0.1')}:{int(server.get('port', 4000))}"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
accesslog = os.path.join(ROOT, "logs/proxy.access.log")
errorlog = os.path.join(ROOT, "logs/proxy.error.log")
capture_output = True
graceful_timeout = 30
timeout = 300


def post_fork(server, worker):
    # UvicornWorker.__init__ copies gunicorn's access log handlers onto uvicorn.access,
    # using gunicorn's plain %(message)s formatter. Replace it with one that adds timestamps.
    import logging
    from uvicorn.logging import AccessFormatter

    formatter = AccessFormatter(
        fmt='%(asctime)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=False,
    )
    for handler in logging.getLogger("uvicorn.access").handlers:
        handler.setFormatter(formatter)
