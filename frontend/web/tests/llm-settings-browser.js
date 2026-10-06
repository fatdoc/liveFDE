// Entire API surface intercepted. Fixture values are synthetic, no provider traffic.
async page => {
 let state={revision:'1',base_url:'',model:'',timeout_seconds:60,configured:false,status:'not_configured',checked_at:null,last_error:null,usage:null,debug_http:false,analysis_enabled:false}
 let mode='ok',checks=0,saves=[]
 const reply=(route,data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname,method=req.method()
  if(path==='/api/v1/auth/me')return reply(route,{user:{id:'synthetic-admin',workspace_id:'llm-fixture',display_name:'合成管理员',role:'admin'},csrf_token:'synthetic'})
  if(!path.startsWith('/api/v1/llm/settings'))throw Error('Unexpected API '+path)
  if(method==='GET')return reply(route,state)
  if(req.headers()['x-csrf-token']!=='synthetic')throw Error('missing CSRF')
  const body=req.postDataJSON()
  if(method==='PUT'){
   if(mode==='409')return reply(route,{error:{code:'revision_conflict'}},409)
   if(mode==='401')return reply(route,{error:{code:'unauthorized'}},401)
   saves.push(body);state={...state,...body,revision:String(Number(state.revision)+1),configured:state.configured||!!body.api_key,status:'unverified',usage:null,checked_at:null};delete state.api_key;delete state.expected_revision
   if(mode==='save-lost')return route.abort('failed')
   return reply(route,state)
  }
  if(method==='DELETE'){state={...state,revision:String(Number(state.revision)+1),configured:false,status:'not_configured',usage:null,checked_at:null};if(mode==='clear-lost')return route.abort('failed');return reply(route,state)}
  if(path.endsWith('/check')){
   if(mode==='busy')return reply(route,{error:{code:'llm_settings_busy'}},409)
   checks++;if(!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(body.request_id)||body.expected_revision!==state.revision)throw Error('invalid check binding')
   if(mode==='unknown'){state={...state,status:'unknown'};return route.abort('failed')}
   await new Promise(r=>setTimeout(r,150));state={...state,status:'verified',checked_at:'2026-10-07T12:00:00Z',usage:{prompt_tokens:4,completion_tokens:1,total_tokens:5}}
   return reply(route,state)
  }
  throw Error('unexpected request')
 })
 const open=async()=>{await page.goto('http://127.0.0.1:5206/settings');await page.getByRole('button',{name:'大模型配置',exact:true}).click();await page.getByLabel('接口地址',{exact:true}).waitFor()}
 const test=()=>page.getByRole('button',{name:'测试已保存配置（一次请求）',exact:true})
 const save=()=>page.getByRole('button',{name:'保存大模型配置',exact:true})
 await open()
 await page.getByLabel('接口地址',{exact:true}).fill('https://example.com/v1');await page.getByLabel('模型名称',{exact:true}).fill('synthetic-model');await page.getByLabel('API 密钥',{exact:true}).fill('synthetic-secret')
 if(!await test().isDisabled())throw Error('dirty test enabled')
 await save().click();await page.getByText('已保存，尚未进行连接测试。密钥输入已清空。',{exact:true}).waitFor()
 if(await page.getByLabel('API 密钥',{exact:true}).inputValue()!==''||checks)throw Error('save leaked input or tested')
 await open();if(await page.getByLabel('模型名称',{exact:true}).inputValue()!=='synthetic-model'||await page.getByLabel('接口地址',{exact:true}).inputValue()!=='https://example.com/v1')throw Error('refresh lost settings')
 await page.getByLabel('超时（秒）',{exact:true}).fill('45');await save().click();await page.getByText('已保存，尚未进行连接测试。密钥输入已清空。',{exact:true}).waitFor()
 if('api_key' in saves[1])throw Error('empty key sent')
 mode='busy';await test().click();await page.getByText('配置正在处理，请稍后读取状态。',{exact:true}).waitFor();mode='ok'
 await test().evaluate(el=>{el.click();el.click()});await page.getByText('连接测试成功',{exact:true}).waitFor()
 if(checks!==1)throw Error('double submission');await page.getByText('Token 用量：输入 4 · 输出 1 · 总计 5',{exact:true}).waitFor()
 await page.getByLabel('模型名称',{exact:true}).fill('changed');if(!await test().isDisabled())throw Error('dirty config reuses result')
 mode='409';await save().click();await page.getByText('配置已被其他操作更新。草稿已保留，请重新读取后核对。',{exact:true}).waitFor();if(await page.getByLabel('模型名称',{exact:true}).inputValue()!=='changed')throw Error('conflict discarded draft')
 mode='ok';await page.getByRole('button',{name:'放弃草稿并重新读取',exact:true}).click();await page.getByText('已从服务器读取。',{exact:true}).waitFor()
 mode='clear-lost';await page.getByRole('button',{name:'清除已保存密钥',exact:true}).click();await page.getByText('保存或清除结果尚未确认，已阻止重复修改。请从服务器刷新核对结果。',{exact:true}).waitFor();if(!await save().isDisabled())throw Error('lost clear allows mutation');mode='ok';await page.getByRole('button',{name:'从服务器刷新',exact:true}).click();await page.getByText('已从服务器读取。',{exact:true}).waitFor();if(!await test().isDisabled()||state.base_url!=='https://example.com/v1')throw Error('clear incorrect')
 mode='save-lost';await page.getByLabel('API 密钥',{exact:true}).fill('synthetic-new');await save().click();await page.getByText('保存或清除结果尚未确认，已阻止重复修改。请从服务器刷新核对结果。',{exact:true}).waitFor();if(!await save().isDisabled())throw Error('lost save allows mutation');mode='ok';await page.getByRole('button',{name:'从服务器刷新',exact:true}).click();await page.getByText('已从服务器读取。',{exact:true}).waitFor()
 mode='unknown';await test().click();await page.getByText('测试结果未知，已禁止重复发送。请管理员核查服务器记录；刷新不会自动重试。',{exact:true}).waitFor();if(!await test().isDisabled()||checks!==2)throw Error('unknown retry enabled')
 await open();if(!await test().isDisabled()||checks!==2)throw Error('refresh retried unknown')
 const storage=await page.evaluate(()=>JSON.stringify([Object.entries(localStorage),Object.entries(sessionStorage)]));if(storage.includes('synthetic-secret')||storage.includes('synthetic-new'))throw Error('secret persisted')
 mode='401';await page.getByLabel('模型名称',{exact:true}).fill('expired');await save().click();await page.getByRole('heading',{name:'管理员登录',exact:true}).waitFor()
 return {passed:['save without network check','refresh persisted','key cleared and omitted','clear key','revision conflict preserves draft','single UUID request','usage visible','dirty disables test','unknown no retry','no secret storage','401 login','save/clear lost response GET recovery','409 busy distinct'],checks,saves:saves.length}
}
