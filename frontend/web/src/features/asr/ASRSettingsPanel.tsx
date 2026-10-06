import {useEffect, useState} from 'react'
import {Button, Badge} from '../../components/UI'
import {AdminSession, type Session} from '../../auth/AdminSession'
import {ApiError, message, request} from '../../api/client'
import type {ASRSettings, Health} from './types'
import {TranscriptionTrial} from './TranscriptionTrial'
import './asr.css'
const healthGuidance: Record<string, string> = {
  provider_dependencies_missing: '识别服务依赖尚未安装，请管理员完成服务安装后重新检查。',
  local_dependencies_missing: '本地识别依赖尚未安装，请管理员安装本地语音识别环境。',
  local_model_missing: '本地模型尚未就绪，请管理员准备模型文件；此按钮不会下载模型。',
  local_model_path_invalid: '本地模型路径无效，请管理员检查模型目录配置。',
  local_model_config_invalid: '本地模型配置无效，请管理员核对模型文件与配置。',
  model_configuration_missing: '尚未配置识别模型，请管理员完成服务配置。',
  tencent_credentials_missing: '腾讯云凭证尚未配置，请管理员在服务器配置凭证。',
  credentials_missing: '腾讯云凭证尚未配置，请管理员在服务器配置凭证。',
  configuration_only_not_network_verified: '凭证配置已读取，尚未验证腾讯云连接或调用权限。',
  provisioned_lazy_not_loaded: '模型文件已准备，将在首次转写时加载；尚未验证实际推理。',
  local_cuda_unavailable: '配置的显卡不可用，请管理员检查设备或改用CPU。',
  local_mps_unsupported: '当前本地服务不支持此设备配置，请管理员选择支持的运行设备。',
}
export function ASRSettingsPanel() {return <AdminSession>{(session, expired) => <SettingsEditor key={session.user.id} session={session} expired={expired}/>}</AdminSession>}
function SettingsEditor({session, expired}: {session: Session; expired: () => void}) {
  const [saved, setSaved] = useState<ASRSettings | null>(null), [draft, setDraft] = useState<ASRSettings | null>(null)
  const [health, setHealth] = useState<Health | null>(null), [busy, setBusy] = useState(false), [checking, setChecking] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [healthError, setHealthError] = useState('')
  const fail = (e: unknown) => {setError(message(e)); if (e instanceof ApiError && e.status === 401) expired()}
  async function load() {
    setBusy(true); setError(''); setNotice('')
    try {const data = await request<ASRSettings>('/asr/settings'); setSaved(data); setDraft(data)} catch (e) {fail(e)} finally {setBusy(false)}
  }
  useEffect(() => {const controller = new AbortController(); request<ASRSettings>('/asr/settings', {signal: controller.signal}).then(data => {setSaved(data); setDraft(data)}).catch(e => {if (!controller.signal.aborted) fail(e)}); return () => controller.abort()}, [])
  async function save() {
    if (!draft || !saved) return
    setBusy(true); setError(''); setNotice('')
    const {revision: _, ...fields} = draft
    try {const data = await request<ASRSettings>('/asr/settings', {method: 'PUT', body: JSON.stringify({...fields, expected_revision: saved.revision})}, session.csrf_token); setSaved(data); setDraft(data); setHealth(null); setNotice('已保存到服务器。刷新页面后仍有效。')}
    catch (e) {fail(e)} finally {setBusy(false)}
  }
  async function checkHealth() {
    setChecking(true); setHealthError('')
    try {setHealth(await request<Health>('/asr/health'))} catch (e) {setHealthError(message(e)); if (e instanceof ApiError && e.status === 401) expired()} finally {setChecking(false)}
  }
  const reason = health?.error || health?.health?.reason
  const dirty = JSON.stringify(saved) !== JSON.stringify(draft)
  return <><h2>语音转写设置</h2><p className="muted">这些设置保存在当前工作区服务器。切换服务不会开始识别。</p>
    {error && <p className="asr-error" role="alert">{error}</p>}{notice && <p className="asr-success" role="status">{notice}</p>}
    {!draft ? <Button onClick={load} disabled={busy}>{busy ? '正在读取…' : '重新读取设置'}</Button> : <>
      <fieldset disabled={busy} className="asr-fields"><legend>服务与隐私</legend>
        <label className="field">隐私策略<select value={draft.privacy} onChange={e => setDraft({...draft, privacy: e.target.value as ASRSettings['privacy'], ...(e.target.value === 'local_only' ? {provider: 'local', allow_cloud_fallback: false} : {})})}><option value="local_only">仅本地处理</option><option value="cloud_allowed">允许云端处理（每次仍需授权）</option></select></label>
        <label className="field">转写服务<select value={draft.provider} onChange={e => setDraft({...draft, provider: e.target.value as ASRSettings['provider']})}><option value="local">本地语音识别</option><option value="tencent" disabled={draft.privacy === 'local_only'}>腾讯云语音识别</option></select></label>
        <label className="asr-option"><input type="checkbox" checked={draft.allow_cloud_fallback} disabled={draft.privacy === 'local_only'} onChange={e => setDraft({...draft, allow_cloud_fallback: e.target.checked})}/><span>本地失败时允许转云端<small>仅在允许云端且本次已明确授权时生效。</small></span></label>
        <div className="asr-options">{([{key: 'speaker', label: '区分说话人', help: '只区分匿名说话人，不识别真实身份。'}, {key: 'emotion', label: '情绪标注', help: '未识别或不支持时显示未知。'}, {key: 'punctuation', label: '补充标点', help: '能力以实际服务支持为准。'}] as const).map(option => <label className="asr-option" key={option.key}><input type="checkbox" checked={draft[option.key]} onChange={e => setDraft({...draft, [option.key]: e.target.checked})}/><span>{option.label}<small>{option.help}</small></span></label>)}</div>
      </fieldset><div className="asr-actions"><Button primary disabled={busy || (!dirty && saved?.revision !== 0)} onClick={save}>{busy ? '正在保存…' : '保存转写设置'}</Button><Button disabled={busy} onClick={load}>{dirty ? '放弃草稿并重新读取' : '从服务器刷新'}</Button><span className="muted">版本 {saved?.revision} {saved?.revision === 0 ? '· 尚未保存工作区设置，请先保存一次' : dirty ? '· 有未保存修改' : '· 已同步'}</span></div>
      <section className="asr-section"><div className="asr-section-heading"><h3>服务状态</h3><Button disabled={checking} onClick={checkHealth}>{checking ? '正在检查…' : '检查已保存的配置'}</Button></div><p className="muted">状态检查不会发起试用转写或下载模型。</p>{healthError && <p role="alert" className="asr-error">{healthError}</p>}{health && <div role="status"><Badge tone={health.config_valid && health.health?.ready ? 'green' : 'amber'}>{!health.config_valid ? '配置无效' : health.health?.ready ? '服务已就绪' : '服务未就绪'}</Badge><p>{reason ? healthGuidance[reason] || '服务返回了状态信息，请管理员核对配置后再试。' : health.health?.ready ? '当前检查未发现异常。' : '服务尚未就绪，请管理员检查配置。'}{health.health?.device && ` · 设备 ${health.health.device}`}</p>{reason && <small>状态码：{reason}</small>}<br/><small>支持能力：{health.health?.capabilities.join('、') || '未报告'} · {health.health?.network_checked ? '已进行网络检查' : '未验证外部服务连接'}</small></div>}</section>
      {saved && <TranscriptionTrial settings={saved} csrf={session.csrf_token} expired={expired} dirty={dirty}/>}
    </>}
  </>
}
