// Synthetic media metadata/API test; no model calls or real platform requests.
async (page) => {
 let posts=0
 const sid='timeline-session',scope='timeline-workspace'
 const materials=[{material_id:'media-a',filename:'A.mp4',media_type:'video/mp4',size_bytes:100},{material_id:'media-b',filename:'B.wav',media_type:'audio/wav',size_bytes:100}]
 await page.route('**/api/v1/**', async route=>{
  const req=route.request(),p=new URL(req.url()).pathname;let data
  if(req.method()==='POST'){if(!p.endsWith('/asr/transcriptions'))throw Error('unexpected POST');posts++;const body=req.postDataJSON();await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({id:body.material_id==='media-a'?'job-a':'job-b',status:'queued'})});return}
  if(p.endsWith('/auth/me'))data={user:{id:'timeline-admin',workspace_id:scope,display_name:'时间戳合成验收',role:'admin'},csrf_token:'synthetic'}
  else if(p.endsWith(`/sessions/${sid}`))data={id:sid,title:'双材料定位验收',platform:'other',session_local_date:'2026-10-07'}
  else if(p.endsWith(`/sessions/${sid}/materials`))data={items:materials.map(material=>({material})),total:2,limit:100,offset:0}
  else if(p.endsWith('/capture/health'))data={enabled:false,providers:{},execution:{ready:false}}
  else if(p.endsWith('/capture/runs'))data={items:[],next_cursor:null}
  else if(p.endsWith('/asr/settings'))data={revision:1,provider:'local'}
  else if(p.includes('/asr/transcriptions/')){
   const a=p.endsWith('job-a');data={job:{id:a?'job-a':'job-b',status:'succeeded',error:null},result:{provider:'local',source:'local',model:'synthetic-test',synthetic:true,complete:true,segments:[{id:'valid',start_ms:a?1250:4500,end_ms:a?2500:6000,text:a?'A段':'B段',timestamp_source:a?'vad':'provider'},{id:'unknown',start_ms:null,end_ms:null,text:'未知段'},{id:'reversed',start_ms:3000,end_ms:1000,text:'逆序段'},{id:'beyond',start_ms:7000,end_ms:9000,text:'越界段'}]}}
  } else if(p.endsWith('/content')){await route.fulfill({status:200,contentType:'application/octet-stream',body:''});return}
  else throw Error('unexpected API '+p)
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto('http://127.0.0.1:5205/settings')
 await page.evaluate(scope=>{sessionStorage.setItem(`material-asr:${scope}:media-a`,'job-a');sessionStorage.setItem(`material-asr:${scope}:media-b`,'job-b')},scope)
 await page.goto(`http://127.0.0.1:5205/sessions/${sid}`)
 const a=page.getByRole('article',{name:'材料：A.mp4',exact:true}),b=page.getByRole('article',{name:'材料：B.wav',exact:true})
 await a.getByText('A段',{exact:true}).waitFor();await b.getByText('B段',{exact:true}).waitFor()
 if(!await a.getByRole('button',{name:'00:01.250 — 00:02.500',exact:true}).isDisabled())throw Error('metadata-unavailable seek enabled')
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('video,audio')).every(n=>n.error!==null))
 await page.locator('video,audio').evaluateAll(nodes=>nodes.forEach(node=>{let time=0;Object.defineProperties(node,{error:{get:()=>null,configurable:true},duration:{get:()=>8,configurable:true},readyState:{get:()=>1,configurable:true},currentTime:{get:()=>time,set:v=>{time=v},configurable:true}});node.dispatchEvent(new Event('loadedmetadata'))}))
 if(!await a.getByRole('button',{name:'00:01.250 — 00:02.500',exact:true}).isDisabled())throw Error('legacy restored job enabled seek')
 await a.getByRole('textbox').fill('job-b')
 await a.getByText('B段',{exact:true}).waitFor()
 if(!await a.getByRole('button',{name:'00:04.500 — 00:06.000',exact:true}).isDisabled())throw Error('other material manual job enabled seek')
 if(posts!==0)throw Error('restore/manual query submitted')
 await page.evaluate(()=>sessionStorage.clear())
 await page.reload()
 await a.getByRole('button',{name:'手动开始本地转写',exact:true}).click()
 await b.getByRole('button',{name:'手动开始本地转写',exact:true}).click()
 await a.getByText('A段',{exact:true}).waitFor();await b.getByText('B段',{exact:true}).waitFor()
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('video,audio')).every(n=>n.error!==null))
 await page.locator('video,audio').evaluateAll(nodes=>nodes.forEach(node=>{let time=0;Object.defineProperties(node,{error:{get:()=>null,configurable:true},duration:{get:()=>8,configurable:true},readyState:{get:()=>1,configurable:true},currentTime:{get:()=>time,set:v=>{time=v},configurable:true}});node.dispatchEvent(new Event('loadedmetadata'))}))
 await a.getByRole('button',{name:'00:01.250 — 00:02.500',exact:true}).click()
 let times=await page.locator('video,audio').evaluateAll(nodes=>nodes.map(n=>({time:n.currentTime,paused:n.paused})))
 if(times[0].time!==1.25||times[1].time!==0||times.some(t=>!t.paused))throw Error('first material seek leaked or autoplayed')
 await b.getByRole('button',{name:'00:04.500 — 00:06.000',exact:true}).click()
 times=await page.locator('video,audio').evaluateAll(nodes=>nodes.map(n=>({time:n.currentTime,paused:n.paused})))
 if(times[0].time!==1.25||times[1].time!==4.5||times.some(t=>!t.paused))throw Error('second material seek leaked or autoplayed')
 for(const group of [a,b])for(const label of ['时间未知 — 时间未知','00:03.000 — 00:01.000','00:07.000 — 00:09.000'])if(!await group.getByRole('button',{name:label,exact:true}).isDisabled())throw Error('invalid range seek enabled')
 await a.getByText('VAD 语音区间边界，非逐词对齐',{exact:true}).waitFor();await b.getByText('识别服务提供的时间戳，未验证逐词对齐',{exact:true}).waitFor()
 if(posts!==2)throw Error('unexpected submission count')
 return {passed:['isolated material players','seek without autoplay','metadata wait','invalid ranges disabled','VAD/provider wording','restore query without submit','unverified restored/manual job cannot seek','two synthetic submissions bind materials'],times,posts}
}
