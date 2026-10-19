const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
const path=require('path');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const results=[];
  try {
    for(const width of [320,390,768,1366]) {
      const context=await browser.newContext({viewport:{width,height:844},isMobile:width<800,hasTouch:width<800});
      const login=await context.request.post('http://127.0.0.1:8019/api/auth/login',{data:{email:'fintrack.qa@example.com',password:'FintrackTeste2026!'}});
      if(!login.ok()) throw new Error('Login failed '+login.status());
      const page=await context.newPage(); const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto('http://127.0.0.1:8019/app.html');
      await page.waitForFunction(()=>document.querySelector('#sideName').textContent!=='...');
      await page.waitForSelector('#reminderBell');
      for(const destination of ['dashboard','transactions','goals','education','finbot','classes','settings','notifications']) {
        await page.evaluate(p=>setPage(p),destination);
        await page.waitForTimeout(300);
        const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
        if(dims.scroll>dims.client+1)throw new Error(`Horizontal overflow ${width} ${destination}: ${JSON.stringify(dims)}`);
      }
      await page.waitForFunction(()=>!document.querySelector('#reminderItems').textContent.includes('Carregando'));
      await page.locator('#monthlyBudget').fill('1.500,00');
      await page.getByRole('button',{name:'Salvar preferências',exact:true}).click();
      await page.getByText('Preferências salvas.',{exact:true}).waitFor();
      await page.evaluate(()=>{document.activeElement.blur();window.scrollTo(0,0)});
      await page.screenshot({path:path.join(__dirname,`mobile-reminders-${width}.png`),fullPage:true});
      if(width<800) {
        const font=await page.locator('#monthlyBudget').evaluate(e=>parseFloat(getComputedStyle(e).fontSize));
        if(font<16)throw new Error(`Small input font ${width}: ${font}`);
        await page.locator('#mobileNavToggle').click();
        await page.locator('.nav button[data-page="dashboard"]').click();
        if(await page.locator('#mobileNavToggle').getAttribute('aria-expanded')!=='false')throw new Error('Menu failed to close');
      }else await page.evaluate(()=>setPage('dashboard'));
      await page.locator('#newTxTop').click();
      await page.locator('#txModal.open').waitFor();
      const dialog=await page.locator('#txModal .dialog').boundingBox();
      if(dialog.x<0 || dialog.x+dialog.width>width+1)throw new Error('Dialog overflows');
      await page.keyboard.press('Escape');
      if(errors.length)throw new Error(errors.join('; '));
      results.push({width,pages:8,overflow:false,errors});
      await context.close();
    }
    fs.writeFileSync(path.join(__dirname,'mobile-test-results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
