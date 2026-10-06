import { useEffect, useRef, useState } from 'react'
import { AdminSession, type Session } from '../../auth/AdminSession'
import { ApiError, request } from '../../api/client'
import { Button, Badge } from '../../components/UI'
import {
  changed,
  savePayload,
  safeReason,
  statusText,
  type Draft,
  type LLMSettings,
} from './settings'
import '../asr/asr.css'

export function LLMSettingsPanel() {
  return (
    <AdminSession>
      {(session, expired) => (
        <Editor
          key={session.user.workspace_id + session.user.id}
          session={session}
          expired={expired}
        />
      )}
    </AdminSession>
  )
}
function Editor({ session, expired }: { session: Session; expired: () => void }) {
  const [saved, setSaved] = useState<LLMSettings | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [key, setKey] = useState(''),
    [busy, setBusy] = useState('')
  const [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const [unknown, setUnknown] = useState(false),
    [conflict, setConflict] = useState(false)
  const [needsReload, setNeedsReload] = useState(false)
  const lock = useRef(false),
    alive = useRef(true)
  function accept(data: LLMSettings) {
    setSaved(data)
    setDraft({ base_url: data.base_url, model: data.model, timeout_seconds: data.timeout_seconds })
    setKey('')
    setConflict(false)
    setNeedsReload(false)
  }
  function fail(e: unknown) {
    if (e instanceof ApiError && e.status === 401) {
      setKey('')
      expired()
      return
    }
    if (e instanceof ApiError && e.status === 409 && e.code === 'revision_conflict') {
      setConflict(true)
      setError('配置已被其他操作更新。草稿已保留，请重新读取后核对。')
      return
    }
    setError(
      e instanceof ApiError && e.status === 403
        ? '无权操作或会话校验失败，请重新登录。'
        : e instanceof ApiError
          ? safeReason(e.code)
          : '操作结果尚未确认，请从服务器刷新后核对。',
    )
  }
  useEffect(() => {
    alive.current = true
    const abort = new AbortController()
    request<LLMSettings>('/llm/settings', { signal: abort.signal })
      .then(accept)
      .catch((e) => {
        if (!abort.signal.aborted) fail(e)
      })
    return () => {
      alive.current = false
      abort.abort()
    }
  }, [])
  async function mutate(action: 'save' | 'clear' | 'check' | 'load') {
    if (lock.current || (action !== 'load' && (!saved || !draft || needsReload))) return
    if (
      action === 'check' &&
      (!saved ||
        !draft ||
        changed(saved, draft, key) ||
        unknown ||
        conflict ||
        !saved.configured ||
        ['unknown', 'checking'].includes(saved.status))
    )
      return
    lock.current = true
    setBusy(action)
    setError('')
    setNotice('')
    const revision = saved?.revision
    try {
      const path = action === 'check' ? '/llm/settings/check' : '/llm/settings'
      const body =
        action === 'save'
          ? savePayload(saved!, draft!, key)
          : action === 'check'
            ? { expected_revision: revision, request_id: crypto.randomUUID() }
            : { expected_revision: revision }
      const data = await request<LLMSettings>(
        path,
        action === 'load'
          ? {}
          : {
              method: action === 'save' ? 'PUT' : action === 'clear' ? 'DELETE' : 'POST',
              body: JSON.stringify(body),
            },
        session.csrf_token,
      )
      if (!alive.current) return
      if (action === 'check' && data.revision !== revision) {
        setConflict(true)
        setError('配置版本已变化，本次结果不用于当前配置。请重新读取。')
        return
      }
      accept(data)
      if (action === 'save' || action === 'clear') setUnknown(false)
      setNotice(
        action === 'save'
          ? '已保存，尚未进行连接测试。密钥输入已清空。'
          : action === 'clear'
            ? '密钥已清除，接口地址与模型已保留。'
            : action === 'load'
              ? '已从服务器读取。'
              : '连接测试状态已更新。',
      )
    } catch (e) {
      if (!alive.current) return
      if (action === 'check' && (!(e instanceof ApiError) || e.status >= 500)) {
        setUnknown(true)
        setError('测试结果未知，已禁止重复发送。请管理员核查服务器记录；刷新不会自动重试。')
      } else if (
        (action === 'save' || action === 'clear') &&
        (!(e instanceof ApiError) || e.status >= 500)
      ) {
        setNeedsReload(true)
        setKey('')
        setError('保存或清除结果尚未确认，已阻止重复修改。请从服务器刷新核对结果。')
      } else fail(e)
    } finally {
      lock.current = false
      if (alive.current) setBusy('')
    }
  }
  const dirty = saved && draft ? changed(saved, draft, key) : false
  const valid =
    draft &&
    !!draft.base_url.trim() &&
    !!draft.model.trim() &&
    Number.isFinite(draft.timeout_seconds) &&
    draft.timeout_seconds > 0 &&
    (!key || !!key.trim())
  return (
    <>
      <h2>大模型配置</h2>
      <p className="muted">
        配置保存在当前工作区服务器。保存不会调用模型；复盘报告与评分分析尚未启用。
      </p>
      {error && (
        <p className="asr-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="asr-success">
          {notice}
        </p>
      )}
      {!draft || !saved ? (
        <Button disabled={!!busy} onClick={() => mutate('load')}>
          重新读取大模型设置
        </Button>
      ) : (
        <>
          <fieldset className="asr-fields" disabled={!!busy}>
            <legend>接口与模型</legend>
            <label className="field">
              接口地址
              <input
                type="url"
                value={draft.base_url}
                onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
              />
            </label>
            <label className="field">
              模型名称
              <input
                value={draft.model}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
              />
            </label>
            <label className="field">
              超时（秒）
              <input
                type="number"
                min={1}
                value={draft.timeout_seconds}
                onChange={(e) => setDraft({ ...draft, timeout_seconds: Number(e.target.value) })}
              />
            </label>
            <label className="field">
              API 密钥
              <input
                type="password"
                autoComplete="new-password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="留空保留已保存密钥"
              />
            </label>
            <p>
              密钥状态：{saved.configured ? '已配置' : '未配置'}
              。只写入，不回显；填入新密钥会替换已保存密钥。
            </p>
          </fieldset>
          {saved.debug_http && (
            <p className="asr-warning">
              服务端已为此接口启用授权 HTTP 调试。此状态不代表业务分析可用。
            </p>
          )}
          <div className="asr-actions">
            <Button
              primary
              disabled={!!busy || !valid || conflict || needsReload}
              onClick={() => mutate('save')}
            >
              保存大模型配置
            </Button>
            <Button
              disabled={!!busy || !saved.configured || conflict || needsReload}
              onClick={() => mutate('clear')}
            >
              清除已保存密钥
            </Button>
            <Button disabled={!!busy} onClick={() => mutate('load')}>
              {dirty ? '放弃草稿并重新读取' : '从服务器刷新'}
            </Button>
          </div>
          <p className="muted">
            版本 {saved.revision} · {dirty ? '配置已变更，保存后需重测' : '已同步'}
          </p>
          <section className="asr-section">
            <h3>连接测试</h3>
            <p className="muted">
              仅对已保存版本发送一次最小合成请求，不发送直播材料。连接成功仅证明本次测试通过，业务分析尚未启用。
            </p>
            <Badge>
              {dirty
                ? '配置已变更需重测'
                : unknown
                  ? '测试结果未知，禁止重复发送'
                  : statusText(saved.status)}
            </Badge>
            {saved.checked_at && <p>测试时间：{saved.checked_at}</p>}
            {!dirty && saved.last_error && <p>{safeReason(saved.last_error)}</p>}
            {!dirty && saved.usage && (
              <p>
                Token 用量：输入 {saved.usage.prompt_tokens ?? '未提供'} · 输出{' '}
                {saved.usage.completion_tokens ?? '未提供'} · 总计{' '}
                {saved.usage.total_tokens ?? '未提供'}
              </p>
            )}
            <Button
              disabled={
                !!busy ||
                !!dirty ||
                conflict ||
                needsReload ||
                unknown ||
                !saved.configured ||
                ['checking', 'unknown'].includes(saved.status)
              }
              onClick={() => mutate('check')}
            >
              {busy === 'check' ? '正在测试…' : '测试已保存配置（一次请求）'}
            </Button>
          </section>
        </>
      )}
    </>
  )
}
