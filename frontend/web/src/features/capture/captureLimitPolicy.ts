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
    bytes < 1 ||
    bytes > limits.max_bytes
  )
    return false
  return limits.available_max_bytes == null || bytes <= limits.available_max_bytes
}
