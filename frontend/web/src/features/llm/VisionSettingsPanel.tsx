import {useEffect, useState} from 'react'
import {type Session} from '../../auth/AdminSession'
import {Badge, Button} from '../../components/UI'
import {useSettingsResource} from '../model-settings/useSettingsResource'
import '../asr/asr.css'

type Vision = {
  revision: string; enabled: boolean; mode: 'default' | 'independent'; model: string;
  base_url: string; timeout_seconds: number; configured: boolean; independent_key_configured: boolean;
  effective_base_url: string; default_revision: string | null; default_status: string | null;
  debug_http: boolean; analysis_enabled: false; verification: 'not_tested'
}
export function VisionSettingsEditor({session, expired}: {session: Session; expired: () => void}) {
  const r = useSettingsResource<Vision>('/llm/vision/settings', session, expired)
  const [draft, setDraft] = useState<Vision | null>(null), [key, setKey] = useState('')
  useEffect(() => {setDraft(r.value); setKey('')}, [r.value])
  async function save() {
    if (!draft) return
    const {enabled, mode, model, base_url, timeout_seconds} = draft
    await r.perform('save', {enabled, mode, model: model.trim(), base_url: base_url.trim(), timeout_seconds, ...(mode === 'independent' && key ? {api_key: key} : {})})
    setKey('')
  }
  const invalid = !draft || (draft.enabled && !draft.model.trim()) || (draft.mode === 'independent' && !draft.base_url.trim()) || !Number.isInteger(draft?.timeout_seconds) || draft.timeout_seconds < 1 || draft.timeout_seconds > 120
  return <section className="asr-section" aria-label="画面理解服务配置"><h2>画面理解 · 可选</h2>
    <p className="muted">为抽取的画面选择支持图片输入的模型。可以复用上方默认服务，模型名称单独填写。保存配置不会上传画面，录像分析业务尚待接入。</p>
    <Badge tone="amber">视觉能力未验证 · 业务待接入</Badge>
    {r.error && <p className="asr-error" role="alert">{r.error}</p>}{r.notice && <p className="asr-success" role="status">{r.notice}</p>}
    {draft && <fieldset className="asr-fields" disabled={r.busy || r.blocked}><legend>画面用途</legend>
      <label className="asr-option"><input type="checkbox" checked={draft.enabled} onChange={e => setDraft({...draft, enabled: e.target.checked})}/><span>保存画面理解用途配置<small>这是配置偏好，不会自动开始分析。</small></span></label>
      <label className="field">服务来源<select value={draft.mode} onChange={e => {setDraft({...draft, mode: e.target.value as Vision['mode']}); setKey('')}}><option value="default">复用默认文本服务的接口与密钥</option><option value="independent">独立配置画面服务</option></select></label>
      <label className="field">视觉模型名称<input value={draft.model} maxLength={128} placeholder="填写供应商提供的图片理解模型标识" onChange={e => setDraft({...draft, model: e.target.value})}/></label>
      {draft.mode === 'default' ? <p className="muted">接口与密钥按引用读取，不复制保存。默认服务更新后引用同步生效。{r.value?.mode === 'default' && r.value.effective_base_url && <> 当前已保存引用：{r.value.effective_base_url}</>}</p> : <>
        <p className="muted">协议：OpenAI-compatible。模型名称与接口协议是两项不同配置。</p>
        <label className="field">画面服务 API Base URL<input value={draft.base_url} placeholder="https://api.example.com/v1" onChange={e => setDraft({...draft, base_url: e.target.value})}/></label>
        <label className="field">画面服务 API Key<input type="password" autoComplete="new-password" value={key} onChange={e => setKey(e.target.value)} placeholder={r.value?.independent_key_configured ? '留空保留已保存密钥' : '填写独立服务密钥'}/></label>
        <label className="field">画面服务超时（秒）<input type="number" min={1} max={120} value={draft.timeout_seconds} onChange={e => setDraft({...draft, timeout_seconds: Number(e.target.value)})}/></label>
      </>}
    </fieldset>}
    {r.value && <p className="muted">已保存状态：{r.value.enabled ? '已选择画面用途' : '暂不使用画面用途'} · {r.value.configured ? '配置字段已齐备，未验证能力' : '配置尚未齐备'}{r.value.default_status === 'unknown' && ' · 默认文本测试结果未知，不能重放旧请求'}{r.value.debug_http && ' · HTTP仅限已授权的开发配置，不代表视觉业务可执行'}</p>}
    <div className="asr-actions"><Button primary disabled={r.busy || r.blocked || invalid} onClick={save}>保存画面配置</Button><Button disabled={r.busy} onClick={() => r.perform('load')}>重新读取画面配置</Button><Button disabled={!r.value?.independent_key_configured || r.busy || r.blocked} onClick={async () => {await r.perform('clear'); setKey('')}}>清除独立密钥并关闭画面用途</Button></div>
  </section>
}
