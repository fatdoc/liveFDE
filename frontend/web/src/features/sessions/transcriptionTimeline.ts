export function formatTimestamp(ms: unknown): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '时间未知'
  const whole = Math.floor(ms)
  return `${String(Math.floor(whole / 60000)).padStart(2, '0')}:${String(Math.floor(whole / 1000) % 60).padStart(2, '0')}.${String(whole % 1000).padStart(3, '0')}`
}
export function seekProblem(
  start: unknown,
  end: unknown,
  durationSeconds: number | null,
): string | null {
  if (
    typeof start !== 'number' ||
    typeof end !== 'number' ||
    !Number.isFinite(start) ||
    !Number.isFinite(end)
  )
    return '时间未知或无效，无法定位'
  if (start < 0 || end <= start) return '起止时间无效，无法定位'
  if (durationSeconds === null || !Number.isFinite(durationSeconds) || durationSeconds <= 0)
    return '等待媒体元数据，暂不能定位'
  if (start >= durationSeconds * 1000 || end > durationSeconds * 1000)
    return '时间超出当前材料范围，无法定位'
  return null
}
export function timestampOrigin(
  segment: { timestamp_source?: unknown },
  metadata?: Record<string, unknown>,
): string {
  const sources = metadata?.timestamp_sources
  const source =
    segment.timestamp_source ?? (Array.isArray(sources) && sources.length === 1 ? sources[0] : null)
  if (source === 'vad') return 'VAD 语音区间边界，非逐词对齐'
  if (source === 'vad_window') return 'VAD 分窗边界，非逐词对齐'
  if (source === 'provider') return '识别服务提供的时间戳，未验证逐词对齐'
  return '时间戳来源未确认，未验证逐词对齐'
}
