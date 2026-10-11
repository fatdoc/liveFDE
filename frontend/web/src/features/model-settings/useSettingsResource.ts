import {useEffect, useRef, useState} from 'react'
import {ApiError, request} from '../../api/client'
import type {Session} from '../../auth/AdminSession'

// Two private configuration editors share CAS and ambiguous-write recovery, not secrets.
export function useSettingsResource<T extends {revision: string}>(path: string, session: Session, expired: () => void) {
  const [value, setValue] = useState<T | null>(null)
  const [busy, setBusy] = useState(false), [blocked, setBlocked] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const lock = useRef(false), alive = useRef(true)
  function failure(e: unknown, writing: boolean) {
    if (e instanceof ApiError && e.status === 401) {expired(); return}
    if (writing && (!(e instanceof ApiError) || e.status >= 500 || e.status === 409)) setBlocked(true)
    setError(e instanceof ApiError && e.status === 409 ? '配置已变化或正在处理。请重新读取后核对，不要重复提交。'
      : e instanceof ApiError && e.status === 422 ? '字段未通过校验。请核对模型、接口地址、超时及凭据格式；密钥留空表示保留。'
      : e instanceof ApiError && e.status === 403 ? '当前会话无权修改，请重新登录。'
      : '操作未确认。请重新读取服务器配置后再操作。')
  }
  useEffect(() => {
    alive.current = true
    const abort = new AbortController()
    request<T>(path, {signal: abort.signal}).then(v => {if (alive.current) setValue(v)})
      .catch(e => {if (!abort.signal.aborted && alive.current) failure(e, false)})
    return () => {alive.current = false; abort.abort()}
  }, [path, session.user.workspace_id])
  async function perform(action: 'load' | 'save' | 'clear', fields?: Record<string, unknown>) {
    if (lock.current || (action !== 'load' && (!value || blocked))) return false
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try {
      const result = await request<T>(path, action === 'load' ? {} : {
        method: action === 'save' ? 'PUT' : 'DELETE',
        body: JSON.stringify({...fields, expected_revision: value!.revision}),
      }, action === 'load' ? undefined : session.csrf_token)
      if (alive.current) {setValue(result); setBlocked(false); setNotice(action === 'load' ? '已重新读取。' : action === 'clear' ? '已清除该服务凭据。' : '配置已保存；没有发送模型请求。')}
      return true
    } catch(e) {if (alive.current) failure(e, action !== 'load'); return false}
    finally {lock.current = false; if (alive.current) setBusy(false)}
  }
  return {value, busy, blocked, error, notice, perform}
}
