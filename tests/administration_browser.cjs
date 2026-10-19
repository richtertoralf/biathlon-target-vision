// Administration without RTSP: camera CRUD, lane grid for 4/10/20 lanes, sessions, ergonomics.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');

async function freePort(){return new Promise(resolve=>{const server=net.createServer();server.listen(0,'127.0.0.1',()=>{const {port}=server.address();server.close(()=>resolve(port));});});}
async function startServer(lanes){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'btv-admin-')),port=await freePort();
 const process_=spawn('.venv/bin/python',['-m','biathlon_target_vision','--lanes',String(lanes),'--data-dir',directory,'--port',String(port)]);
 let logs='';process_.stderr.on('data',value=>logs+=value);
 const url=`http://127.0.0.1:${port}`;
 for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)return {url,directory,process:process_};}catch{}await new Promise(r=>setTimeout(r,100));}
 throw Error('Server nicht gestartet: '+logs);
}
async function stopServer(server){server.process.kill();await new Promise(resolve=>server.process.exitCode!==null?resolve():server.process.once('exit',resolve));fs.rmSync(server.directory,{recursive:true,force:true});}
const json=async(url)=> (await fetch(url,{cache:'no-store'})).json();

// Every visible control must be large enough for touch use and nothing may scroll sideways.
async function checkErgonomics(page,name){
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,name+': horizontal overflow');
 assert.ok(await page.evaluate(()=>parseFloat(getComputedStyle(document.body).fontSize))>=16,name+': font size');
 const small=await page.evaluate(()=>[...document.querySelectorAll('main button, main input:not([type=checkbox]), main summary, .tabs a, .link-row a')]
  .filter(node=>node.offsetParent!==null&&node.getBoundingClientRect().height<44).map(node=>node.outerHTML.slice(0,80)));
 assert.deepEqual(small,[],name+': controls below 44 px');
 fs.mkdirSync('.test-artifacts',{recursive:true});await page.screenshot({path:`.test-artifacts/admin-${name}.png`,fullPage:true});
}

