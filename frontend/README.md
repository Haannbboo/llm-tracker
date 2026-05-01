# llm-tracker Dashboard

The frontend for visualizing LLM usage, cost trends, and performance metrics across different providers and agents.

## Prerequisites

- [Node.js](https://nodejs.org/) (v18 or later)
- [npm](https://www.npmjs.com/)

## Setup

1. **Install Dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Configuration**:
   The Vite dev server resolves the backend API URL in this order on each proxied request:
   1. `LLM_TRACKER_API_URL`
   2. `LLM_TRACKER_BACKEND_URL`
   3. `~/.llm-tracker/config.yaml` using `server.host` and `server.api_port`
   4. Fallback to `http://localhost:4001`

   Example override:
   ```bash
   LLM_TRACKER_API_URL=http://localhost:4011 npm run dev
   ```

   If you change `~/.llm-tracker/config.yaml` while the dev server is running, subsequent frontend API requests will use the updated `server.api_port` automatically.

## Development

To start the development server with hot-reload:

```bash
npm run dev
```

The dashboard will typically be available at [http://localhost:5173](http://localhost:5173).

## Production

To build the application for production:

```bash
npm run build
```

The build artifacts will be stored in the `dist/` directory. You can preview the production build locally using:

```bash
npm run preview
```

## Features

- **Usage Visualization**: Hourly and daily breakdown of token consumption.
- **Cost Tracking**: Estimates costs based on provider-specific pricing.
- **Performance Metrics**: Monitor latency and Time to First Token (TTFT) across agents.
- **Provider/Model Filtering**: Drill down into specific usage patterns.
