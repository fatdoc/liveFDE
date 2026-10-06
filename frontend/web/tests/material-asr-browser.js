// Synthetic API and metadata only. No actual media, ASR, LLM, or capture calls.
async page=>{
 let settings={revision:1,provider:'local',privacy:'local_only',allow_cloud_fallback:false,speaker:false,emotion:false,punctuation:true},submitted=[],saves=0,historyLoads=0,unknown=false,successor=false
 const run=(id)=>({capture_run_id:id,session_id:'s',platform:'douyin',source_ref:'',state:'failed',job_status:'failed',stop_requested:false,material_id:null,import_status:'none',error_code:'synthetic_failure',manifest:null})
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname;let data
  if(p.endsWith('/auth/me'))data={user:{id:'a',workspace_id:'w',display_name:'合成管理员',role:'admin'},csrf_token:'fixture'}
  else if(p.endsWith('/sessions/s'))data={id:'s',title:'合成场次',platform:'douyin',session_local_date:'2026-10-07'}
  else if(p.endsWith('/sessions/s/materials'))data={items:[{material:{material_id:'m',filename:'fixture.mp4',media_type:'video/mp4',size_bytes:1}}]}
  else if(p.endsWith('/capture/health'))data={enabled:false,providers:{},execution:{ready:false}}
  else if(p.endsWith('/capture/runs')){if(req.method()!=='GET')throw Error('capture mutation');if(url.searchParams.has('cursor')){historyLoads++;data={items:[{...run('oldest'),job_status:'running',state:'recording',error_code:null}],next_cursor:null}}else data={items:[run('latest'),run('old')],next_cursor:'older'}}
  else if(p.endsWith('/capture/runs/oldest'))data={...run('oldest'),job_status:'running',state:'recording',error_code:null}
  else if(p.endsWith('/asr/settings')){if(req.method()==='PUT'){saves++;const body=req.postDataJSON();if(body.expected_revision!==settings.revision)throw Error('revision');settings={...body,revision:settings.revision+1};delete settings.expected_revision}data=settings}
  else if(p.endsWith('/asr/providers'))data={providers:[{provider:'local',configured:true,reason:null,max_duration_seconds:14400,max_audio_bytes:null,network_checked:false},{provider:'tencent',configured:true,reason:null,max_duration_seconds:156,max_audio_bytes:5000000,network_checked:false}]}
  else if(p.endsWith('/asr/transcriptions')){submitted.push(req.postDataJSON());if(unknown)return route.abort('failed');data={id:'job1',revision:4,can_retry:true,status:'failed',error:{code:'synthetic_failure'}}}
  else if(p.endsWith('/asr/transcriptions/job1'))data={successor_job_id:successor?'job2':null,job:{id:'job1',revision:4,can_retry:true,status:'failed',error:{code:'synthetic_failure'}},result:null}
  else if(p.endsWith('/asr/transcriptions/job2'))data={job:{id:'job2',revision:1,status:'succeeded',error:null},result:null}
  else if(p.endsWith('/content'))return route.fulfill({status:200,body:''})
  else throw Error('unexpected API '+p)
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto('http://127.0.0.1:5207/settings');await page.evaluate(()=>sessionStorage.clear());await page.goto('http://127.0.0.1:5207/sessions/s')
 const card=page.getByRole('article',{name:'材料：fixture.mp4',exact:true}),start=()=>card.getByRole('button',{name:'手动开始腾讯云转写',exact:true})
 await card.getByRole('heading',{name:'材料转写',exact:true}).waitFor()
 const history=page.locator('details').filter({has:page.locator('summary').filter({hasText:'历史采集记录'})}).first()
 if(await history.getAttribute('open')!==null)throw Error('history default expanded')
 if(await page.getByText('采集编号 old',{exact:true}).isVisible())throw Error('historical failure visible')
 await history.locator('summary').first().click();await page.getByRole('button',{name:'加载更早记录',exact:true}).click();await page.getByText('采集编号 oldest',{exact:true}).waitFor()
 await page.getByRole('button',{name:'刷新状态',exact:true}).click();await page.getByText('采集编号 oldest',{exact:true}).waitFor();if(historyLoads!==1)throw Error('paging duplicate');await page.getByRole('button',{name:'停止录制',exact:true}).waitFor()
 await card.getByRole('combobox',{name:'选择转写服务',exact:true}).selectOption('tencent')
 if(!await start().isDisabled())throw Error('unsaved cloud enabled')
 const save=card.getByRole('button',{name:'保存转写服务设置',exact:true})
 if(!await save.isDisabled())throw Error('privacy silently changed')
 await card.getByText('允许当前工作区使用云端处理；每次任务仍需单独授权',{exact:true}).click();await save.click();await card.getByText('工作区转写服务已保存；尚未提交转写。',{exact:true}).waitFor()
 if(saves!==1||submitted.length||settings.privacy!=='cloud_allowed')throw Error('save started job or privacy not saved')
 if(!await start().isDisabled())throw Error('unknown duration enabled')
 await page.waitForFunction(()=>document.querySelector('video')?.error!==null)
 const duration=async n=>card.locator('video').evaluate((node,n)=>{Object.defineProperties(node,{error:{get:()=>null,configurable:true},duration:{get:()=>n,configurable:true},readyState:{get:()=>1,configurable:true}});node.dispatchEvent(new Event('loadedmetadata'))},n)
 await duration(200);await card.getByText(/材料超过当前服务 156 秒上限/).waitFor();if(!await start().isDisabled())throw Error('long cloud enabled')
 await duration(60)
 await card.getByText('授权本次将音频发送腾讯云并接受费用',{exact:true}).click();await card.getByLabel('金额预算（美元）',{exact:true}).fill('0.5')
 await start().evaluate(el=>{el.click();el.click()});await card.getByText('转写失败',{exact:true}).waitFor()
 if(submitted.length!==1||submitted[0].expected_revision!==2||submitted[0].allow_network!==true||submitted[0].max_requests!==1||submitted[0].max_cost_usd!==0.5)throw Error('cloud payload invalid')
 await card.getByRole('combobox',{name:'选择转写服务',exact:true}).selectOption('local');await card.getByRole('button',{name:'保存转写服务设置',exact:true}).click();await card.getByText('工作区转写服务已保存；尚未提交转写。',{exact:true}).waitFor()
 unknown=true;await card.getByRole('button',{name:'按所选服务重新转写',exact:true}).click();await card.getByText('提交结果尚未确认，已阻止重复提交。请核查服务器任务，取得任务编号后恢复查询。',{exact:true}).waitFor()
 if(submitted.length!==2||submitted[1].allow_network!==false||submitted[1].max_requests!==null||submitted[1].previous_job_id!=='job1'||submitted[1].expected_previous_revision!==4)throw Error('local grant invalid')
 await page.reload();await card.getByText('提交结果尚未确认，已阻止重复提交。请核查服务器任务，取得任务编号后恢复查询。',{exact:true}).waitFor();if(!await card.getByRole('button',{name:'手动开始本地转写',exact:true}).isDisabled()||submitted.length!==2)throw Error('unknown resubmitted')
 successor=true;await card.getByLabel('恢复查询任务编号',{exact:true}).fill('job1');await card.getByRole('button',{name:'查看后续任务',exact:true}).click();await card.getByText('转写完成',{exact:true}).waitFor();if(submitted.length!==2)throw Error('successor query submitted new task')
 return {passed:['history collapsed/paged/preserved','explicit workspace privacy save','save no task','unknown/long duration cloud blocked','single cloud authorized payload','local no cloud grant','unknown refresh no retry','failed job authorized successor','existing successor read only','older active stays visible'],submitted:submitted.length}
}
