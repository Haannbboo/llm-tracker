export const zh: Record<string, string> = {
  // Navigation
  'Dashboard': '仪表盘',
  'Request Logs': '请求日志',
  'Settings': '设置',
  'Connectivity Test': '连通性测试',

  // Theme
  'Switch to light mode': '切换到亮色模式',
  'Switch to dark mode': '切换到暗色模式',

  // Date range
  'Last 24 Hours': '最近 24 小时',
  'Last 7 Days': '最近 7 天',
  'Last 30 Days': '最近 30 天',
  'All Time': '全部时间',
  'Custom Range': '自定义范围',

  // Source filter
  'All Sources': '全部来源',

  // Dashboard widgets
  'Token Usage': 'Token 用量',
  'Requests': '请求数',
  'Estimated Cost': '预估费用',
  'Performance': '性能',
  'Average Response': '平均响应',
  'RPM': 'RPM',
  'TPM': 'TPM',
  'Success Rate:': '成功率：',

  // Dashboard widget details
  'In:': '输入：',
  'Out:': '输出：',
  'Cached:': '缓存：',
  'Hit)': '命中)',
  'Avg:': '平均：',
  'tokens/req': 'tokens/请求',
  '/ req': '/ 请求',
  'Avg $/M tokens:': '平均 $/百万 tokens：',
  'Avg Throughput:': '平均吞吐量：',

  // Chart titles
  'Hourly Usage Trend': '每小时用量趋势',
  'Daily Usage Trend': '每日用量趋势',
  'Cache Hit Rate': '缓存命中率',
  'Top Models': '热门模型',
  'Top Providers': '热门供应商',
  'Top Sources': '热门来源',

  // Chart legend labels
  'Input': '输入',
  'Cached': '缓存',
  'Output': '输出',
  'Input Cost': '输入费用',
  'Output Cost': '输出费用',
  'Tokens': 'Tokens',
  'Cost': '费用',
  'Throughput': '吞吐量',
  'Speed': '速度',

  // Chart messages
  'No trend data available': '暂无趋势数据',
  'No cache data available': '暂无缓存数据',
  'No data available': '暂无数据',
  'No activity': '无活动',
  'No requests': '无请求',

  // TrendChart tooltips
  'Input:': '输入：',
  'Output:': '输出：',
  'Total Tokens:': '总 Tokens：',
  'Est. Cost:': '预估费用：',
  'Input Cost:': '输入费用：',
  'Output Cost:': '输出费用：',
  'Total Cost:': '总费用：',
  'Tokens:': 'Tokens：',
  'Requests:': '请求数：',

  // CacheHitRateChart
  'Hit Rate': '命中率',
  'avg': '平均',
  'Hit Rate:': '命中率：',
  'Prompt:': '提示词：',

  // DailyHeatmap
  'Daily Activity': '每日活动',
  'Success Rate': '成功率',
  'Less': '少',
  'More': '多',
  '100%': '100%',
  'Fail': '失败',
  'Sun': '日',
  'Mon': '一',
  'Tue': '二',
  'Wed': '三',
  'Thu': '四',
  'Fri': '五',
  'Sat': '六',
  'Total:': '总计：',
  'Cost:': '费用：',
  'Successful:': '成功：',
  'Failed:': '失败：',

  // Logs page filters
  'Model': '模型',
  'Source': '来源',
  'Date Range': '时间范围',
  'Since': '开始时间',
  'Until': '结束时间',
  'Refresh': '刷新',
  'Last 24h': '最近 24 小时',

  // Table headers
  'Time': '时间',
  'Provider': '供应商',
  'Input (Prompt)': '输入（提示词）',
  'Status': '状态',

  // TTFT tooltip
  'TTFT / Latency': 'TTFT / 延迟',
  'Claude Code: No TTFT': 'Claude Code：无 TTFT',
  'Gemini CLI: Time to first chunk': 'Gemini CLI：首块时间',
  'Codex: Actual TTFT': 'Codex：实际 TTFT',
  'Proxy: Time to first chunk': '代理：首块时间',

  // Table body
  'tokens': 'tokens',
  '(Prompt:': '（提示词：',
  ' chars)': ' 字符）',
  'Cache read': '缓存读取',
  'Reasoning': '推理',

  // Cost tooltip
  'Cache:': '缓存：',

  // TTFT/Latency titles
  'Time To First Token': '首 Token 时间',
  'Total Latency': '总延迟',

  // Pagination
  'No requests found for the selected filters.': '未找到符合筛选条件的请求。',
  'Showing': '显示',
  'of': '/',
  'logs': '条日志',
  'Prev': '上一页',
  'Next': '下一页',
  'Jump:': '跳转：',
  '/ page': '/ 页',

  // Settings - Active Providers
  'Active Providers': '活跃供应商',
  'Base URL': '基础 URL',
  'Models': '模型',
  'No providers configured in config.yaml.': 'config.yaml 中未配置供应商。',
  'Cost Override': '费用覆盖',

  // Settings - Model Pricing
  'Model Pricing': '模型定价',
  'Scope:': '范围：',
  'Global Default': '全局默认',
  'Provider:': '供应商：',
  'Input (per 1M)': '输入（每百万）',
  'Output (per 1M)': '输出（每百万）',
  'Cache Read (per 1M)': '缓存读取（每百万）',
  'Cache Write (per 1M)': '缓存写入（每百万）',
  'No global models configured in config.yaml.': 'config.yaml 中未配置全局模型。',
  'Provider Override': '供应商覆盖',

  // Settings - Configuration
  'Configuration (YAML)': '配置（YAML）',
  'Directly edit your <code>config.yaml</code>. Providers and routing are defined here.': '直接编辑 <code>config.yaml</code>。供应商和路由在此定义。',
  'Configuration saved successfully': '配置保存成功',
  'Save Configuration': '保存配置',
  'Saving...': '保存中...',

  // Connectivity Test
  'Upstream Connectivity Test': '上游连通性测试',
  'The upstream API root URL, e.g. https://api.openai.com/v1': '上游 API 根 URL，例如 https://api.openai.com/v1',
  'API Key': 'API 密钥',
  'Format': '格式',
  'OpenAI': 'OpenAI',
  'Chat Completion': '聊天补全',
  'Anthropic': 'Anthropic',
  'Claude': 'Claude',
  'Codex': 'Codex',
  'Responses': 'Responses',
  'Custom:': '自定义：',
  'Message': '消息',
  'Testing...': '测试中...',
  'Run Connectivity Test': '运行连通性测试',
  'Manual curl equivalent': '等效 curl 命令',
  'Copy': '复制',
  'Copied': '已复制',
  'Test Result': '测试结果',
  'Results will appear here after testing': '测试后结果将显示在此处',
  'Status Code': '状态码',
  'Error': '错误',
  'Latency': '延迟',
  'Response': '响应',
  'Upstream returned HTML -- check that base_url points to an API endpoint': '上游返回了 HTML — 请检查 base_url 是否指向 API 端点',
  'Response Body': '响应体',

  // Error messages
  'Failed to fetch dashboard data': '获取仪表盘数据失败',
  'Failed to fetch log data': '获取日志数据失败',
  'Unknown error': '未知错误',
  'Failed to save config': '保存配置失败',
  'Connection error while saving config': '保存配置时连接错误',
  'Test failed': '测试失败',

  // ModelSelector
  'All Models': '全部模型',
  'model': '个模型',
  'models': '个模型',

  // SourceTokenChart
  'unknown': '未知',
}
