import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AdminSession, type Session } from '../../auth/AdminSession'
import { request, message, ApiError } from '../../api/client'
import { PageHeader, Empty, Button } from '../../components/UI'
import { CapturePanel } from '../capture/CapturePanel'
import { MaterialTranscription } from './MaterialTranscription'
import { platformName, type LiveSession, type Page, type Material } from './types'
import '../asr/asr.css'
export function LiveSessionDetail() {
  const { id = '' } = useParams()
  return (
    <>
      <Link className="text-link" to="/sessions">
        ← 直播场次
      </Link>
      <AdminSession>
        {(auth, expired) => (
          <Detail key={`${auth.user.id}:${id}`} id={id} auth={auth} expired={expired} />
        )}
      </AdminSession>
    </>
  )
}
function Detail({ id, auth, expired }: { id: string; auth: Session; expired: () => void }) {
  const [session, setSession] = useState<LiveSession | null>(null),
    [materials, setMaterials] = useState<Material[]>([]),
    [error, setError] = useState(''),
    [reload, setReload] = useState(0)
  useEffect(() => {
    const a = new AbortController()
    Promise.all([
      request<LiveSession>(`/sessions/${id}`, { signal: a.signal }),
      request<Page<{ material: Material }>>(`/sessions/${id}/materials?limit=100`, {
        signal: a.signal,
      }),
    ])
      .then(([s, m]) => {
        setSession(s)
        setMaterials(m.items.map((x) => x.material))
        setError('')
      })
      .catch((e) => {
        if (!a.signal.aborted) {
          setError(message(e))
          if (e instanceof ApiError && e.status === 401) expired()
        }
      })
    return () => a.abort()
  }, [id, reload])
  return (
    <>
      {error && (
        <p className="asr-error" role="alert">
          {error}
        </p>
      )}
      {session ? (
        <>
          <PageHeader
            title={session.title}
            description={`${platformName[session.platform]} · ${session.session_local_date} · 真实场次`}
          />
          <CapturePanel
            session={session}
            csrf={auth.csrf_token}
            scope={auth.user.workspace_id}
            onImported={() => setReload((x) => x + 1)}
          />
          <section className="asr-section">
            <div className="asr-section-heading">
              <h2>场次材料</h2>
              <Button onClick={() => setReload((x) => x + 1)}>刷新材料</Button>
            </div>
            {!materials.length ? (
              <Empty title="尚无录制材料" description="采集结束并成功导入后，录像会出现在这里。" />
            ) : (
              materials.map((m) => (
                <article className="asr-section" key={m.material_id}>
                  <h3>{m.filename}</h3>
                  <p className="muted">{(m.size_bytes / 1024 / 1024).toFixed(1)} MB</p>
                  {m.media_type.startsWith('video/') ? (
                    <video
                      style={{ width: '100%', maxHeight: 480 }}
                      controls
                      preload="metadata"
                      src={`/api/v1/materials/${m.material_id}/content`}
                    />
                  ) : m.media_type.startsWith('audio/') ? (
                    <audio
                      controls
                      preload="metadata"
                      src={`/api/v1/materials/${m.material_id}/content`}
                    />
                  ) : null}
                  <p>
                    <a
                      className="text-link"
                      href={`/api/v1/materials/${m.material_id}/content`}
                      download={m.filename}
                    >
                      下载原材料
                    </a>
                  </p>
                  {/^(audio|video)\//.test(m.media_type) && (
                    <MaterialTranscription
                      materialId={m.material_id}
                      csrf={auth.csrf_token}
                      scope={auth.user.workspace_id}
                    />
                  )}
                </article>
              ))
            )}
          </section>
          <section className="asr-section">
            <h2>复盘报告</h2>
            <p className="muted">
              尚未生成。采集或转写完成不代表已形成复盘报告；评分标准仍待配置。
            </p>
          </section>
        </>
      ) : (
        !error && <p role="status">正在读取场次…</p>
      )}
    </>
  )
}
