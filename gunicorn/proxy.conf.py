import os
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.expanduser("~/.llm-tracker/config.yaml")) as _f:
    _cfg = yaml.safe_load(_f) or {}
_srv = _cfg.get("server", {})

bind = f"{_srv.get('host', '0.0.0.0')}:{int(_srv.get('port', 4000))}"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
accesslog = os.path.join(_ROOT, "logs/proxy.access.log")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
errorlog = os.path.join(_ROOT, "logs/proxy.error.log")
capture_output = True
graceful_timeout = 30
timeout = 300
