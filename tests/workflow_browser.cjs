// Reale Touch-Bedienung des gemeinsamen Ablaufs, mit zwei Tablets und laufenden Bildern.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');
const readline=require('node:readline'),fs=require('node:fs'),assert=require('node:assert/strict');

async function scenario(browser,manualOnly){
 const fixture=spawn('.venv/bin/python',['-u','-m','tests.vision_fixture',...(manualOnly?['--manual-only','--three-lanes']:[])]);
 let logs='';fixture.stderr.on('data',value=>logs+=value);const contexts=[],errors=[];
 try{
  const line=await new Promise((resolve,reject)=>{readline.createInterface({input:fixture.stdout}).once('line',resolve);fixture.once('exit',()=>reject(Error(logs)));});
  const {url,control}=JSON.parse(line);
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  const pages=[];
  for(const viewport of [{width:600,height:960},{width:960,height:600}]){
   const context=await browser.newContext({viewport,hasTouch:true});contexts.push(context);
   const page=await context.newPage();pages.push(page);page.on('pageerror',error=>errors.push(error.message));
   await page.goto(url);await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
  }
  const [first,second]=pages;
  const monitor=await contexts[1].newPage();await monitor.goto(url+'/monitor');
  const card=(page,n=1)=>page.locator(`#lane-${n}`);
  const snapshot=async()=> (await(await fetch(url+'/api/state')).json());
  async function options(page,n,open){
   const details=card(page,n).locator('.lane-options');
   if(await details.evaluate(node=>node.open)!==open)await details.locator('summary').click();
  }
  async function status(n,value){for(const page of pages)await expect(card(page,n)).toHaveAttribute('data-status',value);}
  async function reset(n){
   const button=card(first,n).locator('[data-action=manual-reset]');
   if(!await button.isVisible())await options(first,n,true);
   await button.tap();await expect(card(first,n).locator('.bib')).toBeEnabled();await options(first,n,false);
  }
  async function occupy(n){await card(first,n).locator('.lane-main[data-action=occupy]').tap();await status(n,'occupied');}
  async function leave(n){await card(first,n).locator('.lane-main[data-action=release]').tap();await expect(card(first,n).locator('.bib')).toBeEnabled();}
  async function bib(n,number){
   await card(first,n).locator('[data-action=bib]').tap();await first.locator('[data-key=clear]').click();
   for(const digit of String(number))await first.locator(`[data-key="${digit}"]`).click();
   await first.locator('#confirm-bib').click();await expect(first.locator('#editor')).not.toBeVisible();
   await expect(card(second,n).locator('.bib')).toHaveText(String(number));
  }
  async function target(page,n,position,value='fallen'){
   await card(page,n).locator('.target').nth(position-1).tap();
   if(await page.locator('#editor').isVisible()){
    // Den kurz eingeblendeten nativen Chromium-Touchrahmen nicht mit abbilden.
    await page.waitForTimeout(250);
    await page.screenshot({path:'.test-artifacts/unified-unknown-choice.png'});
    await page.locator(`[data-target-state=${value}]`).tap();
   }
   await expect(page.locator('#editor')).not.toBeVisible();await expect(card(page,n).locator('.bib')).toBeEnabled();
  }
  async function screenshot(name){
   fs.mkdirSync('.test-artifacts',{recursive:true});
   for(const [index,page]of pages.entries()){
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:`.test-artifacts/${name}-${index===0?'portrait':'landscape'}.png`,fullPage:true});
   }
  }
  const write=data=>{fs.writeFileSync(control+'.new',JSON.stringify(data));fs.renameSync(control+'.new',control);};
  if(manualOnly){
   await reset(3);await status(3,'ready');
   await reset(1);await status(1,'ready');await occupy(1);
   let state=await snapshot();const bout=state.lanes['1'].occupied_bout_id;
   assert.equal(state.bouts[bout].bib,null);
   const top=await card(first).locator('.lane-main').boundingBox();
   await target(first,1,3);await expect(card(second).locator('.target').nth(2)).toHaveAttribute('data-state','fallen');
   await target(second,1,3);await expect(card(first).locator('.target').nth(2)).toHaveAttribute('data-state','standing');
   assert.equal((await snapshot()).lanes['1'].current_bout_id,bout);
   assert.equal((await snapshot()).sequence>state.sequence,true);
   const after=await card(first).locator('.lane-main').boundingBox();assert.equal(top.y,after.y);
   await target(first,1,1);await bib(1,42);await bib(1,43);await status(1,'occupied');
   for(const language of ['en','de','cs']){
    for(const page of pages)await page.locator('#language').selectOption(language);
    await expect(first.locator('html')).toHaveAttribute('lang',language);
    await status(1,'occupied');await status(2,'reset_required');await status(3,'ready');
    const colors=await first.locator('.lane-card').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).backgroundColor));
    assert.equal(new Set(colors).size,3);
    assert.deepEqual(colors,['rgb(255, 241, 197)','rgb(230, 234, 238)','rgb(229, 243, 232)']);
    await expect.poll(async()=>monitor.locator('.lane').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).backgroundColor))).toEqual(colors);
    await expect(monitor.locator('button,input,select')).toHaveCount(0);
    await monitor.screenshot({path:`.test-artifacts/unified-monitor-${language}.png`,fullPage:true});
    const fills=await card(first).locator('.target .disc').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).backgroundColor));
    assert(fills.includes('rgb(17, 17, 17)'));assert(fills.includes('rgb(255, 255, 255)'));
    const positions=await second.locator('.lane-card').evaluateAll(nodes=>nodes.map(node=>({top:node.getBoundingClientRect().top,action:node.querySelector('.lane-main').getBoundingClientRect().top,height:node.querySelector('.lane-main').getBoundingClientRect().height})));
    assert(positions.every(position=>position.top===positions[0].top&&position.action===positions[0].action&&position.height===56));
    await screenshot(`workflow-${language}`);
   }
   for(const page of pages)await page.locator('#language').selectOption('de');
   await expect(card(first).locator('.lane-main')).toHaveText('Bahn verlassen');
   assert.equal(await card(first).locator('.set-unknown').count(),0);
   const circles=await card(first).locator('.target').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};}));
   assert(circles.every(circle=>circle.width>=48&&circle.height>=48&&circle.y===circles[0].y));
   // Unbekannt erfordert eine eindeutige Auswahl, keine versteckte Geste.
   await target(second,2,1,'standing');await target(first,2,2,'fallen');
   await expect(card(first,2).locator('.target').nth(0)).toHaveAttribute('data-state','standing');
   await expect(card(second,2).locator('.target').nth(1)).toHaveAttribute('data-state','fallen');
   assert.equal(await first.locator('.lane-mode,.target-comparison,[data-action=override-release],[data-action=unknown-menu]').count(),0);
   await leave(1);await status(1,'reset_required');
   await reset(1);await status(1,'ready');
   // Umgekehrte Reihenfolge: Rückstellung beendet nicht die Belegung.
   await occupy(1);await bib(1,44);await target(first,1,2);await reset(1);await status(1,'occupied');
   await leave(1);await status(1,'ready');
   // Keine gefallenen Scheiben: unverändert aufgerichtet ist kein neuer Reset.
   await occupy(1);await bib(1,45);await leave(1);await status(1,'reset_required');
   await reset(1);await status(1,'ready');
   const events=(await(await fetch(url+'/api/events')).json()).events;
   assert(events.every(event=>!['shot','hit','miss'].includes(event.command.kind)));
   assert(events.filter(event=>event.command.kind==='manual_target').every(event=>event.command.start_bout===false));
  }else{
   await expect(card(first).locator('.target[data-state=standing]')).toHaveCount(5,{timeout:10000});
   await status(1,'reset_required'); // Anfangsbild ist kein Rückstellereignis.
   await reset(1);await status(1,'ready');await reset(2);await status(2,'ready');
   await occupy(1);await occupy(2);await bib(1,61);await bib(2,62);
   write({camera1:{mask:9},camera2:{mask:9}});
   for(const n of [1,2])await expect(card(second,n).locator('.target[data-state=fallen]')).toHaveCount(2);
   const before=await card(first,2).locator('.lane-main').boundingBox();
   await target(first,2,3);await expect(card(second,2).locator('.target').nth(2)).toHaveAttribute('data-state','fallen');
   assert.equal((await snapshot()).lanes['2'].manual_targets[2],'fallen');
   const after=await card(first,2).locator('.lane-main').boundingBox();assert.equal(before.y,after.y);
   write({camera1:{mask:25},camera2:{mask:25}});
   await expect(card(first,2).locator('.target[data-state=fallen]')).toHaveCount(4);
   await screenshot('workflow-camera-mixed');
   await target(second,2,3);
   await expect(card(first,2).locator('.target').nth(2)).toHaveAttribute('data-state','standing');
   const bout=(await snapshot()).lanes['2'].occupied_bout_id;
   write({camera1:{mask:25},camera2:{connected:false}});
   await expect(card(first,2).locator('.target[data-state=unknown]')).toHaveCount(4);
   await target(first,2,3);
   assert.equal((await snapshot()).lanes['2'].current_bout_id,bout);
   assert.equal((await snapshot()).bouts[bout].bib,62);
   await status(1,'occupied');await status(2,'occupied');
   await leave(2);await status(2,'reset_required');await reset(2);await status(2,'ready');
   await leave(1);await status(1,'reset_required');
   write({camera1:{mask:0},camera2:{connected:false}});await status(1,'ready');
   // Ein unverändertes Fünferbild nach Belegung reicht auch automatisch nicht.
   await occupy(1);await bib(1,63);await leave(1);await status(1,'reset_required');
  }
  assert.deepEqual(errors,[]);
 }finally{
  for(const context of contexts)await context.close();fixture.kill('SIGTERM');
  if(fixture.exitCode===null)await new Promise(resolve=>fixture.once('exit',resolve));
 }
}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{await scenario(browser,true);await scenario(browser,false);
  console.log('Ablauf-Browserprüfung erfolgreich: drei Sprachen, kleine Touch-Tablets hoch/quer, drei Kachelfarben, ein Ablauf ohne Quellenwahl, Korrektur, Kameraausfall und zwei Tablets.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
