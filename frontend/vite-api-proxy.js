import { resolveApiUrl } from './vite-api-url.js'

export function shouldProxyApiRequest(requestUrl) {
  const pathname = new URL(requestUrl, 'http://localhost').pathname
  return pathname === '/config' || pathname === '/usage' || pathname.startsWith('/usage/') || pathname === '/test-connectivity' || pathname === '/local/agents' || pathname === '/local/setup-health'
}

export function resolveProxyRequestUrl(
  requestUrl,
  { env, trackerConfigPath } = {},
) {
  const normalizedRequestUrl = new URL(requestUrl, 'http://localhost')
  return new URL(
    `${normalizedRequestUrl.pathname}${normalizedRequestUrl.search}`,
    resolveApiUrl({ env, trackerConfigPath }),
  ).toString()
}

async function readRequestBody(req) {
  const chunks = []
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  return chunks.length > 0 ? Buffer.concat(chunks) : undefined
}

function buildForwardHeaders(headers) {
  const forwarded = new Headers()
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue
    if (key.toLowerCase() === 'host') continue

    if (Array.isArray(value)) {
      for (const item of value) {
        forwarded.append(key, item)
      }
      continue
    }

    forwarded.set(key, value)
  }
  return forwarded
}

export function createApiProxyMiddleware({ env, trackerConfigPath } = {}) {
  return async function apiProxyMiddleware(req, res, next) {
    if (!req.url || !shouldProxyApiRequest(req.url)) {
      next()
      return
    }

    try {
      const response = await fetch(
        resolveProxyRequestUrl(req.url, { env, trackerConfigPath }),
        {
          method: req.method,
          headers: buildForwardHeaders(req.headers),
          body:
            req.method === 'GET' || req.method === 'HEAD'
              ? undefined
              : await readRequestBody(req),
        },
      )

      res.statusCode = response.status
      response.headers.forEach((value, key) => {
        res.setHeader(key, value)
      })

      const body = Buffer.from(await response.arrayBuffer())
      res.end(body)
    } catch (error) {
      res.statusCode = 502
      res.setHeader('content-type', 'application/json')
      res.end(
        JSON.stringify({
          detail:
            error instanceof Error
              ? error.message
              : 'Failed to proxy request to llm-tracker API',
        }),
      )
    }
  }
}

export function createApiProxyPlugin(options = {}) {
  return {
    name: 'llm-tracker-api-proxy',
    configureServer(server) {
      server.middlewares.use(createApiProxyMiddleware(options))
    },
  }
}
