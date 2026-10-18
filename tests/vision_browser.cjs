// Synthetische Videofolge über Erfassung, Journal und WebSocket bis Tablet/Monitor.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');const readline=require('node:readline');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const fixture=spawn('.venv/bin/python',['-u','-m','tests.vision_fixture']);let browser;let stderr='';fixture.stderr.on('data',x=>stderr+=x);
 try{
  const line=await new Promise((resolve,reject)=>{readline.createInterface({input:fixture.stdout}).once('line',resolve);fixture.once('exit',()=>reject(Error(stderr)));});
  const {url,control}=JSON.parse(line);
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true});const tablet=await browser.newPage(),monitor=await browser.newPage();
  await tablet.goto(url);await monitor.goto(url+'/monitor');
  await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5,{timeout:10000});
  const state=await (await fetch(url+'/api/state')).json();const lane=state.lanes['1'];
  const assignment=await fetch(url+'/api/lanes/1/bib',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({lane_id:1,bib:42,expected_revision:lane.revision,expected_assignment_revision:lane.assignment_revision})});assert.equal(assignment.status,200);
  const write=data=>{fs.writeFileSync(control+'.new',JSON.stringify(data));fs.renameSync(control+'.new',control);};
  write({camera1:{mask:16},camera2:{mask:4}});
  await expect(tablet.locator('#lane-1 .target').nth(4)).toHaveAttribute('data-state','fallen');
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['1'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(1);
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['2'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(1);
  write({camera1:{mask:18,noise:5,brightness:.8},camera2:{mask:4}});
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['1'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(2);
  write({camera1:{mask:18,missing:1},camera2:{mask:4}});
  await expect(tablet.locator('#lane-1 .target').nth(1)).toHaveAttribute('data-state','unknown');
  await expect(monitor.locator('#lane-1 .unknown')).toHaveCount(1);
  write({camera1:{connected:false},camera2:{mask:12}});
  await expect(monitor.locator('#lane-1 .unknown')).toHaveCount(5);
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['2'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(2);
  write({camera1:{mask:19},camera2:{mask:12}});
  await expect(monitor.locator('#lane-1 .fallen')).toHaveCount(3);
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['1'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(2);
  write({camera1:{mask:0},camera2:{mask:12}});
  await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5);
  await expect.poll(async()=>{const s=await (await fetch(url+'/api/state')).json();return s.bouts[s.lanes['1'].current_bout_id]?.fallen_target_ids.length??0;}).toBe(0);
  const events=(await (await fetch(url+'/api/events')).json()).events;
  assert(events.some(e=>e.baseline));assert(events.every(e=>!['shot','miss'].includes(e.command.kind)));
  console.log('Optik-Browserprüfung erfolgreich: zwei Kameras, beliebige Ziele, Verdeckung, Ausfall, Baseline, Reset bis Tablet/Monitor.');
 }finally{if(browser)await browser.close();fixture.kill('SIGTERM');if(fixture.exitCode===null)await new Promise(r=>fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
