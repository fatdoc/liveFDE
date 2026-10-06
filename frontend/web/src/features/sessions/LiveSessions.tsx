import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AdminSession, type Session } from '../../auth/AdminSession'
import { request, message, ApiError } from '../../api/client'
import { PageHeader, Button, Empty, Modal } from '../../components/UI'
import { platformName, type Platform, type Streamer, type LiveSession, type Page } from './types'
import '../asr/asr.css'
export function LiveSessions() {
  return (
    <>
      <PageHeader title="直播场次" description="创建真实场次，录制直播并查看材料。" />
      <AdminSession>
        {(auth, expired) => <SessionList auth={auth} expired={expired} />}
      </AdminSession>
    </>
  )
}
function SessionList({ auth, expired }: { auth: Session; expired: () => void }) {
  const [page, setPage] = useState<Page<LiveSession> | null>(null),
    [streamers, setStreamers] = useState<Streamer[]>([])
  const [offset, setOffset] = useState(0),
    [reload, setReload] = useState(0),
    [error, setError] = useState(''),
    [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false),
    [title, setTitle] = useState(''),
    [streamer, setStreamer] = useState(''),
    [name, setName] = useState(''),
    [platform, setPlatform] = useState<Platform>('douyin')
  const [date, setDate] = useState(
    new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date()),
  )
  const navigate = useNavigate()
  function fail(e: unknown) {
    setError(message(e))
    if (e instanceof ApiError && e.status === 401) expired()
  }
  useEffect(() => {
    const controller = new AbortController()
    setPage(null)
    setError('')
    Promise.all([
      request<Page<LiveSession>>(`/sessions?limit=20&offset=${offset}`, {
        signal: controller.signal,
      }),
      request<Page<Streamer>>('/streamers?limit=100', { signal: controller.signal }),
    ])
      .then(([p, s]) => {
        setPage(p)
        setStreamers(s.items)
      })
      .catch((e) => {
        if (!controller.signal.aborted) fail(e)
      })
    return () => controller.abort()
  }, [offset, reload])
  async function create(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const person = streamer
        ? streamers.find((s) => s.id === streamer)!
        : await request<Streamer>(
            '/streamers',
            { method: 'POST', body: JSON.stringify({ name: name.trim(), platform }) },
            auth.csrf_token,
          )
      if (!streamer) {
        setStreamers((s) => [...s, person])
        setStreamer(person.id)
      }
      const result = await request<LiveSession>(
        '/sessions',
        {
          method: 'POST',
          body: JSON.stringify({
            title: title.trim(),
            streamer_id: person.id,
            platform: person.platform,
            session_local_date: date,
          }),
        },
        auth.csrf_token,
      )
      navigate(`/sessions/${result.id}`)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="toolbar">
        <Button primary onClick={() => setOpen(true)}>
          新建直播场次
        </Button>
        <Button onClick={() => setReload((x) => x + 1)}>刷新列表</Button>
        <Link className="text-link" to="/demo/sessions">
          查看演示场次
        </Link>
      </div>
      {error && (
        <p role="alert" className="asr-error">
          {error}
        </p>
      )}
      {!page ? (
        <p role="status">{error ? '暂未读取到场次。' : '正在读取场次…'}</p>
      ) : page.items.length ? (
        <>
          <div className="table-scroll">
            <table className="session-table">
              <thead>
                <tr>
                  <th>主题</th>
                  <th>主播</th>
                  <th>平台</th>
                  <th>日期</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((s) => (
                  <tr key={s.id}>
                    <td>{s.title}</td>
                    <td>{streamers.find((p) => p.id === s.streamer_id)?.name ?? '主播'}</td>
                    <td>{platformName[s.platform]}</td>
                    <td>{s.session_local_date}</td>
                    <td>
                      <Link to={`/sessions/${s.id}`} className="text-link">
                        进入场次
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <Button disabled={!offset} onClick={() => setOffset((x) => Math.max(0, x - 20))}>
              上一页
            </Button>
            <span>共 {page.total} 场</span>
            <Button disabled={offset + 20 >= page.total} onClick={() => setOffset((x) => x + 20)}>
              下一页
            </Button>
          </div>
        </>
      ) : (
        <Empty title="还没有直播场次" description="先登记主播与主题，再开始录制。" />
      )}
      <Modal
        open={open}
        onOpenChange={(v) => {
          if (!busy) setOpen(v)
        }}
        title="新建直播场次"
        description="信息保存到当前工作区。日期按北京时间登记。"
      >
        <form onSubmit={create}>
          <label className="field">
            直播主题
            <input
              required
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="field">
            主播
            <select value={streamer} onChange={(e) => setStreamer(e.target.value)}>
              <option value="">新建主播</option>
              {streamers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {platformName[s.platform]}
                </option>
              ))}
            </select>
          </label>
          {!streamer && (
            <>
              <label className="field">
                主播姓名
                <input
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="field">
                直播平台
                <select value={platform} onChange={(e) => setPlatform(e.target.value as Platform)}>
                  {Object.entries(platformName).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <label className="field">
            直播日期
            <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {error && (
            <p role="alert" className="asr-error">
              {error}
            </p>
          )}
          <Button
            primary
            type="submit"
            disabled={busy || !title.trim() || (!streamer && !name.trim())}
          >
            {busy ? '正在保存…' : '保存并进入场次'}
          </Button>
        </form>
      </Modal>
    </>
  )
}
