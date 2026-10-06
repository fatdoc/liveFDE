export type DouyinSettings = {
  revision: string
  configured: boolean
  status: 'not_configured' | 'unverified' | 'verified' | 'needs_update' | 'check_failed'
  checked_at: string | null
  checked_source: string | null
  last_error: string | null
  service_ready: boolean
  checked_state: 'live' | 'not_live' | null
}
export const platformStatus: Record<DouyinSettings['status'], string> = {
  not_configured: '未配置',
  unverified: '已保存 · 尚未验证',
  verified: '当次解析已验证',
  needs_update: '需要核对接入信息',
  check_failed: '检查未通过',
}
export function platformError(code: string | null) {
  if (!code) return ''
  const messages: Record<string, string> = {
    https_required: '直播源地址不符合当前 HTTPS 要求，本次未通过检查。',
    domain_not_allowed: '直播来源域未获允许，本次未通过检查。',
    unsafe_stream_url: '直播来源地址不符合安全策略，本次未通过检查。',
    source_auth_required: '平台拒绝访问，请核对登录及授权条件，必要时更新 Cookie。',
    source_http_error: '平台返回 HTTP 错误，本次未验证登录状态。',
    source_rate_limited: '平台限制请求频率，请等待后手动检查。',
    source_challenge_required: '平台要求额外验证，本次无法确认连接。',
    source_schema_changed: '平台响应结构变化，需要维护采集适配。',
    source_protocol_error: '平台响应协议异常，本次未验证连接。',
    source_network_error: '网络连接失败，本次未验证登录状态。',
    validation_error: '输入格式不符合要求，请核对 Cookie 和直播间链接。',
    platform_not_configured: '当前工作区未保存 Cookie，请先保存。',
    platform_settings_busy: '已有平台设置操作正在执行，请等待后刷新。',
    platform_storage_unavailable: '平台私密存储暂不可用，操作结果尚未确认。',
    source_parse_failed: '平台响应无法解析，无法据此判断 Cookie 是否过期。',
    source_empty_response: '平台返回空响应，无法据此判断 Cookie 是否过期。',
    source_timeout: '平台响应超时，本次未验证。请稍后手动检查。',
    cookie_expired: '平台明确拒绝当前登录状态，请更新 Cookie 后检查。',
    credentials_expired: '平台明确拒绝当前登录状态，请更新 Cookie 后检查。',
    cookie_required: '请先保存抖音 Cookie。',
    credentials_missing: '请先保存抖音 Cookie。',
    invalid_cookie: 'Cookie 格式无效，请检查输入。',
    invalid_source: '请输入抖音电脑端数字直播间链接。',
    provider_dependencies_missing: '采集服务依赖尚未就绪。',
    upstream_version_mismatch: '采集组件版本不匹配，请联系管理员。',
    check_in_progress: '已有检查正在执行，请等待完成后刷新状态。',
  }
  return messages[code] ?? '本次检查未完成，请核对接入条件；当前结果不能证明 Cookie 过期。'
}
export const validDouyinSource = (value: string) =>
  /^https:\/\/live\.douyin\.com\/\d+\/?$/.test(value.trim())
