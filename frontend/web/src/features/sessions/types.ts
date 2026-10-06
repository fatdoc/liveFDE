export type Platform = 'douyin' | 'wechat' | 'other'
export const platformName = { douyin: '抖音', wechat: '微信视频号', other: '其他' }
export type Streamer = { id: string; name: string; platform: Platform }
export type LiveSession = {
  id: string
  title: string
  streamer_id: string
  platform: Platform
  session_local_date: string
  processing_status: string
}
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }
export type Material = {
  material_id: string
  filename: string
  media_type: string
  size_bytes: number
}
