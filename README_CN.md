[English](README.md) | [中文](README_CN.md)

# llm-tracker

**面向命令行 LLM Agent 的本地优先可观测性工具。**

`llm-tracker` 用来查看你的 coding agents 到底在干什么：请求记录、token 使用量、费用估算、延迟、TTFT、模型、来源和 session ID。支持 **Claude Code**、**Codex**、**Gemini CLI**，也支持 OpenAI/Anthropic 兼容流量。

它适合那些本地同时跑多个 LLM Agent、又想在一个地方回答这些问题的人：

- 哪个 Agent/模型花钱最多？
- 我刚刚那条命令到底有没有被追踪到？
- 这次 coding session 花了多少钱？
- 哪些请求慢、走了流式、命中了缓存、用了 reasoning？

默认是本地部署：配置在 `~/.llm-tracker/config.yaml`，使用量数据默认存在 SQLite `~/.llm-tracker/usage.db`，服务绑定在本机 loopback 端口。

## 它能做什么

- **追踪常见 coding agents**：通过本地 OTLP telemetry 追踪 Claude Code、Codex 和 Gemini CLI。
- **追踪 OpenAI/Anthropic 兼容客户端**：通过可选的本地 proxy 转发并记录请求。
- **提供 Dashboard**：查看使用量、费用、延迟、模型、来源、请求日志、setup health 和 first-event onboarding。
- **输出命令级摘要**：用 `llm-tracker` 跑 agent，结束后打印这次运行的使用量。
- **保持可检查**：纯 YAML 配置，默认 SQLite，日志在 `logs/`，不依赖 hosted backend。
- **支持 SQL 数据库**：默认本地 SQLite，也可以通过 SQLAlchemy `db.url` 指向 PostgreSQL/MySQL。

## 采集方式

`llm-tracker` 有两条互补的数据采集路径：

```text
Claude Code / Codex / Gemini CLI
        │
        │ OTLP telemetry
        ▼
llm-tracker OTLP collector ──► database ──► dashboard / API / summaries
```

```text
OpenAI-compatible or Anthropic-compatible client
        │
        │ HTTP
        ▼
llm-tracker proxy ──► upstream provider
        │
        ▼
     database
```

Agent telemetry 更适合拿到 session、tool/reasoning metadata 等 agent-specific 字段。Proxy 更适合支持自定义 base URL 的客户端。

## 快速开始

### 前置条件

- macOS 或 Linux shell 环境
- Python 3.13，或者可用的 `uv` 让安装脚本创建环境
- Node.js 18+，用于构建和提供 Dashboard
- 可选：本地已安装 `claude`、`codex` 或 `gemini`

### 1. 一键 Bootstrap

```bash
bash scripts/bootstrap.sh
```

Bootstrap 会帮你处理这些烦人的东西：

1. 把 Python 依赖安装到 `.venv`
2. Node/npm 可用时构建 Dashboard
3. 按需创建 `~/.llm-tracker/config.yaml`
4. 为检测到的 Agent 配置本地 OTLP tracking
5. 用 Supervisor 启动 proxy、API 和 OTLP 服务
6. 检查服务端口和 Agent setup health
7. 在 `~/.local/bin/llm-tracker` 创建 CLI symlink

如果 `~/.local/bin` 不在 `PATH` 里，安装脚本会打印该加到 shell profile 的命令。

### 2. 打开 Dashboard

```bash
open http://localhost:4001
```

如果你在开发前端，想用 Vite dev server：

```bash
cd frontend
npm install
npm run dev
```

