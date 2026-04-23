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
   Ensure the `.env` file in the `frontend` directory points to your running API service.
   ```env
   LLM_TRACKER_BACKEND_URL=http://localhost:4001
   ```

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
