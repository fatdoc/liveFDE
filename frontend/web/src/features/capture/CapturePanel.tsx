import { useEffect, useRef, useState } from 'react'
import { ApiError, request, message } from '../../api/client'
import { RecordingLimits } from './RecordingLimits'
import { recordingChoiceValid } from './captureLimitPolicy'
import { Button, Badge } from '../../components/UI'
import type { LiveSession } from '../sessions/types'
import { isActive, runLabel, type CaptureHealth, type CaptureRun } from './types'
export function CapturePanel({
  session,
  csrf,
  scope,
  onImported,
}: {
  session: LiveSession
  csrf: string
  scope: string
  onImported: () => void
}) {
  const [health, setHealth] = useState<CaptureHealth | null>(null),
    [runs, setRuns] = useState<CaptureRun[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false)
  const [older, setOlder] = useState<CaptureRun[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [historyBusy, setHistoryBusy] = useState(false)
  const historyLock = useRef(false),
    paged = useRef(false),
    previousPage = useRef<CaptureRun[]>([])
  const [source, setSource] = useState(''),
    [retry, setRetry] = useState(0),
    [pending, setPending] = useState<{
      key: string
      source: string
      duration_seconds?: number
      max_bytes?: number
    } | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0),
    [maxBytes, setMaxBytes] = useState(0)
  const initializedLimits = useRef(false)
  const trackedActive = useRef(new Set<string>())
  const lock = useRef(false),
    knownMaterials = useRef(new Set<string>())
  const storageKey = `capture-attempt:${scope}:${session.id}`
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(storageKey)
      if (stored) {
        const value = JSON.parse(stored)
        setPending(value)
        setSource(value.source)
      }
    } catch {
      setError('本次提交记录无法恢复，请先刷新采集列表核对。')
    }
  }, [storageKey])
  useEffect(() => {
    const abort = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try {
        const [h, page] = await Promise.all([
          request<CaptureHealth>('/capture/health', { signal: abort.signal }),
          request<{ items: CaptureRun[]; next_cursor: string | null }>(
            `/capture/runs?session_id=${session.id}&limit=20`,
            { signal: abort.signal },
          ),
        ])
        if (abort.signal.aborted) return
        setHealth(h)
        if (!initializedLimits.current && h.limits) {
          setDurationSeconds(h.limits.default_duration_seconds ?? h.limits.max_seconds)
          setMaxBytes(h.limits.default_max_bytes ?? h.limits.max_bytes)
          initializedLimits.current = true
        }
        const ids = new Set(page.items.map((r) => r.capture_run_id))
        const tracked = await Promise.all(
          [...trackedActive.current]
            .filter((id) => !ids.has(id))
            .map((id) => request<CaptureRun>(`/capture/runs/${id}`, { signal: abort.signal })),
        )
        if (abort.signal.aborted) return
        if (tracked.length)
          setOlder((old) => [
            ...new Map([...old, ...tracked].map((r) => [r.capture_run_id, r])).values(),
          ])
        for (const run of [...page.items, ...tracked]) {
          if (isActive(run)) trackedActive.current.add(run.capture_run_id)
          else trackedActive.current.delete(run.capture_run_id)
        }
        const displaced = previousPage.current.filter((r) => !ids.has(r.capture_run_id))
        if (displaced.length)
          setOlder((old) => [
            ...new Map([...displaced, ...old].map((r) => [r.capture_run_id, r])).values(),
          ])
        previousPage.current = page.items
        setRuns(page.items)
        if (!paged.current) setCursor(page.next_cursor)
        setLoaded(true)
        for (const r of [...page.items, ...tracked])
          if (r.material_id && !knownMaterials.current.has(r.material_id)) {
            knownMaterials.current.add(r.material_id)
            onImported()
          }
        timer = setTimeout(refresh, 2500)
      } catch (e) {
        if (!abort.signal.aborted) {
          setError(message(e))
          setLoaded(false)
        }
      }
    }
    void refresh()
    return () => {
      abort.abort()
      clearTimeout(timer)
    }
  }, [session.id, retry])
  async function loadOlder() {
    if (!cursor || historyLock.current) return
    historyLock.current = true
    setHistoryBusy(true)
    try {
      const page = await request<{ items: CaptureRun[]; next_cursor: string | null }>(
        `/capture/runs?session_id=${session.id}&limit=20&cursor=${encodeURIComponent(cursor)}`,
      )
      setOlder((old) => [
        ...new Map([...old, ...page.items].map((r) => [r.capture_run_id, r])).values(),
      ])
      for (const run of page.items) if (isActive(run)) trackedActive.current.add(run.capture_run_id)
      paged.current = true
      setCursor(page.next_cursor)
    } catch (e) {
      setError(message(e))
    } finally {
      historyLock.current = false
      setHistoryBusy(false)
    }
  }
  const allRuns = [...new Map([...older, ...runs].map((r) => [r.capture_run_id, r])).values()]
  const currentRuns = allRuns.some(isActive) ? allRuns.filter(isActive) : runs.slice(0, 1)
  const currentIds = new Set(currentRuns.map((r) => r.capture_run_id))
  const historyRuns = [...runs, ...older].filter(
    (r, i, items) =>
      !currentIds.has(r.capture_run_id) &&
      items.findIndex((x) => x.capture_run_id === r.capture_run_id) === i,
  )
  const platform = session.platform,
    active = allRuns.some(isActive)
  const provider = health?.providers[platform]
  const ready =
    loaded &&
    health?.enabled &&
    health.ffmpeg_ready &&
    health.ffprobe_ready &&
    health.execution?.ready === true &&
    health.execution.automatic_dispatch &&
    provider?.start_ready === true
  const validSource =
    platform === 'wechat' || /^https:\/\/live\.douyin\.com\/\d+\/?$/.test(source.trim())
  async function start() {
    if (
      lock.current ||
      !health?.enabled ||
      (!ready && !pending) ||
      (active && !pending) ||
      !validSource ||
      (!pending && !recordingChoiceValid(health?.limits, durationSeconds, maxBytes))
    )
      return
    lock.current = true
    setBusy(true)
    setError('')
    const attempt = pending ?? {
      key: crypto.randomUUID(),
      source: platform === 'wechat' ? 'phone_cast' : source.trim(),
      duration_seconds: durationSeconds,
      max_bytes: maxBytes,
    }
    setPending(attempt)
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(attempt))
      const run = await request<CaptureRun>(
        '/capture/runs',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': attempt.key },
          body: JSON.stringify({
            session_id: session.id,
            platform,
            source_ref: attempt.source,
            ...(attempt.duration_seconds === undefined
              ? {}
              : { duration_seconds: attempt.duration_seconds }),
            ...(attempt.max_bytes === undefined ? {} : { max_bytes: attempt.max_bytes }),
          }),
        },
        csrf,
      )
      setRuns((old) => [run, ...old.filter((r) => r.capture_run_id !== run.capture_run_id)])
      sessionStorage.removeItem(storageKey)
      setPending(null)
      setRetry((x) => x + 1)
    } catch (e) {
      // A 4xx is an explicit rejection. Unknown network/5xx results keep the
      // exact request and key so a retry can recover an already-created run.
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        sessionStorage.removeItem(storageKey)
        setPending(null)
      }
      setError(message(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  async function act(run: CaptureRun, action: 'stop' | 'import') {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      await request(`/capture/runs/${run.capture_run_id}/${action}`, { method: 'POST' }, csrf)
      setRetry((x) => x + 1)
    } catch (e) {
      setError(message(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  function renderRun(run: CaptureRun) {
    return (
      <article className="asr-section" key={run.capture_run_id}>
        <Badge tone={run.error_code ? 'amber' : 'teal'}>{runLabel(run)}</Badge>
        <p>
          <small>采集编号 {run.capture_run_id}</small>
        </p>
        {run.recording_limits && (
          <p className="muted">
            本次上限 {run.recording_limits.max_seconds} 秒 / {run.recording_limits.max_bytes} 字节
          </p>
        )}
        {(run.recorded_bytes != null || run.elapsed_seconds != null) && (
          <p className="muted">
            已封装材料：{run.elapsed_seconds ?? '未提供'} 秒 · {run.recorded_bytes ?? '未提供'} 字节
          </p>
        )}
        {run.error_code && (
          <details>
            <summary>失败详情</summary>
            <p className="asr-error">采集未完成：{run.error_code}</p>
          </details>
        )}
        {isActive(run) && (
          <Button disabled={busy || run.stop_requested} onClick={() => act(run, 'stop')}>
            {run.stop_requested ? '等待服务器停止' : '停止录制'}
          </Button>
        )}
        {!isActive(run) && !!run.manifest && !run.material_id && (
          <Button disabled={busy} onClick={() => act(run, 'import')}>
            重新导入录制材料
          </Button>
        )}
      </article>
    )
  }
  if (platform === 'other')
    return (
      <section className="asr-section">
        <h2>直播采集</h2>
        <p>当前支持抖音与微信视频号场次。</p>
      </section>
    )
  return (
    <section className="asr-section">
      <h2>直播采集</h2>
      <p className="muted">录制完成后进入场次材料。转写需要你手动开始。</p>
      {ready && (
        <p className="muted">
          配置已就绪，可测试录制；真实直播源尚待验证。
          {health?.limits &&
            ` 单次最多 ${health.limits.max_seconds} 秒 / ${Math.round(health.limits.max_bytes / 1000000)} MB。`}
        </p>
      )}
      {!ready && (
        <p className="asr-warning">
          {!loaded
            ? '正在读取采集服务状态；未确认就绪前无法启动。'
            : !health?.enabled
              ? '采集服务尚未启用。'
              : provider?.blockers?.length
                ? provider.blockers.map((item) => item.message).join(' ')
                : '未收到平台就绪信息，请刷新状态或等待服务更新。'}
        </p>
      )}
      {platform === 'douyin' ? (
        <label className="field">
          抖音电脑端直播间链接
          <input
            value={source}
            disabled={busy || active || !!pending}
            placeholder="https://live.douyin.com/数字房间号"
            onChange={(e) => setSource(e.target.value)}
          />
        </label>
      ) : (
        <div className="callout" style={{ display: 'block' }}>
          <strong>手机投屏录制</strong>
          <ol>
            <li>手机与采集电脑连接同一局域网。</li>
            <li>点击开始等待投屏，再打开微信视频号直播。</li>
            <li>
              在直播的投屏菜单选择接收设备「{provider?.device_name || '等待服务返回设备名称'}」。
            </li>
          </ol>
          <p>若直播没有投屏入口，本次无法采集。无需粘贴临时播放地址。</p>
        </div>
      )}
      <RecordingLimits
        limits={health?.limits}
        duration={durationSeconds}
        bytes={maxBytes}
        disabled={busy || active || !!pending}
        onDuration={setDurationSeconds}
        onBytes={setMaxBytes}
      />
      {pending && (
        <p className="asr-warning">
          上一次提交尚待确认。重试将查询同一次请求，不创建新的录制；请保留当前直播间。
        </p>
      )}
      <div className="actions">
        <Button
          primary
          disabled={
            !health?.enabled ||
            (!ready && !pending) ||
            !loaded ||
            (active && !pending) ||
            busy ||
            !validSource ||
            (!pending && !recordingChoiceValid(health?.limits, durationSeconds, maxBytes))
          }
          onClick={start}
        >
          {busy
            ? '正在处理…'
            : pending
              ? '重试确认同次采集'
              : platform === 'wechat'
                ? '开始等待投屏'
                : '开始录制'}
        </Button>
        <Button disabled={busy} onClick={() => setRetry((x) => x + 1)}>
          刷新状态
        </Button>
      </div>
      {error && (
        <p role="alert" className="asr-error">
          {error}
        </p>
      )}
      <div aria-live="polite">
        {currentRuns.map(renderRun)}
        <details>
          <summary>历史采集记录（当前已加载 {historyRuns.length} 条）</summary>
          <p className="muted">历史失败仅收起，不删除记录；可继续读取更早记录。</p>
          {historyRuns.map(renderRun)}
          {cursor && (
            <Button disabled={historyBusy} onClick={loadOlder}>
              {historyBusy ? '正在加载…' : '加载更早记录'}
            </Button>
          )}
        </details>
      </div>
    </section>
  )
}
