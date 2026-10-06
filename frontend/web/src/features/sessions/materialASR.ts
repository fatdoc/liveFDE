import type { ASRSettings } from '../asr/types'
export type ProviderInfo = {
  provider: 'local' | 'tencent'
  configured: boolean
  reason: string | null
  max_duration_seconds: number | null
  max_audio_bytes: number | null
  network_checked: false
}
export type MaterialGrant = {
  expected_revision: number
  allow_network: boolean
  max_requests: number | null
  max_cost_usd: number | null
}
export function providerReason(code: string | null) {
  const messages: Record<string, string> = {
    model_not_registered: '此识别服务尚未在服务器注册配置；腾讯云需管理员单独配置。',
    model_configuration_missing: '服务端尚未配置识别模型。',
    provider_disabled: '此识别服务尚未启用。',
    asr_provider_disabled: '此识别服务尚未启用。',
    credentials_missing: '腾讯云凭据尚未配置，请管理员配置。',
    tencent_credentials_missing: '腾讯云凭据尚未配置，请管理员配置。',
    local_model_missing: '本地识别模型尚未准备。',
    configuration_invalid: '服务端识别配置无效。',
  }
  return code ? messages[code] || '识别服务配置尚未就绪，请管理员检查。' : '尚未收到服务配置状态。'
}
export function materialBlocker(info: ProviderInfo | undefined, duration: number | null) {
  if (!info?.configured) return providerReason(info?.reason ?? null)
  if (info.max_duration_seconds === null) return '材料时长限制尚未确认，暂不能提交。'
  if (duration !== null && Number.isFinite(duration) && duration > info.max_duration_seconds)
    return `材料超过当前服务 ${info.max_duration_seconds} 秒上限，请改用可支持此时长的服务。`
  if (
    info.provider === 'tencent' &&
    (duration === null || !Number.isFinite(duration) || duration <= 0)
  )
    return '尚未取得有效材料时长，不能提交云端转写。'
  return null
}
export function cloudBudgetValid(requests: string, cost: string) {
  return (
    Number.isInteger(Number(requests)) &&
    Number(requests) >= 1 &&
    Number(requests) <= 10 &&
    Number.isFinite(Number(cost)) &&
    Number(cost) > 0 &&
    Number(cost) <= 100
  )
}
export function serviceChanged(settings: ASRSettings, provider: ASRSettings['provider']) {
  return settings.provider !== provider
}