然后打开 [http://localhost:5173](http://localhost:5173)。

### 3. 生成第一条 tracked event

Bootstrap 之后，运行 Dashboard 里展示的命令，或者直接用下面这些：

```bash
llm-tracker codex exec "hello"
llm-tracker claude
llm-tracker gemini -p "hello"
```

如果 symlink 还没进 `PATH`，可以用 repo-local fallback：

```bash
llm-tracker codex exec "hello"
llm-tracker claude
llm-tracker gemini -p "hello"
```

空 Dashboard 会自动检查第一条 event。没有假 demo 数据，也不用手动 seed。

## CLI 示例

Wrapper 会运行子命令，捕获运行期间的使用量，然后打印摘要。

```bash
# 交互式 agents
llm-tracker codex
llm-tracker claude
llm-tracker gemini

# 一次性命令
llm-tracker codex exec "say hello in one sentence"
llm-tracker gemini -p "say hello in one sentence"

# 安装后的 CLI
llm-tracker codex exec "say hello in one sentence"
```

只有在传 `llm-tracker` 自己的 flags 时才需要 `--`：

```bash
llm-tracker --json -- codex
llm-tracker --usage-only -- codex exec "say hello in one sentence"
llm-tracker --wait-ms 5000 -- codex exec "say hello in one sentence"
llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude
llm-tracker --proxy-env -- some-openai-compatible-cli
llm-tracker --no-summary -- gemini -p "say hello"
```

完整 CLI 参考见 [docs/cli-reference.md](docs/cli-reference.md)，包括所有 flags、tracking modes、退出码、服务命令、API endpoints 和环境变量。

## Dashboard

Dashboard 提供：

- 无数据时的 first-event onboarding
- 使用量和费用概览
- 模型/来源拆分
- latency 和 TTFT 趋势
- 请求日志
- 已检测到的 Agent 和 setup health
- connectivity test

默认情况下，后端 API 会在 `http://localhost:4001` 提供构建后的 Dashboard。前端 dev server 按下面顺序解析 API URL：

1. `LLM_TRACKER_API_URL`
2. `LLM_TRACKER_BACKEND_URL`
3. `~/.llm-tracker/config.yaml` 中的 `server.host` 和 `server.api_port`
4. `http://localhost:4001`

前端相关说明见 [frontend/README.md](frontend/README.md)。

## 默认本地服务

| 服务 | 默认 URL | 用途 |
| --- | --- | --- |
| Proxy | `http://127.0.0.1:4000` | 转发 OpenAI/Anthropic 兼容请求并记录使用量 |
| API + Dashboard | `http://127.0.0.1:4001` | REST API 和构建后的 Dashboard |
| OTLP collector | `http://127.0.0.1:4002` | 本地 Agent telemetry ingestion |

服务命令：

```bash
bash scripts/status.sh
bash scripts/restart.sh
bash scripts/stop.sh
```

运行时文件在 `~/.llm-tracker/run/`。日志写入 `logs/`。

## 配置

主配置文件：

```text
~/.llm-tracker/config.yaml
```

最小 provider 和数据库配置：

```yaml
models:
  gpt-5.4:
    cost:
      input: 2.5
      output: 15.0
      cacheRead: 0.25

providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      gpt-5.4: {}

server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001
  otlp_port: 4002

db:
  path: ~/.llm-tracker/usage.db
```

如果要用 PostgreSQL 或 MySQL 替代 SQLite，设置 `db.url`：

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

`bash scripts/start.sh` 和 `bash scripts/restart.sh` 会把 `config.example.yaml` 里缺失的默认值合并进用户配置，但不会覆盖已有值。

## 把客户端指向 Proxy

OpenAI 兼容客户端：

```bash
export OPENAI_BASE_URL=http://127.0.0.1:4000/v1
```

Anthropic 兼容客户端：

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
```

也可以让 wrapper 只为某个子进程设置这些环境变量：

```bash
llm-tracker --proxy-env -- some-openai-compatible-cli
```

支持的 proxy paths：

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/messages`

对于 streaming response，proxy 会把 TTFT 记录为第一个 upstream chunk 到达前的时间。

## Tracking 覆盖范围

| 指标 | Gemini CLI | Claude Code | Codex | Direct proxy |
| --- | --- | --- | --- | --- |
| Input tokens | OTLP | OTLP | OTLP | Response usage |
| Output tokens | OTLP | OTLP | OTLP | Response usage |
| Cached tokens read | OTLP | OTLP | OTLP | Response usage |
| Cached tokens write | 不可用 | OTLP | 不可用 | 不可用 |
| Reasoning tokens | OTLP | 不可用 | OTLP | Response usage |
| Tool tokens | OTLP | 不可用 | OTLP | 不可用 |
| Prompt length | OTLP | OTLP | OTLP | 不可用 |
| Latency | Hook/OTLP | OTLP | OTLP | Proxy timing |
| TTFT | Hook | 不可用 | OTLP | Streaming only |
| Session ID | OTLP | OTLP | OTLP | 不可用 |

TTFT 是运维参考指标，不是 billing-grade 指标。每个 Agent 暴露的 timing 数据不一样。

## API

常用本地 endpoints：

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
curl http://127.0.0.1:4001/config
curl http://127.0.0.1:4001/local/setup-health
```

`/usage` query params：`limit`、`offset`、`provider`、`model`、`since`、`until`。

`/usage/daily` query params：`since`、`until`、`provider`、`model`、`granularity`、`tz_offset`。

## 开发

安装/启动后端服务：

```bash
bash scripts/start.sh
```

运行后端测试：

```bash
./.venv/bin/python -m pytest -q
```

运行前端测试和构建：

```bash
cd frontend
npm test
npm run build
```

维护者专用 bootstrap smoke test：

```bash
bash scripts/dev/smoke-bootstrap-container.sh
```

这个检查会在全新的 Docker 或 Apple `container` 环境里运行 `scripts/bootstrap.sh`。它不是普通用户 setup 的一部分。

## 隐私和安全说明

- `llm-tracker` 设计为本地运行。
- 使用量默认存储在 `~/.llm-tracker/usage.db`。
- 如果配置了 `db.url`，使用量数据会写入该数据库。
- Proxy 会原样转发 auth headers。
- `llm-tracker` 不管理 API keys。
- OTLP payload 由 Agent 自己发出；如果你需要严格控制 metadata，请检查 Agent telemetry settings。

## 贡献

欢迎 issues 和 PR。好的贡献通常包含：

- 清晰的 bug report 或产品问题
- 小而可测试的改动
- 改 Python 行为时配 backend tests（`pytest`）
- 改 Dashboard 行为时把 frontend tests 放到 `frontend/tests/`
- 改命令、setup 或行为时同步更新 docs

请保持示例一致：plain agent invocation 使用 `llm-tracker codex`、`llm-tracker claude` 或 `llm-tracker gemini`；只有传 `llm-tracker` 自己的 flags 时才保留 `--`。

## 开源协议

MIT。详见 [LICENSE](LICENSE)。
