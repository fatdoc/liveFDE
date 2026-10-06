import type { CaptureLimits } from './types'
import { recordingChoiceValid, readableBytes, readableDuration, minutesToSeconds, gibToBytes } from './captureLimitPolicy'
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
        本次录制限制：{readableDuration(duration)} / {readableBytes(bytes)}
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
            <option value="">自定义分钟</option>
            {limits.duration_presets_seconds
              ?.filter((n) => n <= limits.max_seconds)
              .map((n) => (
                <option value={n} key={n}>
                  {readableDuration(n)}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          最长录制时间（分钟）
          <input
            type="number"
            min={1 / 60}
            max={limits.max_seconds / 60}
            step="any"
            value={duration / 60}
            onChange={(e) => onDuration(minutesToSeconds(Number(e.target.value)))}
          />
        </label>
        <label className="field">
          文件容量上限（GiB）
          <input
            type="number"
            min={1 / 1024}
            max={Math.min(limits.max_bytes, limits.available_max_bytes ?? limits.max_bytes) / 1024 ** 3}
            step="any"
            value={bytes / 1024 ** 3}
            onChange={(e) => onBytes(gibToBytes(Number(e.target.value)))}
          />
        </label>
      </fieldset>
      <p className="muted">系统预留导入空间；到时、到容量或手动停止即结束。不支持断点恢复。</p>
      <p className="muted">服务端最多 {readableDuration(limits.max_seconds)} / {readableBytes(limits.max_bytes)}；当前可用预算 {limits.available_max_bytes == null ? '未取得' : readableBytes(limits.available_max_bytes)}。</p>
      <details><summary>高级说明</summary>
        <p className="muted">分钟按最近的整秒换算，容量按最近的整字节保存，最小 1 MiB（0.0009765625 GiB）。</p>
        <p className="muted">最终封装可多出最多 {readableBytes(limits.size_overrun_bytes ?? 0)}。空间可能被其他任务占用，启动时仍由服务器检查；录制与导入需要多个文件副本。</p>
        <p className="muted">本轮为单文件录制，完成后不自动转写。手动上传上限 {limits.manual_upload_max_bytes == null ? '未提供' : readableBytes(limits.manual_upload_max_bytes)}，与录制上限不同。</p>
      </details>
      {!recordingChoiceValid(limits, duration, bytes) && (
        <p className="asr-warning">
          请选择服务端允许范围内的时长，文件阈值至少 1 MiB，并确保不超过当前可用空间预算。
        </p>
      )}
    </details>
  )
}