(async()=>{
 const browser=await chromium.launch({headless:true});const errors=[];
 try{
  // Overview with 4, 10 and 20 lanes on desktop, tablet and phone.
  for(const lanes of [4,10,20]){
   const server=await startServer(lanes);
   try{
    for(const [device,viewport] of [['desktop',{width:1366,height:900}],['tablet',{width:768,height:1024}],['phone',{width:390,height:844}]]){
     const context=await browser.newContext({viewport,hasTouch:device!=='desktop'});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
     await page.goto(server.url+'/admin#lanes');await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
     await expect(page.locator('.lane-tile')).toHaveCount(lanes);
     await checkErgonomics(page,`${lanes}-lanes-${device}`);
     if(lanes===20&&device==='desktop'){
      const rows=new Set(await page.locator('.lane-tile').evaluateAll(tiles=>tiles.map(tile=>Math.round(tile.getBoundingClientRect().top))));
      assert.ok(rows.size<=4,'20 Bahnen auf dem Desktop in höchstens vier Reihen statt einer langen Liste');
      for(const tab of ['cameras','sessions']){await page.locator(`[data-tab=${tab}]`).click();await expect(page.locator('#'+tab)).toBeVisible();await checkErgonomics(page,`${tab}-${device}`);}
     }
     await context.close();
    }
   }finally{await stopServer(server);}
  }

  // Full administration workflow with 20 lanes.
  const server=await startServer(20);
  try{
   const context=await browser.newContext({viewport:{width:1024,height:900},hasTouch:true});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
   await page.goto(server.url+'/admin');await expect(page.locator('#cameras')).toBeVisible();
   // A new camera needs an address; nothing is stored without it.
   await page.locator('#camera-name').fill('Kamera Bahnen 1–4');
   await expect(page.locator('#camera-id')).toHaveValue('kamera-bahnen-1-4');
   await page.locator('#camera-form button[type=submit]').click();
   await expect(page.locator('#status')).toHaveAttribute('data-error','');assert.deepEqual((await json(server.url+'/api/cameras')).cameras,[]);
   const secret='rtsp://admin:geheim@127.0.0.1:9/stream1';
   await page.locator('#camera-url').fill(secret);
   for(const lane of [1,2,3,4])await page.locator(`#camera-lanes [data-lane="${lane}"]`).click();
   await page.locator('#camera-form button[type=submit]').click();await expect(page.locator('#status')).toHaveText('Kamera gespeichert.');
   await expect(page.locator('#camera-address-value')).toHaveText('rtsp://***@127.0.0.1:9/stream1');
   await expect(page.locator('#camera-url')).toHaveValue('');
   assert.doesNotMatch(await page.content(),/geheim/,'Zugangsdaten erscheinen nicht in der Seite');
   await expect(page.locator('#calibrations a')).toHaveCount(4);
   await expect(page.locator('#camera-connection')).toHaveAttribute('data-connected','false');
   // Second camera: lanes of the first camera cannot be assigned twice.
   await page.locator('#new-camera').click();await page.locator('#camera-name').fill('Kamera Bahnen 5–8');
   await expect(page.locator('#camera-lanes [data-lane="1"]')).toBeDisabled();
   await page.locator('#camera-id').fill('cam-b');await page.locator('#camera-url').fill('rtsp://127.0.0.1:9/b');
   for(const lane of [5,6,7,8])await page.locator(`#camera-lanes [data-lane="${lane}"]`).click();
   await page.locator('#camera-form button[type=submit]').click();await expect(page.locator('#status')).toHaveText('Kamera gespeichert.');
   await expect(page.locator('#camera-list [data-camera]')).toHaveCount(2);
   // Editing name and lanes without a new address keeps the stored credentials.
   await page.locator('[data-camera="kamera-bahnen-1-4"]').click();await expect(page.locator('#camera-id')).toHaveJSProperty('readOnly',true);
   await page.locator('#camera-name').fill('Kamera Nord');await page.locator('#camera-lanes [data-lane="4"]').click();
   await page.locator('#camera-form button[type=submit]').click();await expect(page.locator('#status')).toHaveText('Kamera gespeichert.');
   let config=JSON.parse(fs.readFileSync(path.join(server.directory,'config.json'),'utf8'));
   const north=config.cameras.find(camera=>camera.id==='kamera-bahnen-1-4');
   assert.deepEqual([north.name,north.url,north.lane_ids],['Kamera Nord',secret,[1,2,3]]);
   await page.locator('#camera-url').fill('rtsp://10.0.0.1:9/neu');await page.locator('#camera-form button[type=submit]').click();
   await expect(page.locator('#camera-address-value')).toHaveText('rtsp://10.0.0.1:9/neu');
   // Removal needs a second tap.
   await page.locator('[data-camera="cam-b"]').click();await page.locator('#remove').click();
   await expect(page.locator('#remove')).toHaveText('Wirklich entfernen?');assert.equal((await json(server.url+'/api/cameras')).cameras.length,2);
   await page.locator('#remove').click();await expect(page.locator('#status')).toHaveText('Kamera entfernt.');
   await expect(page.locator('#camera-list [data-camera]')).toHaveCount(1);

   // Lanes: status in the grid, details and source switch only after selection.
   await page.locator('[data-tab=lanes]').click();
   await expect(page.locator('.lane-tile[data-lane="1"]')).toHaveAttribute('data-capture','fault');
   await expect(page.locator('.lane-tile[data-lane="1"]')).toContainText('Kamera getrennt');
   await expect(page.locator('.lane-tile[data-lane="10"]')).toContainText('Keine Kamera');
   await expect(page.locator('#lane-detail')).toBeHidden();
   await page.locator('.lane-tile[data-lane="1"]').click();await expect(page.locator('#lane-detail')).toContainText('Noch nicht kalibriert');
   const source=page.locator('[data-source-lane="1"]');await expect(source).toBeChecked();await source.uncheck();
   await expect.poll(async()=> (await json(server.url+'/api/state')).lanes['1'].mode).toBe('manual');
   await expect(page.locator('.lane-tile[data-lane="1"]')).toContainText('Automatik gesperrt');
   await expect(source).not.toBeChecked();await source.check();
   await expect.poll(async()=> (await json(server.url+'/api/state')).lanes['1'].mode).toBe('automatic');
   await expect(page.locator('#lane-detail .disc.unknown')).toHaveCount(5);
   await page.locator('#lane-detail [data-close]').click();await expect(page.locator('#lane-detail')).toBeHidden();

   // Sessions: rename, explicit confirmation, archive.
   await page.locator('[data-tab=sessions]').click();
   await page.locator('#session-name').fill('Training');await page.locator('#rename-session button').click();
   await expect(page.locator('#current-session')).toContainText('Training');
   const oldId=(await json(server.url+'/api/state')).session_id;
   await page.locator('#new-session-name').fill('Arber Test');await page.locator('#start-session-button').click();
   assert.equal((await json(server.url+'/api/state')).session_id,oldId,'Ohne Bestätigung kein Wechsel');
   await page.locator('#confirm-session').check();await page.locator('#start-session-button').click();
   await expect(page.locator('#session-status')).toContainText('Neue Sitzung gestartet');
   await expect(page.locator('#current-session')).toContainText('Arber Test');
   await page.locator('details summary').click();await expect(page.locator('#session-archives a')).toContainText('Training');
   // Camera configuration survives the session change; reloading keeps the selected area.
   await page.reload();await expect(page.locator('#sessions')).toBeVisible();
   assert.equal((await json(server.url+'/api/cameras')).cameras.length,1);
   // A lost server connection is shown clearly.
   await context.setOffline(true);await expect(page.locator('#connection')).toHaveAttribute('data-status','offline');
   await context.setOffline(false);await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
   await context.close();
  }finally{await stopServer(server);}
  assert.deepEqual(errors,[]);
  console.log('Administration: Kameras, 4/10/20 Bahnen, Bahndetails, Sitzungen und Ergonomie erfolgreich.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
