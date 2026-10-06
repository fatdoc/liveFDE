import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, message, request } from '../../api/client'
import { Button, Badge } from '../../components/UI'
import type { ASRSettings, Job, Transcription } from '../asr/types'
export function MaterialTranscription({
  materialId,
  csrf,
  scope,
}: {
  materialId: string
  csrf: string
  scope: string
}) {
  const [settings, setSettings] = useState<ASRSettings | null>(null),
    [data, setData] = useState<Transcription | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [jobId, setJobId] = useState(''),
    [query, setQuery] = useState(0),
    [uncertain, setUncertain] = useState(false)
  const lock = useRef(false),
    storageKey = `material-asr:${scope}:${materialId}`
  const active = !!data && ['queued', 'running', 'cancel_requested'].includes(data.job.status)
  useEffect(() => {
    const a = new AbortController()
    request<ASRSettings>('/asr/settings', { signal: a.signal })
      .then(setSettings)
      .catch((e) => {
        if (!a.signal.aborted) setError(message(e))
      })
    const saved = sessionStorage.getItem(storageKey)
    if (saved === 'unknown') setUncertain(true)
    else if (saved) setJobId(saved)
    return () => a.abort()
  }, [materialId])
  useEffect(() => {
    if (!jobId || !/^[a-zA-Z0-9_-]{1,100}$/.test(jobId)) return
    const a = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const r = await request<Transcription>(`/asr/transcriptions/${jobId}`, { signal: a.signal })
        if (a.signal.aborted) return
        setData(r)
        if (['queued', 'running', 'cancel_requested'].includes(r.job.status))
          timer = setTimeout(poll, 1800)
      } catch (e) {
        if (!a.signal.aborted) setError(message(e))
      }
    }
    void poll()
    return () => {
      a.abort()
      clearTimeout(timer)
    }
  }, [jobId, query])
  async function start() {
    if (
      lock.current ||
      !settings ||
      settings.provider !== 'local' ||
      !settings.revision ||
      uncertain
    )
      return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      sessionStorage.setItem(storageKey, 'unknown')
      setUncertain(true)
      const job = await request<Job>(
        '/asr/transcriptions',
        {
          method: 'POST',
          body: JSON.stringify({
            material_id: materialId,
            expected_revision: settings.revision,
            allow_network: false,
          }),
        },
        csrf,
      )
      sessionStorage.setItem(storageKey, job.id)
      setUncertain(false)
      setData({ job, result: null })
      setJobId(job.id)
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) {
        sessionStorage.removeItem(storageKey)
        setUncertain(false)
      }
      setError(message(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <div className="asr-section">
      <h3>本地转写</h3>
      <p className="muted">直接使用这份材料，不再次上传，不调用云端服务。</p>
      {(!settings?.revision || settings.provider !== 'local') && (
        <p>
          请先在
          <Link className="text-link" to="/settings">
            设置
          </Link>
          中保存本地转写配置。
        </p>
      )}
      <Button
        disabled={
          busy ||
          active ||
          !!data ||
          uncertain ||
          !settings?.revision ||
          settings.provider !== 'local'
        }
        onClick={start}
      >
        {busy ? '正在提交…' : '手动开始本地转写'}
      </Button>
      {uncertain && (
        <p className="asr-warning">
          提交结果尚未确认，已阻止重复提交。请核查服务器任务，取得任务编号后恢复查询。
        </p>
      )}
      <label className="field">
        恢复查询任务编号
        <input value={jobId} disabled={active} onChange={(e) => setJobId(e.target.value.trim())} />
      </label>
      <Button disabled={!jobId} onClick={() => setQuery((x) => x + 1)}>
        查询任务
      </Button>
      {error && (
        <p role="alert" className="asr-error">
          {error}
        </p>
      )}
      {data && (
        <div aria-live="polite">
          <Badge>
            {
              {
                queued: '等待转写',
                running: '正在转写',
                succeeded: '转写完成',
                failed: '转写失败',
                canceled: '已取消',
                cancel_requested: '等待取消',
              }[data.job.status]
            }
          </Badge>
          {data.job.error && <p role="alert">{data.job.error.code}</p>}
          {data.result && (
            <>
              <p>
                {data.result.synthetic
                  ? '合成测试结果，非真实听写。'
                  : data.result.complete
                    ? '完整转写结果'
                    : '部分转写结果'}
              </p>
              {data.result.segments.map((s) => (
                <p key={s.id}>
                  <small>
                    {s.start_ms === null ? '时间未知' : `${(s.start_ms / 1000).toFixed(1)} 秒`}
                  </small>
                  <br />
                  {s.text}
                </p>
              ))}
              {!data.result.segments.length && <p>{data.result.text}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
