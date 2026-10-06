import type { CaptureLimits } from './types'
import { recordingChoiceValid } from './captureLimitPolicy'
export function RecordingLimits({
  limits,
  duration,
  bytes,
  disabled,
  onDuration,
  onBytes,
}: {
  limits: CaptureLimits | undefined
  duration: number
  bytes: number
  disabled: boolean
  onDuration: (n: number) => void
  onBytes: (n: number) => void
}) {
  if (!limits) return <p className="muted">等待服务器录制限制，暂不能启动。</p>
  return (
    <details>
      <summary>
        本次录制限制：{duration} 秒 / {(bytes / 1024 ** 3).toFixed(2)} GiB
      </summary>
      <fieldset className="asr-fields" disabled={disabled}>
        <legend>录制停止条件</legend>
        <label className="field">
          时长预设
          <select
            aria-label="时长预设"
            value={limits.duration_presets_seconds?.includes(duration) ? duration : ''}
            onChange={(e) => {
              if (e.target.value) onDuration(Number(e.target.value))
            }}
          >
            <option value="">自定义秒数</option>
            {limits.duration_presets_seconds
              ?.filter((n) => n <= limits.max_seconds)
              .map((n) => (
                <option value={n} key={n}>
                  {n / 60} 分钟
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          最大录制秒数
          <input
            type="number"
            min={1}
            max={limits.max_seconds}
            step={1}
            value={duration}
            onChange={(e) => onDuration(Number(e.target.value))}
          />
        </label>
        <label className="field">
          文件停止阈值（字节）
          <input
            type="number"
            min={1}
            max={Math.min(limits.max_bytes, limits.available_max_bytes ?? limits.max_bytes)}
            step={1}
            value={bytes}
            onChange={(e) => onBytes(Number(e.target.value))}
          />
        </label>
      </fieldset>
      <p className="muted">
        服务端最多 {limits.max_seconds} 秒 / {limits.max_bytes}{' '}
        字节。先达到时长、文件阈值或手动停止条件即结束。最终封装可多出最多{' '}
        {limits.size_overrun_bytes ?? 0} 字节。
      </p>
      <p className="muted">
        当前可用录制预算：{limits.available_max_bytes ?? '未取得'}{' '}
        字节；空间可能被其他任务占用，启动时仍由服务器检查。录制与导入需预留多个文件副本。
      </p>
      <p className="muted">
        本轮为单文件录制，不支持断点恢复；录制完成不自动转写。手动上传上限{' '}
        {limits.manual_upload_max_bytes ?? '未提供'} 字节，与录制上限不同。
      </p>
      {!recordingChoiceValid(limits, duration, bytes) && (
        <p className="asr-warning">
          请选择服务端允许范围内的正整数时长和文件阈值，并确保不超过当前可用空间预算。
        </p>
      )}
    </details>
  )
}
