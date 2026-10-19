// Monitor aktualisiert echte Zielpositionen ohne Eingabemöglichkeiten.
const {chromium, expect} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
const {spawn} = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
(async () => {
 const dir = fs.mkdtempSync(path.join(os.tmpdir(),'btv-monitor-'));
 const reservation = net.createServer(); await new Promise(r=>reservation.listen(0,'127.0.0.1',r));
 const port=reservation.address().port; await new Promise(r=>reservation.close(r));
 const server=spawn('.venv/bin/python',['-m','biathlon_target_vision','--port',String(port),'--data-dir',dir,'--lanes','2']);
 const url=`http://127.0.0.1:${port}`; let browser;
 try {
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{} await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true}); const page=await browser.newPage(); await page.goto(url+'/monitor');
  await expect(page.locator('#connection')).toHaveAttribute('data-status','online'); await expect(page.locator('.lane')).toHaveCount(2);
  await expect(page.locator('button,input,select')).toHaveCount(0);
  await fetch(url+'/api/observations',{method:'POST',headers:{'Content-Type':'application/json','X-Session-ID':(await(await fetch(url+'/api/state')).json()).session_id},body:JSON.stringify({kind:'target',lane_id:1,target_id:5,state:'fallen',source:'test',observed_at:'2026-10-17T12:00:00Z'})});
  await expect(page.locator('#lane-1 .target').nth(4)).toHaveAttribute('data-state','fallen');
  await expect(page.locator('#lane-1 .fallen')).toHaveCount(1);
  await expect(page.locator('#lane-1 .unknown')).toHaveCount(4);
  console.log('Monitor-Browserprüfung erfolgreich.');
 } finally {if(browser)await browser.close();server.kill();await new Promise(r=>server.on('exit',r));fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
