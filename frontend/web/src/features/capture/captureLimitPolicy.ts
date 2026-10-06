import type { CaptureLimits } from './types'
export function recordingChoiceValid(
  limits: CaptureLimits | undefined,
  seconds: number,
  bytes: number,
) {
  if (
    !limits ||
    !Number.isInteger(seconds) ||
    seconds < 1 ||
    seconds > limits.max_seconds ||
    !Number.isSafeInteger(bytes) ||
    bytes < 1024 ** 2 ||
    bytes > limits.max_bytes
  )
    return false
  return limits.available_max_bytes == null || bytes <= limits.available_max_bytes
}

export function readableBytes(bytes: number) {
  const unit = bytes >= 1024 ** 3 ? 'GiB' : 'MiB'
  return `${Number((bytes / (unit === 'GiB' ? 1024 ** 3 : 1024 ** 2)).toFixed(2))} ${unit}`
}
export function readableDuration(seconds: number) {
  if (seconds % 3600 === 0) return `${seconds / 3600}小时`
  if (seconds % 60 === 0) return `${seconds / 60}分钟`
  return `${seconds}秒`
}

export const minutesToSeconds = (minutes: number) => Math.round(minutes * 60)
export const gibToBytes = (gib: number) => Math.round(gib * 1024 ** 3)
