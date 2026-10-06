import { useEffect, useRef, useState } from 'react'
import { AdminSession, type Session } from '../../auth/AdminSession'
import { ApiError, request } from '../../api/client'
import { Badge, Button, Modal } from '../../components/UI'
import {
  platformError,
  platformStatus,
  validDouyinSource,
  type DouyinSettings,
} from './platformSettings'
import '../asr/asr.css'
const endpoint = '/capture/settings/douyin'
export function PlatformSettingsPanel() {
  return (
    <AdminSession>
      {(session, expired) => <Editor key={session.user.id} session={session} expired={expired} />}
    </AdminSession>
  )
}
function Editor({ session, expired }: { session: Session; expired: () => void }) {
  const [saved, setSaved] = useState<DouyinSettings | null>(null),
    [cookie, setCookie] = useState(''),
    [source, setSource] = useState('')
  const [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [clearOpen, setClearOpen] = useState(false)
  const lock = useRef(false),
    controller = useRef<AbortController | null>(null)
  useEffect(() => {
    void load()
    return () => {
      controller.current?.abort()
      lock.current = false
    }
  }, [])
  function fail(e: unknown) {
    if (e instanceof ApiError) {
      if (e.status === 401) {
        setCookie('')
        expired()
        return
      }
      if (e.status === 409) {
        setBlocked(true)
        setError('设置版本已变化或另一次检查正在进行。请刷新状态，核对后再操作。')
        return
      }
      if (e.status === 403) {
        setError('没有操作权限或会话校验失败，请重新登录。')
        return
      }
      if (e.status === 503 && ['provider_dependencies_missing', 'platform_storage_unavailable'].includes(e.code)) {
        setBlocked(true)
        setError(platformError(e.code) + ' 请刷新状态后再操作。')
        return
      }
      if (e.status < 500) {
        setError(platformError(e.code))
        return
      }
    }
    setBlocked(true)
    setError('请求结果尚未确认。请刷新当前状态后再操作；系统不会自动重试。')
  }
  async function load() {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    setNotice('')
    const abort = new AbortController()
    controller.current = abort
    try {
      const data = await request<DouyinSettings>(endpoint, { signal: abort.signal })
      if (!abort.signal.aborted) {
        setSaved(data)
        setBlocked(false)
      }
    } catch (e) {
      if (!abort.signal.aborted) {
        setBlocked(true)
        fail(e)
      }
    } finally {
      if (!abort.signal.aborted) {
        lock.current = false
        setBusy(false)
      }
    }
  }
  async function mutate(kind: 'save' | 'clear' | 'check') {
    if (lock.current || blocked || !saved) return
    if (kind === 'save' && !cookie.trim()) return
    if (
      kind === 'check' &&
      (!saved.configured || !saved.service_ready || cookie || !validDouyinSource(source))
    )
      return
    lock.current = true
    setBusy(true)
    setError('')
    setNotice('')
    const abort = new AbortController()
    controller.current = abort
    try {
      const body =
        kind === 'save'
          ? { cookie, expected_revision: saved.revision }
          : kind === 'check'
            ? { source_ref: source.trim(), expected_revision: saved.revision }
            : { expected_revision: saved.revision }
      const result = await request<DouyinSettings>(
        kind === 'check' ? `${endpoint}/check` : endpoint,
        {
          method: kind === 'save' ? 'PUT' : kind === 'clear' ? 'DELETE' : 'POST',
          body: JSON.stringify(body),
          signal: abort.signal,
        },
        session.csrf_token,
      )
      if (abort.signal.aborted) return
      setSaved(result)
      if (kind !== 'check') {
        setCookie('')
        setClearOpen(false)
      }
      setNotice(
        kind === 'save'
          ? '已保存。输入框已清空，尚未验证平台连接。'
          : kind === 'clear'
            ? '已清除当前工作区的 Cookie。'
            : result.status === 'verified'
              ? '当次解析成功；未启动录制。'
              : '检查已结束，未启动录制。请查看下方状态。',
      )
    } catch (e) {
      if (!abort.signal.aborted) fail(e)
    } finally {
      if (!abort.signal.aborted) {
        lock.current = false
        setBusy(false)
      }
    }
  }
  return (
    <section>
      <div className="asr-section-heading">
        <h2>抖音接入</h2>
        <Button disabled={busy} onClick={load}>
          刷新状态
        </Button>
      </div>
      <p className="muted">管理员为当前工作区保存抖音 Cookie，供直播间解析使用。</p>
      {error && (
        <p className="asr-error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!saved ? (
        <p>{busy ? '正在读取平台设置…' : '尚未读取到设置。'}</p>
      ) : (
        <>
          <div className="setting-row">
            <div>
              <h3>采集服务</h3>
              <p className="muted">服务就绪不代表 Cookie 有效或直播可录制。</p>
            </div>
            <Badge tone={saved.service_ready ? 'teal' : 'amber'}>
              {saved.service_ready ? '服务就绪' : '服务未就绪'}
            </Badge>
          </div>
          <div className="setting-row">
            <div>
              <h3>Cookie</h3>
              <p className="muted">仅显示保存状态，不回显已保存内容。</p>
            </div>
            <Badge>{saved.configured ? '已保存' : '未保存'}</Badge>
          </div>
          <div className="setting-row">
            <div>
              <h3>连接检查</h3>
              <p className="muted">仅验证当次直播间解析，不创建采集任务。</p>
            </div>
            <Badge tone={saved.status === 'verified' ? 'teal' : 'amber'}>
              {platformStatus[saved.status]}
            </Badge>
          </div>
          {saved.checked_at && (
            <p className="muted">
              最近检查：{new Date(saved.checked_at).toLocaleString('zh-CN')}
              <br />
              直播间：{saved.checked_source ?? '未记录'}
              <br />
              {saved.checked_state === 'live'
                ? '当次解析：正在直播。'
                : saved.checked_state === 'not_live'
                  ? '当次解析：尚未开播，仍属于解析成功。'
                  : '本次未确认开播状态。'}
            </p>
          )}
          {saved.last_error && <p className="asr-warning">{platformError(saved.last_error)}</p>}
          <label className="field">
            {saved.configured ? '新的抖音 Cookie' : '抖音 Cookie'}
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={cookie}
              disabled={busy}
              onChange={(e) => setCookie(e.target.value)}
              placeholder="粘贴完整 Cookie；保存后清空"
            />
          </label>
          <p className="muted">
            仅保存在服务器工作区私密文件中，由操作系统权限保护；不宣称加密。本系统不将输入内容保存到浏览器存储。
          </p>
          <div className="actions">
            <Button
              primary
              disabled={busy || blocked || !cookie.trim()}
              onClick={() => mutate('save')}
            >
              {busy ? '正在处理…' : saved.configured ? '更新 Cookie' : '保存 Cookie'}
            </Button>
            <Button
              disabled={busy || blocked || !saved.configured}
              onClick={() => setClearOpen(true)}
            >
              清除 Cookie
            </Button>
          </div>
          <section className="asr-section">
            <h3>检查直播间连接</h3>
            <label className="field">
              抖音电脑端直播间链接
              <input
                value={source}
                disabled={busy}
                onChange={(e) => setSource(e.target.value)}
                placeholder="https://live.douyin.com/数字房间号"
              />
            </label>
            {cookie && (
              <p className="asr-warning">请先保存或清空 Cookie 输入，再检查服务器已保存的版本。</p>
            )}
            <Button
              disabled={
                busy ||
                blocked ||
                !saved.configured ||
                !saved.service_ready ||
                !!cookie ||
                !validDouyinSource(source)
              }
              onClick={() => mutate('check')}
            >
              仅检查连接
            </Button>
            <p className="muted">只发送一次解析请求，不录制、不转写，也不会自动重试。</p>
          </section>
          <p className="callout">
            排队但尚未开始解析的任务使用最新
            Cookie；已经开始的任务继续使用启动时的版本，直到结束。清除或更新不会中断正在进行的录制。
          </p>
        </>
      )}
      <Modal
        open={clearOpen}
        onOpenChange={(v) => {
          if (!busy) setClearOpen(v)
        }}
        title="清除抖音 Cookie？"
        description="清除当前工作区已保存的 Cookie，后续新解析需重新配置。正在进行的任务保持原版本。"
      >
        <Button disabled={busy} onClick={() => setClearOpen(false)}>
          保留
        </Button>
        <Button primary disabled={busy || blocked} onClick={() => mutate('clear')}>
          确认清除 Cookie
        </Button>
      </Modal>
    </section>
  )
}
