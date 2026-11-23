const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
fs.mkdirSync(`${__dirname}/../.work`,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage();page.on('response',async r=>{if(r.url().endsWith('/tick')){const j=await r.json();if(!j.accepted)console.log('REJECT',r.request().postData(),j);}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8019/login.html?mode=signup');
  await page.locator('#signupName').fill('Teste dos vídeos');
  await page.locator('#signupEmail').fill(`video-${Date.now()}@example.com`);
  await page.locator('#signupPassword').fill('FintrackTeste2026!');
  await page.locator('#signupConfirm').fill('FintrackTeste2026!');
  await page.locator('#signupTerms').check();await page.locator('#signupSubmit').click();
  await page.waitForURL('**/avatar.html');await page.locator('#save').click();await page.waitForURL('**/app.html');
  await page.waitForFunction(()=>state.categories && state.dashboardData);
  await page.evaluate(async()=>{setPage('education');await loadEducation();});
  const api=context.request;
  assert.equal((await api.post('http://127.0.0.1:8019/api/education/planejamento/metas/check',{data:{i:0,answer:0}})).status(),403);
  assert.equal((await api.post('http://127.0.0.1:8019/api/education/investimentos/tesouro/submit',{data:{answers:[]}})).status(),403);
  const s=await (await api.post('http://127.0.0.1:8019/api/intro/planejamento/start')).json();
  const jump=await (await api.post('http://127.0.0.1:8019/api/intro/planejamento/tick',{data:{token:s.token,position:s.duration}})).json();
  assert.equal(jump.completed,false);assert.equal(jump.accepted,false);
  const anon=await browser.newContext();assert.equal((await anon.request.get('http://127.0.0.1:8019/api/intro/planejamento/media')).status(),401);await anon.close();
  const range=await api.get('http://127.0.0.1:8019/api/intro/planejamento/media',{headers:{Range:'bytes=0-1023'}});assert.equal(range.status(),206);
  for(const [module,topic] of [['planejamento','metas'],['investimentos','tesouro']]) {
   await page.evaluate(([m,t])=>openLesson(m,t),[module,topic]);
   await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);
   assert.equal(await page.locator('#introContinue').isDisabled(),true);
   await page.evaluate(()=>{document.querySelector('video').currentTime=30;});
   await page.waitForFunction(()=>{const v=document.querySelector('video');return v && !v.seeking && v.readyState>=2 && v.currentTime<1;});
   assert.ok(await page.locator('video').evaluate(v=>v.currentTime<1));
   await page.locator('video').evaluate(v=>{v.muted=true;v.play().catch(console.error);});
   if(module==='planejamento') {
    await page.waitForFunction(()=>document.querySelector('video')?.currentTime>3);await page.locator('#introBack').click();
    await page.waitForTimeout(400);await page.evaluate(()=>openLesson('planejamento','metas'));
    await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);assert.ok(await page.locator('video').evaluate(v=>v.currentTime>1));
    await page.locator('video').evaluate(v=>{v.muted=true;v.play().catch(console.error);});
   }
   await page.waitForFunction(()=>!document.querySelector('#introContinue').disabled,{},{timeout:70000}).catch(async e=>{console.log('PLAYER',await page.locator('video').evaluate(v=>({time:v.currentTime,duration:v.duration,paused:v.paused,seeking:v.seeking,ready:v.readyState,hidden:document.hidden})),await page.locator('#introStatus').textContent());throw e;});
   assert.ok(await page.locator('video').evaluate(v=>v.currentTime>=v.duration-.2));
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false);
   for(const width of [320,768,1366,390]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
   await page.screenshot({path:`${__dirname}/../.work/video-${module}-mobile.png`,fullPage:true});
   await page.locator('#introContinue').click();await page.waitForSelector('[data-go="1"]');
   assert.equal((await api.post(`http://127.0.0.1:8019/api/education/${module}/${topic}/check`,{data:{i:0,answer:module==='investimentos'?1:2100}})).status(),200);
   await page.evaluate(()=>loadEducation());
   console.log('PASS full playback, unlock and mobile:',module);
  }
  await page.reload();await page.waitForFunction(()=>state.me && state.categories);
  const data=await (await api.get('http://127.0.0.1:8019/api/education')).json();
  assert.ok(data.modules.filter(m=>['planejamento','investimentos'].includes(m.key)).every(m=>m.intro.completed));assert.deepEqual(errors,[]);
  fs.writeFileSync(`${__dirname}/video-34-results.json`,JSON.stringify({realPlaybackBoth:true,seekBlocked:true,directApiBlocked:true,authenticatedMedia:true,rangeRequests:true,resume:true,persistence:true,viewportWidths:[320,390,768,1366],errors},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
