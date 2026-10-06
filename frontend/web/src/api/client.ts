export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(status === 401 ? '登录已失效，请重新登录。' : status === 409 ? '数据已被其他操作更新。你的草稿已保留，请重新读取后核对。' : status === 403 ? '无权执行此操作，或会话校验失败。请重新登录。' : `请求未成功（${status} / ${code}），未保存到本地。`)
  }
}
export async function request<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const headers = new Headers(options.headers)
  if (csrf) headers.set('X-CSRF-Token', csrf)
  if (typeof options.body === 'string') headers.set('Content-Type', 'application/json')
  let response: Response
  try { response = await fetch(`/api/v1${path}`, {...options, headers, credentials: 'include'}) }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new Error('无法连接后端。操作结果尚未确认，请检查连接后刷新；不要重复提交转写任务。') }
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const code = data?.error?.code ?? data?.code
    throw new ApiError(response.status, typeof code === 'string' && /^[a-z0-9_]+$/i.test(code) ? code : 'request_failed')
  }
  if (response.status === 204) return undefined as T
  const type = response.headers.get('content-type') ?? ''
  if (!type.includes('application/json')) throw new Error('后端响应格式不正确，请检查 API 连接。')
  return response.json() as Promise<T>
}
export const message = (error: unknown) => error instanceof Error ? error.message : '操作未完成，请重新检查。'
