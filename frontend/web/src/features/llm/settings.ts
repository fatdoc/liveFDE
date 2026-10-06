export type LLMSettings = {
  revision: string
  base_url: string
  model: string
  timeout_seconds: number
  configured: boolean
  status: 'not_configured' | 'unverified' | 'checking' | 'verified' | 'check_failed' | 'unknown'
  checked_at: string | null
  last_error: string | null
  usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null
  debug_http: boolean
  analysis_enabled: false
}
export type Draft = Pick<LLMSettings, 'base_url' | 'model' | 'timeout_seconds'>
export function changed(saved: LLMSettings, draft: Draft, key: string) {
  return (
    !!key ||
    saved.base_url !== draft.base_url ||
    saved.model !== draft.model ||
    saved.timeout_seconds !== draft.timeout_seconds
  )
}
export function savePayload(saved: LLMSettings, draft: Draft, key: string) {
  return { ...draft, expected_revision: saved.revision, ...(key ? { api_key: key } : {}) }
}
export function statusText(status: LLMSettings['status']) {
  return (
    {
      not_configured: '尚未配置密钥',
      unverified: '未测试',
      checking: '测试中',
      verified: '连接测试成功',
      check_failed: '连接测试失败',
      unknown: '测试结果未知，禁止重复发送',
    }[status] || '状态未确认'
  )
}
export function safeReason(code: string | null) {
  const reasons: Record<string, string> = {
    revision_conflict: '配置版本已变化，请重新读取。',
    llm_settings_busy: '配置正在处理，请稍后读取状态。',
    llm_not_configured: '请先完成配置并保存密钥。',
    llm_request_reused: '此请求已处理，不会重复发送。',
    llm_check_limit: '已达到连接测试限制，请管理员核查记录。',
    llm_auth_failed: '服务鉴权失败，请核对密钥。',
    llm_model_not_found: '接口或模型不存在，请检查接口地址和模型名。',
    llm_rate_limited: '服务请求受限，请核对额度或限流状态。',
    llm_endpoint_rejected: '接口地址被服务端拒绝。',
    llm_http_not_allowed: '此 HTTP 接口未获服务端调试授权。',
    llm_dns_failed: '接口域名解析失败。',
    llm_timeout: '连接测试超时，请核查服务器记录。',
    llm_response_invalid: '服务响应未通过校验。',
    llm_response_too_large: '服务响应超过允许大小。',
    llm_upstream_failed: '上游服务未完成请求。',
    llm_result_unknown: '测试结果未知，请核查记录，不要重复发送。',
  }
  return code ? reasons[code] || '连接未通过检查，请管理员核对配置或服务状态。' : ''
}

export function validTimeout(seconds: number) {
  return Number.isInteger(seconds) && seconds >= 1 && seconds <= 120
}
