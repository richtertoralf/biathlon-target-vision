// Zwei Tablets und Monitor wechseln gemeinsam; alte Dialoge/HTTP-Antworten bleiben zurück.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');
const readline=require('node:readline'),fs=require('node:fs'),assert=require('node:assert/strict');

(async()=>{
 const fixture=spawn('.venv/bin/python',['-u','-m','tests.vision_fixture','--manual-only','--three-lanes']);
 let logs='',browser;fixture.stderr.on('data',value=>logs+=value);
 let releaseResponse;
 try{
  const line=await new Promise((resolve,reject)=>{readline.createInterface({input:fixture.stdout}).once('line',resolve);fixture.once('exit',()=>reject(Error(logs)));});
  const {url}=JSON.parse(line);
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  browser=await chromium.launch({headless:true});
  const portrait=await browser.newContext({viewport:{width:600,height:960},hasTouch:true});
  const landscape=await browser.newContext({viewport:{width:960,height:600},hasTouch:true});
  const first=await portrait.newPage(),second=await landscape.newPage(),admin=await portrait.newPage(),monitor=await landscape.newPage();
  const errors=[];for(const page of [first,second,admin,monitor])page.on('pageerror',error=>errors.push(error.message));
  const state=async()=> (await(await fetch(url+'/api/state')).json());
  const oldId=(await state()).session_id;
  for(const page of [first,second]){await page.goto(url);await expect(page.locator('#connection')).toHaveAttribute('data-status','online');}
  await second.locator('#language').selectOption('cs');
  await monitor.goto(url+'/monitor');await admin.goto(url+'/admin#sessions');
  await admin.locator('#session-name').fill('Vormittag');await admin.locator('#rename-session button').click();
  await expect(first.locator('#session-name')).toHaveText('Vormittag');
  await first.locator('#lane-1 [data-action=manual-reset]').tap();
  await first.locator('#lane-1 [data-action=occupy]').tap();
  await first.locator('#lane-1 [data-action=bib]').tap();await first.locator('#bib-input').fill('42');await first.locator('#confirm-bib').tap();
  await expect(second.locator('#lane-1 .bib')).toHaveText('42');
  // Die Serverantwort wird erst nach dem Sitzungswechsel an dieses Tablet geliefert.
  let heldResolve;const held=new Promise(resolve=>heldResolve=resolve);
  const gate=new Promise(resolve=>releaseResponse=resolve);
  await second.route('**/api/lanes/1/manual-target',async route=>{
   const response=await route.fetch();heldResolve();await gate;await route.fulfill({response});
  });
  await second.locator('#lane-1 .target').nth(2).tap();await held;
  await first.locator('#lane-1 [data-action=bib]').tap();await first.locator('#bib-input').fill('99');await first.locator('#bib-input').dispatchEvent('input');
  await expect(admin.locator('#session-warning')).toContainText('1');
  await admin.locator('#new-session-name').fill('Nachmittag <Test>');
  await admin.locator('#start-session-button').click();
  assert.equal((await state()).session_id,oldId,'Ohne ausdrückliche Bestätigung kein Wechsel');
  await admin.locator('#confirm-session').check();await admin.locator('#start-session-button').click();
  await expect(admin.locator('#session-status')).toContainText('Neue Sitzung gestartet');
  const newId=(await state()).session_id;assert.notEqual(newId,oldId);
  await expect(first.locator('#editor')).not.toBeVisible();
  for(const page of [first,second,monitor]){
   await expect(page.locator('#session-name')).toHaveText('Nachmittag <Test>');
   await expect(page.locator('#lane-1')).toHaveAttribute('data-status','reset_required');
   await expect(page.locator('#lane-1 .unknown')).toHaveCount(5);
  }
  releaseResponse();await expect(second.locator('#lane-1 .bib')).toBeEnabled();
  await expect(second.locator('#lane-1 .unknown')).toHaveCount(5);
  await expect(second.locator('#notice')).toContainText('nová relace');
  assert.equal((await state()).sequence,0);
  assert.deepEqual((await state()).bouts,{});
  const stale=await fetch(url+'/api/lanes/1/occupy',{method:'POST',headers:{'Content-Type':'application/json','X-Session-ID':oldId},body:JSON.stringify({lane_id:1,expected_revision:0})});
  assert.equal(stale.status,409);
  await first.locator('#language').selectOption('de');
  await expect(first.locator('#notice')).toContainText('Neue Aufzeichnungssitzung');
  await first.locator('#lane-1 [data-action=manual-reset]').tap();await first.locator('#lane-1 [data-action=occupy]').tap();
  await first.locator('#lane-1 [data-action=bib]').tap();await first.locator('#bib-input').fill('42');await first.locator('#confirm-bib').tap();
  await expect(second.locator('#lane-1 .bib')).toHaveText('42');
  const archived=await(await fetch(url+'/api/events?session_id='+oldId)).json();
  assert.equal(archived.events.filter(event=>event.command.kind==='assign').length,1);
  await admin.locator('details summary').click();
  await expect(admin.locator('#session-archives a')).toContainText('Vormittag');
  // Offline begonnenen BIB-Entwurf bei Wiederverbindung zur nächsten Sitzung verwerfen.
  await second.locator('#lane-2 [data-action=bib]').tap();await second.locator('#bib-input').fill('88');
  await landscape.setOffline(true);
  const next=await fetch(url+'/api/sessions/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:require('node:crypto').randomUUID(),expected_session_id:newId,name:'Abend',confirm_active:true})});
  assert.equal(next.status,200);await landscape.setOffline(false);
  await second.evaluate(()=>window.dispatchEvent(new Event('online')));
  await expect(second.locator('#session-name')).toHaveText('Abend');await expect(second.locator('#editor')).not.toBeVisible();
  await expect(monitor.locator('#session-name')).toHaveText('Abend');
  await expect(admin.locator('#current-session')).toContainText('Abend');
  fs.mkdirSync('.test-artifacts',{recursive:true});
  for(const [name,page]of [['sessions-admin',admin],['sessions-tablet-portrait',first],['sessions-tablet-landscape',second],['sessions-monitor',monitor]]){
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,name+' horizontal overflow');
   await page.screenshot({path:'.test-artifacts/'+name+'.png',fullPage:true});
  }
  assert.deepEqual(errors,[]);
  console.log('Sitzungswechsel: Administration, zwei Tablets, Monitor, verspätete Antwort und Wiederverbindung erfolgreich.');
 }finally{
  releaseResponse?.();if(browser)await browser.close();fixture.kill();await new Promise(resolve=>fixture.once('exit',resolve));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
