export type CaptureRun = {
  capture_run_id: string
  session_id: string
  platform: string
  source_ref: string
  state: string
  job_status: string
  stop_requested: boolean
  material_id: string | null
  import_status: string
  error_code: string | null
  recording_limits?: { max_seconds: number; max_bytes: number; min_free_bytes: number } | null
  recorded_bytes?: number | null
  elapsed_seconds?: number | null
  manifest: unknown
}
export type CaptureHealth = {
  enabled: boolean
  limits?: CaptureLimits
  ffmpeg_ready: boolean
  ffprobe_ready: boolean
  execution: { ready: boolean; automatic_dispatch: boolean; state: string; reason: string | null }
  providers: Record<
    string,
    {
      dependencies_ready?: boolean
      start_ready?: boolean
      blockers?: { code: string; message: string }[]
      device_name?: string
      reason?: string
      [key: string]: unknown
    }
  >
}
export const isActive = (run: CaptureRun) =>
  ['queued', 'running', 'cancel_requested'].includes(run.job_status)
export function runLabel(run: CaptureRun) {
  if (run.material_id) return '已导入材料'
  if (run.manifest && isActive(run)) return '录制完成，正在导入材料'
  if (run.stop_requested && isActive(run)) return '已请求停止，等待确认'
  if (run.import_status === 'importing' || run.state === 'importing') return '正在导入材料'
  return (
    (
      {
        queued: '等待采集',
        probing: '正在检查直播',
        url_received: '已接收投屏，正在连接',
        waiting: '等待开播',
        waiting_for_live: '等待开播',
        waiting_for_cast: '等待手机投屏',
        recording: '正在录制',
        stopped: '已停止',
        recorded: '录制完成',
        succeeded: '录制完成',
        failed: '采集失败',
        canceled: '已取消',
        completed: '录制完成',
      } as Record<string, string>
    )[run.state] ?? `采集状态：${run.state}`
  )
}

export type CaptureLimits = {
  max_seconds: number
  max_bytes: number
  duration_presets_seconds?: number[]
  default_duration_seconds?: number
  default_max_bytes?: number
  min_free_bytes?: number
  manual_upload_max_bytes?: number
  available_max_bytes?: number | null
  import_overhead_copies?: number
  fragmented_mp4?: boolean
  resumable_recording?: boolean
  size_overrun_bytes?: number
}
