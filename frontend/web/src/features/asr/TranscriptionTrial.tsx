import {useEffect, useState} from 'react'
import {Button, Badge} from '../../components/UI'
import {ApiError, message, request} from '../../api/client'
import type {ASRSettings, Job, Transcription} from './types'
const labels: Record<Job['status'], string> = {queued: '等待处理', running: '正在转写', succeeded: '处理完成', failed: '处理失败', cancel_requested: '等待取消', canceled: '已取消'}
const warningGuidance: Record<string, string> = {
  timestamps_are_vad_or_vad_window_boundaries_not_word_alignment: '时间戳表示语音检测区间或切分窗口的边界，不是逐字对齐时间。',
  model_confidence_unavailable: '当前模型未提供置信度，不能据此显示准确率。',
  nano_native_punctuation: 'Nano会生成原生标点；启用标点恢复时还会进一步处理。',
  'bounded_window_asr_not_token_realtime;window_edges_may_split_words': '当前结果按固定时间窗口增量生成，不是逐词实时识别；窗口边界可能切开词句。',
}
const running = (job: Job) => ['queued', 'running', 'cancel_requested'].includes(job.status)
const time = (ms: number | null) => ms === null ? '时间未知' : `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`
export function TranscriptionTrial({settings, csrf, expired, dirty}: {settings: ASRSettings; csrf: string; expired: () => void; dirty: boolean}) {
  const [file, setFile] = useState<File | null>(null), [busy, setBusy] = useState(false), [phase, setPhase] = useState('')
  const [error, setError] = useState(''), [result, setResult] = useState<Transcription | null>(null), [polling, setPolling] = useState(false)
  const [resumeId, setResumeId] = useState(''), [uncertain, setUncertain] = useState(false)
  const [grant, setGrant] = useState(false), [requests, setRequests] = useState('1'), [cost, setCost] = useState('')
  const cloudPossible = settings.privacy === 'cloud_allowed' && (settings.provider === 'tencent' || settings.allow_cloud_fallback)
  const needsCloud = settings.provider === 'tencent'
  const validBudget = Number.isInteger(Number(requests)) && Number(requests) > 0 && Number(requests) <= 10 && Number.isFinite(Number(cost)) && Number(cost) > 0 && Number(cost) <= 100
  const active = !!result && running(result.job)
  useEffect(() => {setGrant(false)}, [settings.revision])
  useEffect(() => {
    if (!polling || !result) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {const next = await request<Transcription>(`/asr/transcriptions/${result.job.id}`, {signal: controller.signal}); setResult(next); if (!running(next.job)) setPolling(false)}
      catch (e) {if (!controller.signal.aborted) {setPolling(false); setError(message(e)); if (e instanceof ApiError && e.status === 401) expired()}}
    }, 1500)
    return () => {clearTimeout(timer); controller.abort()}
  }, [polling, result])
  async function start() {
    if (settings.revision === 0 || uncertain || !file || dirty || (needsCloud && !grant) || (grant && !validBudget)) return
    setBusy(true); setError(''); setResult(null); setPolling(false)
    const authorized = grant && cloudPossible
    setGrant(false)
    let submitted = false
    try {
      const ext = file.name.split('.').pop()?.toLowerCase()
      const mediaType = ext === 'mp4' ? 'video/mp4' : ext === 'mp3' ? 'audio/mpeg' : ext === 'wav' ? 'audio/wav' : ext === 'm4a' ? 'audio/mp4' : ext === 'aac' ? 'audio/aac' : null
      if (!mediaType) throw new Error('请选择 MP4、WAV、MP3、M4A 或 AAC 文件。')
      if (file.size === 0 || file.size > 512 * 1024 * 1024) throw new Error('文件必须大于 0，且不超过 512 MiB。')
      setPhase('正在登记文件…')
      const upload = await request<{upload_id: string; max_bytes: number}>('/materials/uploads', {method: 'POST', headers: {'Idempotency-Key': crypto.randomUUID()}, body: JSON.stringify({filename: file.name, byte_size: file.size, media_type: mediaType, purpose: 'session_media'})}, csrf)
      if (file.size > upload.max_bytes) throw new Error('文件超出当前服务器上传限制。')
      setPhase('正在上传文件…')
      await request(`/materials/uploads/${upload.upload_id}/content`, {method: 'PUT', headers: {'Content-Type': 'application/octet-stream'}, body: file}, csrf)
      setPhase('正在校验材料…')
      const material = await request<{material_id: string}>(`/materials/uploads/${upload.upload_id}/finalize`, {method: 'POST'}, csrf)
      setPhase('正在提交转写任务…')
      submitted = true
      const job = await request<Job>('/asr/transcriptions', {method: 'POST', body: JSON.stringify({material_id: material.material_id, expected_revision: settings.revision, allow_network: authorized, max_requests: authorized ? Number(requests) : null, max_cost_usd: authorized ? Number(cost) : null})}, csrf)
      setResult({job, result: null}); setResumeId(job.id); setPolling(true)
    } catch (e) {if (submitted && (!(e instanceof ApiError) || e.status >= 500)) setUncertain(true); setError(message(e)); if (e instanceof ApiError && e.status === 401) expired()} finally {setBusy(false); setPhase('')}
  }
  async function resume() {
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(resumeId.trim())) {setError('请输入有效的任务编号。'); return}
    setBusy(true); setError(''); setPolling(false)
    try {const data = await request<Transcription>(`/asr/transcriptions/${resumeId.trim()}`); setResult(data); setPolling(running(data.job))}
    catch (e) {setError(message(e)); if (e instanceof ApiError && e.status === 401) expired()} finally {setBusy(false)}
  }
  return <section className="asr-section"><h3>试用转写</h3><p className="muted">使用已保存的设置上传到本系统服务器。仅本地处理时不会发送给云服务。离开此页或退出登录不会取消服务器任务，请保留任务编号。</p>
    {settings.revision === 0 ? <p className="asr-warning">尚未保存工作区设置，请先保存一次，再开始试用。</p> : dirty && <p className="asr-warning">请先保存或放弃设置草稿，再开始试用。</p>}
    <label className="field">选择音频或视频<input type="file" accept=".mp4,.wav,.mp3,.m4a,.aac,video/mp4,audio/wav,audio/mpeg,audio/mp4,audio/aac" disabled={busy || active} onChange={e => {setFile(e.target.files?.[0] ?? null); setError(''); setGrant(false)}}/></label>
    {cloudPossible && <p className="asr-warning">当前腾讯云文件转写仅支持规范化后的 WAV 不超过 5 MB（16 kHz、单声道、16 位时约 156 秒）。限制针对转换后的音频，不是原 MP3/M4A/视频文件大小；长录音云端转写尚未接入，请使用本地服务。</p>}
    {cloudPossible && <fieldset className="asr-cloud" disabled={busy || active}><legend>本次云端授权</legend><label className="asr-option"><input type="checkbox" checked={grant} onChange={e => setGrant(e.target.checked)}/><span>我授权本次任务将音频发送给腾讯云，并接受服务费用<small>授权仅用于这一次提交；切换服务或保存设置不代表授权。</small></span></label>{grant && <div className="asr-budget"><label className="field">最多请求次数<input type="number" min="1" max="10" step="1" value={requests} onChange={e => setRequests(e.target.value)}/></label><label className="field">金额预算（美元）<input type="number" min="0.01" max="100" step="0.01" value={cost} onChange={e => setCost(e.target.value)}/></label><small>金额为授权声明，系统尚未核算供应商实际账单。</small></div>}</fieldset>}
    {settings.allow_cloud_fallback && !grant && <p className="muted">本次未授权云端，本地失败不会自动转云端。</p>}
    <Button primary disabled={settings.revision === 0 || uncertain || !file || dirty || busy || active || (needsCloud && !grant) || (grant && !validBudget)} onClick={start}>{busy ? phase : '上传并开始本次转写'}</Button>
    {uncertain && <div className="asr-warning" role="alert"><p>转写提交结果未知，服务器可能已创建任务。请由管理员核查任务记录；再次提交可能重复计费。</p><Button onClick={() => {setUncertain(false); setGrant(false)}}>我已核查，允许重新提交</Button></div>}
    <div className="asr-actions"><label className="field">恢复查询任务编号<input value={resumeId} disabled={busy || active} onChange={e => setResumeId(e.target.value)}/></label><Button disabled={busy || active || !resumeId.trim()} onClick={resume}>查询已有任务</Button></div>
    {error && <p className="asr-error" role="alert">{error}</p>}
    {result && <div className="asr-result" aria-live="polite"><div className="asr-section-heading"><Badge tone={result.job.status === 'failed' ? 'amber' : 'teal'}>{labels[result.job.status]}</Badge>{active && !polling && <Button onClick={() => {setError(''); setPolling(true)}}>继续查询任务</Button>}</div><small>任务 {result.job.id}</small>{active && <p>{polling ? '自动更新任务状态…' : '查询已暂停，服务器任务可能仍在运行。'}</p>}<ul>{result.job.steps.map(step => <li key={step.stage}>{step.stage} · {step.status}{step.reason ? ` · ${step.reason}` : ''}</li>)}</ul>
      {result.job.error && <p className="asr-error" role="alert">任务失败：{result.job.error.code}。没有自动重试。</p>}
      {result.result ? <><p>{result.result.source === 'local' ? '本地处理' : '云端处理'} · {result.result.provider} · {result.result.model} · {result.result.complete ? '完整结果' : '部分结果'}{result.result.synthetic ? ' · 合成测试，非真实听写' : ''}</p>{result.result.warnings.map((warning, index) => <p className="asr-warning" key={index}>{warningGuidance[warning] || '识别服务返回了附加提示，请结合状态码核对结果。'}<br/><small>状态码：{warning}</small></p>)}<div className="asr-transcript">{!result.result.segments.length && result.result.text && <p>{result.result.text}</p>}{result.result.segments.map(segment => <article key={segment.id}><small>{time(segment.start_ms)} — {time(segment.end_ms)} · {segment.speaker_id ? `匿名说话人 ${segment.speaker_id}` : '说话人未知'} · {segment.emotion ?? '情绪未知'}</small><p>{segment.text}</p></article>)}</div></> : !active && <p className="muted">未返回转写结果。</p>}
    </div>}
  </section>
}
