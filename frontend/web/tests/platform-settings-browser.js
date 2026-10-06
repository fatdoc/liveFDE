// Synthetic contract checks only. Requires local preview on 5205, never a platform request.
async (page) => {
 let state={revision:'0',configured:false,status:'not_configured',checked_at:null,checked_source:null,last_error:null,service_ready:false,checked_state:null}
 let checks=0, saves=0, clearCalls=0, conflict=false, empty=false, latestRevision='0'
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let data,status=200
  if(path.endsWith('/auth/me'))data={user:{id:'synthetic-admin',workspace_id:'synthetic-workspace',display_name:'合成验收管理员',role:'admin'},csrf_token:'synthetic'}
  else if(path.endsWith('/capture/settings/douyin/check')){
   checks++;const body=req.postDataJSON();if(body.expected_revision!==state.revision)throw Error('check wrong revision')
   state={...state,status:empty?'check_failed':'verified',checked_at:'2026-10-07T00:00:00Z',checked_source:body.source_ref,checked_state:empty?null:'not_live',last_error:empty?'source_empty_response':null};data=state
  }else if(path.endsWith('/capture/settings/douyin')){
   if(req.method()==='GET')data=state
   else{
    const body=req.postDataJSON();if(body.expected_revision!==latestRevision)throw Error('mutation revision mismatch')
    if(conflict){conflict=false;state={...state,revision:'changed-elsewhere'};status=409;data={error:{code:'revision_conflict'}}}
    else if(req.method()==='PUT'){saves++;if(!body.cookie)throw Error('missing cookie');state={...state,configured:true,revision:`saved-${saves}`,status:'unverified',checked_at:null,checked_source:null,checked_state:null,last_error:null};data=state}
    else if(req.method()==='DELETE'){clearCalls++;state={...state,configured:false,revision:'cleared',status:'not_configured',checked_at:null,checked_source:null,checked_state:null,last_error:null};data=state}
   }
  } else throw Error('unexpected API '+path)
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto('http://127.0.0.1:5205/settings')
 await page.getByRole('button',{name:'平台接入',exact:true}).click()
 await page.getByText('未配置',{exact:true}).waitFor()
 if(!await page.getByRole('button',{name:'保存 Cookie',exact:true}).isDisabled())throw Error('empty save enabled')
 await page.getByLabel('抖音 Cookie',{exact:true}).fill('synthetic_cookie=not-a-real-secret')
 await page.getByRole('button',{name:'保存 Cookie',exact:true}).click()
 await page.getByText('已保存 · 尚未验证',{exact:true}).waitFor()
 if(await page.getByLabel('新的抖音 Cookie',{exact:true}).inputValue())throw Error('cookie not cleared after save')
 if(await page.locator('body').innerText().then(t=>t.includes('synthetic_cookie=')))throw Error('secret displayed')
 latestRevision=state.revision
 await page.getByPlaceholder('https://live.douyin.com/数字房间号').fill('https://live.douyin.com/123456')
 await page.getByText('服务未就绪',{exact:true}).waitFor()
 if(await page.getByRole('button',{name:'仅检查连接',exact:true}).isDisabled())throw Error('offline recorder incorrectly blocked parser check')
 await page.getByRole('button',{name:'仅检查连接',exact:true}).click()
 await page.getByText('当次解析已验证',{exact:true}).waitFor()
 await page.getByText('当次解析：尚未开播，仍属于解析成功。',{exact:false}).waitFor()
 empty=true
 await page.getByRole('button',{name:'仅检查连接',exact:true}).click()
 await page.getByText('检查未通过',{exact:true}).waitFor()
 await page.getByText('平台返回空响应，无法据此判断 Cookie 是否过期。',{exact:true}).waitFor()
 conflict=true
 await page.getByLabel('新的抖音 Cookie',{exact:true}).fill('synthetic_update=not-a-real-secret')
 await page.getByRole('button',{name:'更新 Cookie',exact:true}).click()
 await page.getByText('设置版本已变化或另一次检查正在进行。',{exact:false}).waitFor()
 if(!await page.getByRole('button',{name:'更新 Cookie',exact:true}).isDisabled())throw Error('conflict did not block mutation')
 await page.getByRole('button',{name:'刷新状态',exact:true}).click()
 latestRevision=state.revision
 await page.getByRole('button',{name:'更新 Cookie',exact:true}).click()
 await page.getByText('已保存 · 尚未验证',{exact:true}).waitFor()
 latestRevision=state.revision
 await page.getByRole('button',{name:'清除 Cookie',exact:true}).click()
 await page.getByRole('button',{name:'确认清除 Cookie',exact:true}).click()
 await page.getByText('未配置',{exact:true}).waitFor()
 if(checks!==2||saves!==2||clearCalls!==1)throw Error('unexpected automatic request')
 return {passed:['parser check independent of recorder readiness','save clears secret','saved differs from verified','offline parse success','empty response not expired','revision conflict blocks then refreshes','clear revision','no automatic check'],checks,saves,clearCalls}
}
