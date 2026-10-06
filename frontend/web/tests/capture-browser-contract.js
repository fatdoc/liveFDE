// Run using playwright-cli run-code --filename tests/capture-browser-contract.js.
// Synthetic API contract test; no real platform recording, paid models or credentials.
async (page) => {
  const sid = '11111111-1111-4111-8111-111111111111',
    mid = '22222222-2222-4222-8222-222222222222'
  let enabled = false,
    sourceConfigured = false,
    run = null,
    starts = [],
    asrCalls = [],
    stopCount = 0,
    unknown = true,
    reject = true,
    platform = 'douyin'
  const person = { id: 'person1', name: '测试主播', platform: 'douyin' }
  const session = {
    id: sid,
    title: '合成采集验收',
    platform,
    streamer_id: person.id,
    session_local_date: '2026-10-06',
    processing_status: 'pending',
  }
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname.replace('/api/v1', '')
    let data
    let status = 200
    if (path === '/auth/me')
      data = {
        user: {
          id: 'admin1',
          workspace_id: 'test-workspace',
          display_name: '合成测试管理员',
          role: 'admin',
        },
        csrf_token: 'synthetic',
      }
    else if (path === '/auth/logout') {
      status = 204
    } else if (path === '/sessions') data = { items: [session], total: 1, limit: 20, offset: 0 }
    else if (path === '/streamers') data = { items: [person], total: 1, limit: 100, offset: 0 }
    else if (path === `/sessions/${sid}`) data = { ...session, platform }
    else if (path === `/sessions/${sid}/materials`)
      data = {
        items: run?.material_id
          ? [
              {
                material: {
                  material_id: mid,
                  filename: '合成样本.mp4',
                  media_type: 'video/mp4',
                  size_bytes: 1024,
                },
              },
            ]
          : [],
        total: run?.material_id ? 1 : 0,
        limit: 100,
        offset: 0,
      }
    else if (path === '/capture/health')
      data = {
        enabled,
        ffmpeg_ready: true,
        ffprobe_ready: true,
        execution: { ready: true, automatic_dispatch: true, state: 'idle' },
        providers: {
          douyin: {
            dependencies_ready: true, start_ready: enabled && sourceConfigured,
            blockers: sourceConfigured ? [] : [{code: 'capture_source_access_not_configured', message: '直播来源访问尚未开放：允许访问的域名未配置，需先完成采集就绪复核。'}],
          },
          wechat: { dependencies_ready: true, start_ready: enabled, blockers: [], device_name: '直播采集测试设备' },
        },
      }
    else if (path === '/capture/runs' && req.method() === 'GET')
      data = { items: run ? [run] : [], next_cursor: null }
    else if (path === '/capture/runs' && req.method() === 'POST') {
      starts.push({ key: req.headers()['idempotency-key'], body: req.postDataJSON() })
      if (reject) {reject = false; await route.fulfill({status: 422, contentType: 'application/json', body: JSON.stringify({error:{code:'source_rejected'}})}); return}
      if (unknown) {
        unknown = false
        await route.abort()
        return
      }
      run = {
        capture_run_id: 'run1',
        session_id: sid,
        platform,
        source_ref: 'https://live.douyin.com/123456',
        state: 'recording',
        job_status: 'running',
        stop_requested: false,
        material_id: null,
        manifest: null,
        import_status: 'pending',
        error_code: null,
      }
      data = run
      status = 202
    } else if (path === '/capture/runs/run1/stop') {
      stopCount++
      run = { ...run, stop_requested: true }
      data = run
      status = 202
    } else if (path === '/asr/settings')
      data = { revision: 1, provider: 'local', privacy: 'local_only', allow_cloud_fallback: false }
    else if (path === '/asr/transcriptions' && req.method() === 'POST') {
      asrCalls.push(req.postDataJSON())
      data = { id: 'job1', status: 'queued', steps: [], error: null }
      status = 202
    } else if (path === '/asr/transcriptions/job1')
      data = {
        job: { id: 'job1', status: 'succeeded', steps: [], error: null },
        result: {
          synthetic: true,
          complete: true,
          source: 'local',
          segments: [{ id: 's1', start_ms: 0, text: '合成转写契约验证' }],
        },
      }
    else if (path === `/materials/${mid}/content`) {
      await route.fulfill({ status: 200, contentType: 'video/mp4', body: '' })
      return
    } else throw new Error('Unexpected API ' + path)
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: status === 204 ? '' : JSON.stringify(data),
    })
  })
  await page.evaluate(() => sessionStorage.clear())
  await page.goto(new URL(`/sessions/${sid}`, page.url()).href)
  await page.getByText('采集服务尚未启用。', { exact: true }).waitFor()
  if (!(await page.getByRole('button', { name: '开始录制', exact: true }).isDisabled()))
    throw Error('disabled service allowed capture')
  enabled = true
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByText('直播来源访问尚未开放：', { exact: false }).waitFor()
  if (!(await page.getByRole('button', { name: '开始录制', exact: true }).isDisabled()))
    throw Error('empty source policy allowed capture despite ready executor and dependencies')
  if (starts.length) throw Error('blocked state issued a capture request')
  sourceConfigured = true
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page
    .getByPlaceholder('https://live.douyin.com/数字房间号')
    .fill('https://live.douyin.com/123456')
  await page.getByRole('button', { name: '开始录制', exact: true }).click()
  await page.getByText('请求未成功（422 / source_rejected）', { exact: false }).waitFor()
  await page.getByPlaceholder('https://live.douyin.com/数字房间号').fill('https://live.douyin.com/654321')
  await page.getByRole('button', { name: '开始录制', exact: true }).click()
  await page.getByText('上一次提交尚待确认。', { exact: false }).waitFor()
  await page.getByRole('button', { name: '重试确认同次采集', exact: true }).click()
  await page.getByText('正在录制', { exact: true }).waitFor()
  if (starts.length !== 3 || starts[1].key !== starts[2].key || starts[0].key === starts[1].key)
    throw Error('unknown submission changed idempotency key')
  await page.reload()
  await page.getByText('正在录制', { exact: true }).waitFor()
  if (starts.length !== 3) throw Error('refresh created another run')
  await page.getByRole('button', { name: '停止录制', exact: true }).click()
  await page.getByText('已请求停止，等待确认', { exact: true }).waitFor()
  if (stopCount !== 1) throw Error('stop request duplicated')
  run = { ...run, state: 'recorded', manifest: { closed: true }, stop_requested: false }
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByText('录制完成，正在导入材料', { exact: true }).waitFor()
  run = { ...run, material_id: mid, job_status: 'succeeded', import_status: 'imported' }
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByRole('heading', { name: '合成样本.mp4' }).waitFor()
  await page.getByRole('button', { name: '手动开始本地转写', exact: true }).click()
  await page.getByText('合成转写契约验证', { exact: false }).waitFor()
  if (
    asrCalls.length !== 1 ||
    asrCalls[0].material_id !== mid ||
    asrCalls[0].allow_network !== false
  )
    throw Error('ASR must use existing material offline')
  platform = 'wechat'
  run = null
  await page.reload()
  await page.getByText('直播采集测试设备', { exact: false }).waitFor()
  await page.getByRole('button', { name: '开始等待投屏', exact: true }).waitFor()
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.getByRole('heading', { name: '管理员登录' }).waitFor()
  return {
    passed: [
      'disabled gating',
      'empty source policy and specific blocker',
      'definitive rejection permits correction',
      'unknown retry idempotency',
      'refresh recovery',
      'stop confirmation',
      'import state',
      'existing material offline ASR',
      'WeChat instructions',
      'logout unmount',
    ],
    capturePosts: starts.length,
    asrPosts: asrCalls.length,
  }
}
