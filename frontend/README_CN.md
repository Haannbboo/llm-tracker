[English](README.md) | [中文](README_CN.md)

# llm-tracker 仪表盘

用于可视化不同提供商和代理的 LLM 使用量、费用趋势和性能指标的前端应用。

## 前置条件

- [Node.js](https://nodejs.org/)（v18 或更高版本）
- [npm](https://www.npmjs.com/)

## 安装配置

1. **安装依赖**：
   ```bash
   cd frontend
   npm install
   ```

2. **配置说明**：
   Vite 开发服务器按以下顺序在每次代理请求时解析后端 API URL：
   1. `LLM_TRACKER_API_URL`
   2. `LLM_TRACKER_BACKEND_URL`
   3. `~/.llm-tracker/config.yaml` 中的 `server.host` 和 `server.api_port`
   4. 回退到 `http://localhost:4001`

   配置覆盖示例：
   ```bash
   LLM_TRACKER_API_URL=http://localhost:4011 npm run dev
   ```

   如果在开发服务器运行期间修改了 `~/.llm-tracker/config.yaml`，后续的前端 API 请求会自动使用更新后的 `server.api_port`。

## 开发

启动带热重载的开发服务器：

```bash
npm run dev
```

仪表盘通常可在 [http://localhost:5173](http://localhost:5173) 访问。

## 生产环境

构建生产版本：

```bash
npm run build
```

构建产物将存储在 `dist/` 目录中。可在本地预览生产构建：

```bash
npm run preview
```

## 功能特性

- **使用量可视化**：按小时和按天展示 token 消耗明细。
- **费用追踪**：基于提供商特定定价估算费用。
- **性能指标**：监控各代理的延迟和首 token 时间（TTFT）。
- **提供商/模型筛选**：深入查看特定使用模式。
