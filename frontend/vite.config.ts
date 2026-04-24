import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl =
    env.LLM_TRACKER_API_URL || env.LLM_TRACKER_BACKEND_URL || 'http://localhost:4001'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/usage': apiUrl,
        '/config': apiUrl,
      },
    },
  }
})
