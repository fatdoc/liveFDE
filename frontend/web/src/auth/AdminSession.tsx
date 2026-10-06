import {useEffect, useState, type FormEvent, type ReactNode} from 'react'
import {Button} from '../components/UI'
import {request, message} from '../api/client'
export type Session = {user: {id: string; workspace_id: string; display_name: string; role: 'admin'}; csrf_token: string}
export function AdminSession({children}: {children: (session: Session, expired: () => void) => ReactNode}) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [username, setUsername] = useState(''), [password, setPassword] = useState('')
  useEffect(() => { const abort = new AbortController(); request<Session>('/auth/me', {signal: abort.signal}).then(setSession).catch(e => {if (!abort.signal.aborted && e.status !== 401) setError(message(e))}).finally(() => {if (!abort.signal.aborted) setLoading(false)}); return () => abort.abort() }, [])
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { setSession(await request<Session>('/auth/login', {method: 'POST', body: JSON.stringify({username, password})})); setPassword('') }
    catch (e) {setError(message(e))} finally {setBusy(false)}
  }
  async function logout() {
    setBusy(true); setError('')
    try {await request<void>('/auth/logout', {method: 'POST'}, session?.csrf_token); setSession(null)} catch (e) {setError(message(e))} finally {setBusy(false)}
  }
  if (loading) return <p role="status">正在检查管理员会话…</p>
  return <div className="asr-workspace">{error && <p className="asr-error" role="alert">{error}</p>}{session ? <>
    <div className="asr-session"><div><strong>{session.user.display_name}</strong><span> 已登录 · 管理员</span></div><Button disabled={busy} onClick={logout}>退出登录</Button></div>
    {children(session, () => {setSession(null); setError('会话已失效，请重新登录。')})}
  </> : <form onSubmit={login} className="asr-login"><h2>管理员登录</h2><p className="muted">登录后管理真实场次、录制材料和转写设置。</p><label className="field">用户名<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)}/></label><label className="field">密码<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)}/></label><Button primary type="submit" disabled={busy}>{busy ? '正在登录…' : '登录工作区'}</Button></form>}</div>
}
