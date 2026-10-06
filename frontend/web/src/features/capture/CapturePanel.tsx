import { useEffect, useRef, useState } from 'react'
import { request, message } from '../../api/client'
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
  const [source, setSource] = useState(''),
    [retry, setRetry] = useState(0),
    [pending, setPending] = useState<{ key: string; source: string } | null>(null)
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
        setRuns(page.items)
        setLoaded(true)
        for (const r of page.items)
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
  const platform = session.platform,
    active = runs.some(isActive)
  const provider = health?.providers[platform]
  const ready =
    loaded &&
    health?.enabled &&
    health.ffmpeg_ready &&
    health.ffprobe_ready &&
    health.execution?.ready === true &&
    health.execution.automatic_dispatch &&
    provider?.dependencies_ready === true
  const validSource =
    platform === 'wechat' || /^https:\/\/live\.douyin\.com\/\d+\/?$/.test(source.trim())
  async function start() {
    if (
      lock.current ||
      !health?.enabled ||
      (!ready && !pending) ||
      (active && !pending) ||
      !validSource
    )
      return
    lock.current = true
    setBusy(true)
    setError('')
    const attempt = pending ?? {
      key: crypto.randomUUID(),
      source: platform === 'wechat' ? 'phone_cast' : source.trim(),
    }
    setPending(attempt)
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(attempt))
      const run = await request<CaptureRun>(
        '/capture/runs',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': attempt.key },
          body: JSON.stringify({ session_id: session.id, platform, source_ref: attempt.source }),
        },
        csrf,
      )
      setRuns((old) => [run, ...old.filter((r) => r.capture_run_id !== run.capture_run_id)])
      sessionStorage.removeItem(storageKey)
      setPending(null)
      setRetry((x) => x + 1)
    } catch (e) {
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
      {!ready && (
        <p className="asr-warning">
          {!loaded
            ? '正在读取采集服务状态；未确认就绪前无法启动。'
            : !health?.enabled
              ? '采集服务尚未启用。'
              : '采集执行环境尚未就绪，请等待配置完成。'}
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
            !validSource
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
        {runs.map((run) => (
          <article className="asr-section" key={run.capture_run_id}>
            <Badge tone={run.error_code ? 'amber' : 'teal'}>{runLabel(run)}</Badge>
            <p>
              <small>采集编号 {run.capture_run_id}</small>
            </p>
            {run.error_code && <p className="asr-error">采集未完成：{run.error_code}</p>}
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
        ))}
      </div>
    </section>
  )
}
