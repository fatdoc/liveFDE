import {Link} from 'react-router-dom'
import {ArrowRight} from 'lucide-react'
import type {Session} from '../types'
import {Badge,Empty} from './UI'
export const statusNames={review:'待审核话术',complete:'复盘已完成',prepared:'备播稿已形成',draft:'待导入材料'}
export function SessionTable({sessions}:{sessions:Session[]}){return sessions.length?<div className="table-scroll"><table className="session-table"><thead><tr><th>主题</th><th>主播</th><th>日期</th><th>当前进度</th><th>操作</th></tr></thead><tbody>{sessions.map(s=><tr key={s.id}><td><Link className="table-title" to={'/sessions/'+s.id}>{s.title}</Link><small>{s.platform} · {s.duration}</small></td><td>{s.host}</td><td>{s.date.slice(5).replace('-','月')}日</td><td><Badge tone={s.status==='review'?'blue':s.status==='draft'?'neutral':'green'}>{statusNames[s.status]}</Badge></td><td><Link className="text-link" to={'/sessions/'+s.id}>{s.status==='review'?'继续审核':s.status==='draft'?'导入材料':'查看复盘'}<ArrowRight size={15}/></Link></td></tr>)}</tbody></table></div>:<Empty title="没有匹配的直播" description="调整筛选条件，或新建一场直播。"/>}
