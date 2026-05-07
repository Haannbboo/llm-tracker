[English](README.md) | [中文](README_CN.md)

# llm-tracker

本地优先的命令行 LLM 代理使用量追踪工具。

`llm-tracker` 记录 Codex、Claude Code、Gemini CLI 及 OpenAI/Anthropic 兼容客户端等工具的 token 使用量、费用估算、延迟、TTFT 和会话 ID。它适用于希望在每个项目中获得结构化的会话级使用数据，而无需在每个仓库中重新构建代理特定追踪逻辑的团队和个人项目。

它支持两种数据采集方式：

- OTLP 采集器接收编码代理发出的遥测数据。
- 透明代理转发提供商请求，并从响应中记录使用量。

llm-tracker 不管理凭证。使用代理时，API 密钥和授权头会原样转发。

## 功能特性

- 追踪 Codex、Claude Code、Gemini CLI 和直接代理流量。
- 保留会话 ID，用于按次运行和按代理的汇总统计。
- 通过 `scripts/llm-tracker` 打印命令级摘要。
- 默认支持 SQLite，通过 SQLAlchemy URL 支持 SQL 数据库。
- 根据 `~/.llm-tracker/config.yaml` 中的模型定价估算费用。
- 包含 React 仪表盘，展示使用量、费用、延迟和模型趋势。
- 通过 `scripts/start.sh` 和 `scripts/restart.sh` 保持代理遥测配置同步。

## 快速开始

前置条件：

- macOS 或 Linux shell 环境
- Python 3.13，或可用的 `uv`（启动脚本会自动创建环境）
- Node.js 18+（可选，用于仪表盘）

启动后端服务：

```bash
bash scripts/start.sh
```

启动脚本会创建 `.venv`、安装 Python 依赖、按需创建 `~/.llm-tracker/config.yaml`、执行数据库迁移、配置支持的代理遥测，并通过 Supervisor 启动服务。

检查服务状态：

```bash
bash scripts/status.sh
```

默认后端端口：

| 服务 | 默认 URL |
| --- | --- |
| 代理 | `http://127.0.0.1:4000` |
| API | `http://127.0.0.1:4001` |
| OTLP | `http://127.0.0.1:4002` |

启动仪表盘：

```bash
cd frontend
npm install
npm run dev
```

