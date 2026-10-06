import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { request, ApiError } from '../../api/client'
import { Button } from '../../components/UI'
import type { ASRSettings } from '../asr/types'
import {
  materialBlocker,
  cloudBudgetValid,
  serviceChanged,
  type ProviderInfo,
  type MaterialGrant,
} from './materialASR'
export function MaterialASRControls({
  csrf,
  durationSeconds,
  disabled,
  onStart,
  retrying,
}: {
  csrf: string
  durationSeconds: number | null
  retrying?: boolean
  disabled: boolean
  onStart: (grant: MaterialGrant) => Promise<void>
}) {
  const [settings, setSettings] = useState<ASRSettings | null>(null),
    [provider, setProvider] = useState<ASRSettings['provider']>('local'),
    [providers, setProviders] = useState<ProviderInfo[]>([])
  const [privacyGrant, setPrivacyGrant] = useState(false),
    [grant, setGrant] = useState(false),
    [requests, setRequests] = useState('1'),
    [cost, setCost] = useState('')
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [mustReload, setMustReload] = useState(false)
  const lock = useRef(false)
  async function load(signal?: AbortSignal) {
    try {
      const [s, p] = await Promise.all([
        request<ASRSettings>('/asr/settings', { signal }),
        request<{ providers: ProviderInfo[] }>('/asr/providers', { signal }),
      ])
      if (signal?.aborted) return
      setSettings(s)
      setProvider(s.provider)
      setProviders(p.providers)
      setGrant(false)
      setPrivacyGrant(false)
      setMustReload(false)
      setError('')
    } catch (e) {
      if (!signal?.aborted)
        setError(
          e instanceof ApiError && e.status === 401
            ? '管理员会话已失效，请重新登录。'
            : '无法读取转写设置，请重新读取。',
        )
    }
  }
  useEffect(() => {
    const a = new AbortController()
    void load(a.signal)
    return () => a.abort()
  }, [])
  const dirty = !!settings && serviceChanged(settings, provider),
    cloud = provider === 'tencent'
  const needsPrivacy = cloud && settings?.privacy !== 'cloud_allowed'
  const blocker = materialBlocker(
    providers.find((p) => p.provider === provider),
    durationSeconds,
  )
  const unavailable =
    disabled ||
    busy ||
    mustReload ||
    !settings?.revision ||
    dirty ||
    !!blocker ||
    (cloud && (!grant || !cloudBudgetValid(requests, cost)))
  async function save() {
    if (lock.current || !settings || (needsPrivacy && !privacyGrant) || mustReload) return
    lock.current = true
    setBusy(true)
    setError('')
    setNotice('')
    setGrant(false)
    try {
      const { revision, ...fields } = settings
      const s = await request<ASRSettings>(
        '/asr/settings',
        {
          method: 'PUT',
          body: JSON.stringify({
            ...fields,
            provider,
            privacy: cloud ? 'cloud_allowed' : fields.privacy,
            expected_revision: revision,
          }),
        },
        csrf,
      )
      setSettings(s)
      setProvider(s.provider)
      setPrivacyGrant(false)
      setNotice('工作区转写服务已保存；尚未提交转写。')
    } catch (e) {
      setMustReload(true)
      setError(
        e instanceof ApiError && e.status === 409
          ? '设置版本已变化，请重新读取后核对。'
          : '保存结果尚未确认，请重新读取；不要重复保存。',
      )
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  async function start() {
    if (lock.current || unavailable || !settings) return
    lock.current = true
    setBusy(true)
    const authorized = cloud && grant
    setGrant(false)
    try {
      await onStart({
        expected_revision: settings.revision,
        allow_network: authorized,
        max_requests: authorized ? Number(requests) : null,
        max_cost_usd: authorized ? Number(cost) : null,
      })
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <>
      <h3>材料转写</h3>
      <p className="muted">
        复用当前材料，无需再次上传。语音识别使用本地或腾讯云 ASR，大模型聊天配置不用于转写。
      </p>
      <fieldset className="asr-fields" disabled={disabled || busy}>
        <legend>转写服务</legend>
        <label className="field">
          选择转写服务
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value as ASRSettings['provider'])
              setGrant(false)
              setPrivacyGrant(false)
              setNotice('')
            }}
          >
            <option value="local">本地语音识别</option>
            <option value="tencent">腾讯云语音识别</option>
          </select>
        </label>
        <p className="muted">保存将更新当前工作区默认转写服务；不会立即开始转写。</p>
        {needsPrivacy && (
          <label className="asr-option">
            <input
              type="checkbox"
              checked={privacyGrant}
              onChange={(e) => setPrivacyGrant(e.target.checked)}
            />
            <span>允许当前工作区使用云端处理；每次任务仍需单独授权</span>
          </label>
        )}
        <Button
          disabled={!settings || mustReload || (needsPrivacy && !privacyGrant)}
          onClick={save}
        >
          保存转写服务设置
        </Button>
        <Button onClick={() => load()}>重新读取转写设置</Button>
      </fieldset>
      {dirty && <p className="asr-warning">服务选择尚未保存，请先保存后再提交。</p>}
      {blocker && <p className="asr-warning">{blocker}</p>}
      <p className="muted">
        配置状态仅说明服务端配置具备，不代表已验证识别成功。
        <Link to="/settings" className="text-link">
          打开设置
        </Link>
      </p>
      {cloud && (
        <>
          <p className="asr-warning">
            腾讯云当前仅支持规范化 WAV 不超过{' '}
            {providers.find((p) => p.provider === 'tencent')?.max_audio_bytes ?? 5000000} 字节（最多{' '}
            {providers.find((p) => p.provider === 'tencent')?.max_duration_seconds ?? 156}{' '}
            秒）。这不是原视频文件大小；长直播云端转写尚未接入。
          </p>
          <fieldset className="asr-cloud" disabled={disabled || busy || dirty || !!blocker}>
            <legend>本次云端授权</legend>
            <label className="asr-option">
              <input type="checkbox" checked={grant} onChange={(e) => setGrant(e.target.checked)} />
              <span>授权本次将音频发送腾讯云并接受费用</span>
            </label>
            <label className="field">
              最多请求次数
              <input
                type="number"
                min={1}
                max={10}
                step={1}
                value={requests}
                onChange={(e) => setRequests(e.target.value)}
              />
            </label>
            <label className="field">
              金额预算（美元）
              <input
                type="number"
                min={0.01}
                max={100}
                step={0.01}
                value={cost}
                onChange={(e) => setCost(e.target.value)}
              />
            </label>
            <small>金额是授权声明，系统尚未核算供应商实际账单。</small>
          </fieldset>
        </>
      )}
      {!cloud && <p className="muted">本次仅本地处理，不授权云端回退。</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <Button disabled={unavailable} onClick={start}>
        {busy
          ? '正在处理…'
          : retrying
            ? '按所选服务重新转写'
            : cloud
              ? '手动开始腾讯云转写'
              : '手动开始本地转写'}
      </Button>
    </>
  )
}
