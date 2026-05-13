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
  status_429: number | null
  status_4xx: number | null
  status_5xx: number | null
  status_unknown: number | null
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
  status_429: number | null
  status_4xx: number | null
  status_5xx: number | null
  status_unknown: number | null
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
  status_429: number | null
  status_4xx: number | null
  status_5xx: number | null
  status_unknown: number | null
}

export type UsageRow = {
  id: number
  ts: string
  provider: string
  model: string
  client_source: string | null
  session_id: string | null
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
  status_429: number | null
  status_4xx: number | null
  status_5xx: number | null
  status_unknown: number | null
}

export type ActiveFilter = { 
  provider: string; 
  model: string | null; 
  only_failed?: boolean;
  status_429?: boolean;
  status_4xx?: boolean;
  status_5xx?: boolean;
} | null
export type DateRangeOption = '24h' | '7d' | '30d' | 'all' | 'custom'

export type SessionOutcome = 'solved' | 'partial' | 'failed' | 'stuck' | 'no_op' | 'unknown'
export type SessionEvaluationSource = 'manual' | 'heuristic' | 'llm'

export type SessionEvaluation = {
  session_id: string
  outcome: SessionOutcome
  source: SessionEvaluationSource
  confidence: number | null
  task_title: string | null
  summary: string | null
  evidence: string[]
  failure_reason: string | null
  evaluated_at: string | null
}

export type SessionSummary = {
  session_id: string
  client_source: string
  model: string
  started: string
  ended: string
  duration_s: number
  request_count: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  cached_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
  latency_sum_ms: number
  avg_ttft_ms: number
  successful_requests: number
  failed_requests: number
  status_429: number | null
  status_4xx: number | null
  status_5xx: number | null
  status_unknown: number | null
  evaluation: SessionEvaluation | null
}

export type SessionsSummary = {
  session_count: number
  avg_duration_s: number
  total_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
}

export type ModelEffectivenessGroup = {
  key: string
  session_count: number
  evaluated_count: number
  solved_count: number
  partial_count: number
  failed_count: number
  stuck_count: number
  unknown_count: number
  no_op_count: number
  solve_rate: number | null
  total_cost_usd: number
  cost_per_solved: number | null
  avg_duration_s: number
}

export type ModelEffectivenessResponse = {
  groups: ModelEffectivenessGroup[]
}

export type DailyEffectivenessGroup = {
  model: string
  client_source: string
  session_count: number
  evaluated_count: number
  solved_count: number
  failed_count: number
  stuck_count: number
  total_cost_usd: number
  cost_per_solved: number | null
  solve_rate: number | null
}

export type DailyEffectivenessReport = {
  date: string
  summary: string
  session_count: number
  evaluated_count: number
  classified_count: number
  solved_count: number
  partial_count: number
  failed_count: number
  stuck_count: number
  no_op_count: number
  unknown_count: number
  total_cost_usd: number
  highlights: string[]
  needs_attention: string[]
  model_takeaways: string[]
  groups: DailyEffectivenessGroup[]
}

export type SetupAgentHealth = {
  configured: boolean
  endpoint_matches: boolean
  configured_endpoint: string | null
  expected_endpoint: string
  status: 'ready' | 'missing_config' | 'wrong_endpoint'
}

export type SetupDiagnostics = {
  expected: {
    otlp_endpoint: string
    otlp_logs_endpoint: string
  }
  summary: {
    total_agents: number
    configured_agents: number
    matching_agents: number
  }
  agents: Record<string, SetupAgentHealth>
}

export type OnboardingCopiedCommand = {
  source: string
  command: string
}
