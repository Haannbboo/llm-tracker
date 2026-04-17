import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(
    os.path.expanduser("~/.llm-tracker/config.yaml"), encoding="utf-8"
) as config_file:
    cfg = yaml.safe_load(config_file) or {}
server = cfg.get("server", {})
proxy_port = int(server.get("port", 4000))

bind = f"{server.get('host', '0.0.0.0')}:{int(server.get('api_port', proxy_port + 1))}"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
accesslog = os.path.join(ROOT, "logs/api.access.log")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
errorlog = os.path.join(ROOT, "logs/api.error.log")
capture_output = True
graceful_timeout = 30
timeout = 300
