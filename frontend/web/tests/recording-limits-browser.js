// All API traffic is intercepted; creates no real recording.
async page=>{
 let posts=[],mode='lost',created=null
 const limits={max_seconds:14400,max_bytes:17179869184,duration_presets_seconds:[1800,3600,7200,14400],default_duration_seconds:7200,default_max_bytes:8589934592,min_free_bytes:2147483648,manual_upload_max_bytes:536870912,available_max_bytes:10000000000,import_overhead_copies:2,fragmented_mp4:true,resumable_recording:false,size_overrun_bytes:67108864}
 await page.route('**/api/v1/**',async route=>{const req=route.request(),p=new URL(req.url()).pathname;let data
 if(p.endsWith('/auth/me'))data={user:{id:'a',workspace_id:'recording-test',display_name:'合成管理员',role:'admin'},csrf_token:'fixture'}
 else if(p.endsWith('/sessions/r'))data={id:'r',title:'录制限制合成验收',platform:'douyin',session_local_date:'2026-10-07'}
 else if(p.endsWith('/sessions/r/materials'))data={items:[]}
 else if(p.endsWith('/capture/health'))data={enabled:true,ffmpeg_ready:true,ffprobe_ready:true,limits,execution:{ready:true,automatic_dispatch:true},providers:{douyin:{start_ready:true}}}
 else if(p.endsWith('/capture/runs')){if(req.method()==='POST'){posts.push({body:req.postDataJSON(),key:req.headers()['idempotency-key']});if(mode==='lost')return route.abort('failed');data={capture_run_id:'new',session_id:'r',state:'queued',job_status:'queued',stop_requested:false,material_id:null,manifest:null,recording_limits:{max_seconds:1800,max_bytes:2097152},recorded_bytes:null,elapsed_seconds:null};created=data}else data={items:created?[created]:[],next_cursor:null}}
 else throw Error('unexpected '+p)
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})})
 await page.goto('http://127.0.0.1:5207/settings');await page.evaluate(()=>sessionStorage.clear());await page.goto('http://127.0.0.1:5207/sessions/r')
 await page.getByLabel('抖音电脑端直播间链接',{exact:true}).fill('https://live.douyin.com/123')
 await page.locator('summary').filter({hasText:'本次录制限制'}).click()
 const seconds=page.getByLabel('最长录制时间（分钟）',{exact:true}),bytes=page.getByLabel('文件容量上限（GiB）',{exact:true}),start=()=>page.getByRole('button',{name:'开始录制',exact:true})
 if(await seconds.inputValue()!=='120'||await bytes.inputValue()!=='8')throw Error('server defaults ignored')
 await seconds.fill('241');if(!await start().isDisabled())throw Error('server duration limit ignored')
 await page.getByRole('combobox',{name:'时长预设',exact:true}).selectOption('1800');await bytes.fill('10');if(!await start().isDisabled())throw Error('space budget ignored')
 await bytes.fill('0.0005');if(!await start().isDisabled())throw Error('below 1 MiB enabled');await bytes.fill('0.001953125');await start().evaluate(el=>{el.click();el.click()});await page.getByRole('button',{name:'重试确认同次采集',exact:true}).waitFor()
 if(posts.length!==1||posts[0].body.duration_seconds!==1800||posts[0].body.max_bytes!==2097152)throw Error('selected values not frozen')
 await page.reload();await page.getByRole('button',{name:'重试确认同次采集',exact:true}).waitFor();mode='ok';await page.getByRole('button',{name:'重试确认同次采集',exact:true}).click();await page.getByRole('button',{name:'停止录制',exact:true}).waitFor()
 if(posts.length!==2||JSON.stringify(posts[0])!==JSON.stringify(posts[1]))throw Error('pending retry changed choices or key')
 return {passed:['server defaults','duration and disk limits','preset','double click single POST','pending reload immutable payload/key','current stop visible'],syntheticPosts:posts.length}
}
