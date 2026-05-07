export type UsageSummary = {
  provider: string
  model: string
  requests: number
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
  latency_sum_ms: number | null
  avg_throughput: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  avg_effective_price_usd: number | null
  avg_effective_price_per_million_usd: number | null
  successful_requests: number
  failed_requests: number
}

export type ProviderUsage = {
  provider: string
  requests: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
  latency_sum_ms: number | null
  avg_throughput: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  avg_effective_price_usd: number | null
  avg_effective_price_per_million_usd: number | null
  successful_requests: number | null
  failed_requests: number | null
}

export type SourceUsage = {
  client_source: string | null
  requests: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
  latency_sum_ms: number | null
  avg_throughput: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  successful_requests: number | null
  failed_requests: number | null
}

export type UsageRow = {
  id: number
  ts: string
  provider: string
  model: string
  client_source: string | null
  endpoint: string
  prompt_tokens: number | null
  prompt_length: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  latency_ms: number | null
  ttft_ms: number | null
  tool_tokens: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  status: number | null
}

export type DailyUsage = {
  period: string
  requests: number
  prompt_tokens: number | null
  completion_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  avg_latency_ms: number | null
  latency_sum_ms: number | null
  avg_throughput: number | null
  successful_requests: number | null
  failed_requests: number | null
}

export type ActiveFilter = { provider: string; model: string | null } | null
export type DateRangeOption = '24h' | '7d' | '30d' | 'all' | 'custom'
