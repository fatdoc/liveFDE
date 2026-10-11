import {useEffect, useState} from 'react'
import {Badge, Button} from '../../components/UI'
import type {Session} from '../../auth/AdminSession'
import {useSettingsResource} from '../model-settings/useSettingsResource'

type Tencent = {
  revision: string; configured: boolean; secret_id_configured: boolean; secret_key_configured: boolean;
  app_id_configured: boolean; model: string; stream_model: string; timeout_seconds: number;
  max_audio_bytes: number; max_duration_seconds: number; network_checked: false
}
const emptyKeys = {secret_id: '', secret_key: '', app_id: ''}
export function TencentSettingsPanel({session, expired, onSaved}: {session: Session; expired: () => void; onSaved: () => void}) {
  const r = useSettingsResource<Tencent>('/asr/tencent/settings', session, expired)
  const [draft, setDraft] = useState<Tencent | null>(null), [keys, setKeys] = useState(emptyKeys)
  useEffect(() => {setDraft(r.value); setKeys(emptyKeys)}, [r.value])
  async function save() {
    if (!draft) return
    const secrets = Object.fromEntries(Object.entries(keys).filter(([, value]) => value !== ''))
    const ok = await r.perform('save', {model: draft.model.trim(), stream_model: draft.stream_model, timeout_seconds: draft.timeout_seconds, ...secrets})
    setKeys(emptyKeys); if (ok) onSaved()
  }
  const invalid = !draft || !draft.model.trim() || !Number.isInteger(draft.timeout_seconds) || draft.timeout_seconds < 1 || draft.timeout_seconds > 600
  return <section className="asr-section" aria-label="腾讯ASR服务配置"><h3>腾讯云凭据 · 使用云端时填写</h3>
    <p className="muted">本地语音识别无需云密钥。腾讯凭据仅保存到当前工作区服务器，所有凭据只写不回显；留空保留已有值，不继承服务器全局凭据。保存不会发起识别，也不会改变当前隐私选择。</p>
    {r.error && <p className="asr-error" role="alert">{r.error}</p>}{r.notice && <p className="asr-success" role="status">{r.notice}</p>}
    {r.value && <p><Badge tone={r.value.configured ? 'teal' : 'amber'}>{r.value.configured ? '凭据已齐备 · 未验证外部服务' : '缺少文件转写凭据'}</Badge><span className="muted">{!r.value.secret_id_configured && ' 请填写 SecretId。'}{!r.value.secret_key_configured && ' 请填写 SecretKey。'}{!r.value.app_id_configured && ' AppID 尚未配置，实时能力需要此项。'}</span></p>}
    {draft && <fieldset disabled={r.busy || r.blocked} className="asr-fields"><legend>腾讯 ASR 专用协议</legend>
      {([{name:'secret_id',label:'腾讯 SecretId',configured:draft.secret_id_configured},{name:'secret_key',label:'腾讯 SecretKey',configured:draft.secret_key_configured},{name:'app_id',label:'腾讯 AppID（实时识别使用）',configured:draft.app_id_configured}] as const).map(item => <label className="field" key={item.name}>{item.label}<input type="password" autoComplete="new-password" value={keys[item.name]} placeholder={item.configured ? '已保存，留空保留' : '尚未保存'} onChange={e => setKeys({...keys, [item.name]: e.target.value})}/></label>)}
      <label className="field">文件识别模型<input value={draft.model} maxLength={128} onChange={e => setDraft({...draft, model: e.target.value})}/></label>
      <label className="field">实时识别模型<select value={draft.stream_model} onChange={e => setDraft({...draft, stream_model: e.target.value})}><option value="16k_zh_en_speaker_2.0">16k_zh_en_speaker_2.0</option><option value="16k_zh_en_2.0">16k_zh_en_2.0</option></select></label>
      <label className="field">腾讯请求总超时（秒）<input type="number" min={1} max={600} value={draft.timeout_seconds} onChange={e => setDraft({...draft, timeout_seconds: Number(e.target.value)})}/></label>
    </fieldset>}
    <p className="muted">当前文件适配上限：标准化 WAV 5 MB，约 156 秒。长录像的云端分段转写尚未实现。每次发送音频仍需单独授权和预算。</p>
    <div className="asr-actions"><Button primary disabled={invalid || r.busy || r.blocked} onClick={save}>保存腾讯服务配置</Button><Button disabled={r.busy} onClick={() => r.perform('load')}>重新读取腾讯配置</Button><Button disabled={!r.value || r.busy || r.blocked || !(r.value.secret_id_configured || r.value.secret_key_configured || r.value.app_id_configured)} onClick={async () => {const ok = await r.perform('clear'); setKeys(emptyKeys); if (ok) onSaved()}}>清除腾讯全部凭据</Button></div>
  </section>
}