仪表盘通常可在 [http://localhost:5173](http://localhost:5173) 访问。

## 命令摘要

完整 CLI 参考请见 [docs/cli-reference.md](docs/cli-reference.md)，包含所有标志、退出码、追踪模式和服务管理命令。

使用仓库本地包装器运行代理或命令，并打印运行期间捕获的使用量：

```bash
scripts/llm-tracker -- codex
scripts/llm-tracker -- claude
scripts/llm-tracker -- gemini
scripts/llm-tracker -- codex exec "say hello in one sentence"
```

常用选项：

```bash
scripts/llm-tracker --json -- codex
scripts/llm-tracker --usage-only -- codex exec "say hello in one sentence"
scripts/llm-tracker --wait-ms 5000 -- codex exec "say hello in one sentence"
scripts/llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude
scripts/llm-tracker --proxy-env -- some-openai-compatible-cli
scripts/llm-tracker --no-summary -- gemini -p "say hello"
```

使用 `--proxy-env` 时，命令会在运行期间指向一个临时本地代理，从而在合并到主数据库之前隔离代理记录的使用量。

默认情况下，摘要输出到 stderr，以保持子命令的 stdout 可用。当另一个程序需要 stdout 仅包含 llm-tracker 摘要时，使用 `--usage-only`；当需要机器可读的 JSON 格式时，结合 `--json` 使用。包装器为每个命令启动一个临时本地 OTLP 采集器，在每次运行的 SQLite 数据库中记录使用量，然后在命令退出后将这些记录合并回主配置的数据库。

## 配置

主配置文件位于：

```text
~/.llm-tracker/config.yaml
```

最小提供商配置：

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

db:
  path: ~/.llm-tracker/usage.db
```

代理通过匹配请求中的 `model` 与已配置的提供商模型来路由请求，然后将请求转发到该提供商的 `base_url`。

如需使用 PostgreSQL 或 MySQL 代替 SQLite，请设置 `db.url`：

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

运行 `bash scripts/start.sh` 或 `bash scripts/restart.sh` 会将 `config.example.yaml` 中缺失的默认值合并到用户配置中，但不会覆盖现有值。

## 数据采集方式

### OTLP 采集器

Codex、Claude Code 和 Gemini CLI 可以发出 OpenTelemetry 日志。llm-tracker 在本地接收这些日志，并解析在 HTTP 代理层不可见的代理特定字段。

```text
Agent telemetry
      |
      v
llm-tracker OTLP collector
      |
      v
SQLite/Postgres/MySQL
```

启动脚本会配置：

- `~/.codex/config.toml` 用于 Codex OTLP 日志
- `~/.claude/settings.json` 用于 Claude Code OTLP 日志
- `~/.gemini/settings.json` 加 shell hook 用于 Gemini CLI 计时数据

### 透明代理

对于支持自定义 base URL 的工具，llm-tracker 可以位于客户端和上游提供商之间：

```text
LLM client
      |
      v
llm-tracker proxy
      |
      v
Upstream provider
```

支持的代理路径包括：

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/messages`

对于流式响应，代理将 TTFT 记录为直到第一个上游数据块到达的时间。

## 将客户端指向代理

对于 OpenAI 兼容客户端：

```bash
export OPENAI_BASE_URL=http://127.0.0.1:4000/v1
```

对于 Anthropic 兼容客户端：

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
```

命令包装器可以为子进程设置这些环境变量：

```bash
scripts/llm-tracker --proxy-env -- some-openai-compatible-cli
```

## 仪表盘

仪表盘位于 `frontend/` 目录，与 API 服务通信。它按以下顺序解析后端 API URL：

1. `LLM_TRACKER_API_URL`
2. `LLM_TRACKER_BACKEND_URL`
3. `~/.llm-tracker/config.yaml` 中的 `server.host` 和 `server.api_port`
4. `http://localhost:4001`

前端特定的配置请参见 [frontend/README.md](frontend/README.md)。

## 跟踪覆盖范围

| 指标 | Gemini CLI | Claude Code | Codex | 直接代理 |
| --- | --- | --- | --- | --- |
| 输入 token | OTLP | OTLP | OTLP | 响应 usage |
| 输出 token | OTLP | OTLP | OTLP | 响应 usage |
| 缓存读取 token | OTLP | OTLP | OTLP | 响应 usage |
| 缓存写入 token | 不可用 | OTLP | 不可用 | 不可用 |
| 推理 token | OTLP | 不可用 | OTLP | 响应 usage |
| 工具 token | OTLP | 不可用 | OTLP | 不可用 |
| 提示词长度 | OTLP | OTLP | OTLP | 不可用 |
| 延迟 | Hook/OTLP | OTLP | OTLP | 代理计时 |
| TTFT | Hook | 不可用 | OTLP | 仅流式 |
| 会话 ID | OTLP | OTLP | OTLP | 不可用 |

TTFT 应作为运维参考指标，而非计费级精确指标。每个代理暴露的计时数据各不相同。

## API 接口

常用本地端点：

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
```

仪表盘使用相同的 API。

## 开发

安装并启动后端服务：

```bash
bash scripts/start.sh
```

运行测试：

```bash
./.venv/bin/python -m pytest -q
```

管理服务：

```bash
bash scripts/restart.sh
bash scripts/stop.sh
bash scripts/status.sh
```

日志写入 `logs/` 目录。Supervisor 运行时文件位于 `~/.llm-tracker/run/`。

## 隐私说明

llm-tracker 设计为在本地运行。默认情况下，使用量存储在 `~/.llm-tracker/usage.db`。如果配置了 `db.url`，使用量数据将写入该数据库。

代理原样转发认证头。OTLP 负载由代理自身发出；如需严格控制收集的元数据，请检查代理的遥测设置。

## 开源协议

MIT 许可证。详见 [LICENSE](LICENSE)。
