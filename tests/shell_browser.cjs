// Shared page frame on all four pages: header, server clock, connection state, footer and ergonomics.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');

const PAGES=[['tablet','/'],['monitor','/monitor'],['admin','/admin'],['calibration','/calibration']];
const VIEWPORTS=[[1920,1080],[1366,768],[1024,768],[768,1024],[390,844]];
const berlin=new Intl.DateTimeFormat('de-DE',{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
const seconds=text=>{const [h,m,s]=text.split(':').map(Number);return h*3600+m*60+s;};

async function freePort(){return new Promise(resolve=>{const server=net.createServer();server.listen(0,'127.0.0.1',()=>{const {port}=server.address();server.close(()=>resolve(port));});});}

// The clock must show server time even if the browser clock is wrong.
function assertServerTime(text){
 assert.match(text,/^\d{2}:\d{2}:\d{2}$/);
 const difference=Math.abs(seconds(text)-seconds(berlin.format(Date.now())));
 assert.ok(Math.min(difference,86400-difference)<=2,`Uhr ${text} weicht von der Serverzeit ab`);
}

async function checkFrame(page,name,current,health){
 const header=page.locator('.shell-header'),footer=page.locator('.shell-footer');
 await expect(header).toContainText('BTV');
 await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
 await expect(page.locator('#clock')).toHaveAttribute('data-synced','true');
 assertServerTime(await page.locator('#clock').textContent());
 await expect(footer).toContainText(`BTV v${health.version} · ${health.commit}`);
 await expect(footer.locator('nav a')).toHaveCount(4);
 assert.deepEqual(await footer.locator('nav a').evaluateAll(links=>links.map(link=>link.getAttribute('href'))),['/','/monitor','/admin','/calibration']);
 await expect(footer.locator('[aria-current=page]')).toHaveAttribute('href',current);
 const layout=await page.evaluate(()=>{
  const box=selector=>document.querySelector(selector).getBoundingClientRect();
  const controls=[...document.querySelectorAll('main button, main select, main input:not([type=checkbox]), main summary, .tabs a, .link-row a, .shell-footer a')]
   .filter(node=>node.offsetParent!==null&&node.getBoundingClientRect().height<44).map(node=>node.outerHTML.slice(0,80));
  return {overflow:document.documentElement.scrollWidth>innerWidth,header:box('.shell-header').height,mainTop:box('main').top,headerBottom:box('.shell-header').bottom,
   mainBottom:box('main').bottom,footerTop:box('.shell-footer').top,font:parseFloat(getComputedStyle(document.body).fontSize),controls};
 });
 assert.equal(layout.overflow,false,name+': horizontal overflow');
 assert.ok(layout.header>=44&&layout.header<=48,name+': header height '+layout.header);
 assert.ok(layout.mainTop>=layout.headerBottom-.5,name+': header covers the work area');
 assert.ok(layout.footerTop>=layout.mainBottom-.5,name+': footer covers the work area');
 assert.ok(layout.font>=16,name+': font size');
 assert.deepEqual(layout.controls,[],name+': controls below 44 px');
 fs.mkdirSync('.test-artifacts',{recursive:true});await page.screenshot({path:`.test-artifacts/shell-${name}.png`});
}

(async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'btv-shell-')),port=await freePort(),url=`http://127.0.0.1:${port}`;
 const server=spawn('.venv/bin/python',['-m','biathlon_target_vision','--lanes','20','--data-dir',directory,'--port',String(port)]);
 let logs='';server.stderr.on('data',value=>logs+=value);
 const browser=await chromium.launch({headless:true});const errors=[];
 try{
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  const health=await(await fetch(url+'/api/health')).json();
  assert.match(health.commit,/^[0-9a-f]{7,}$/,'commit from the installed program state');
  assert.ok(!Number.isNaN(Date.parse(health.server_time)));

  for(const [width,height] of VIEWPORTS){
   const context=await browser.newContext({viewport:{width,height},hasTouch:width<1366});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
   for(const [name,route] of PAGES){await page.goto(url+route);await checkFrame(page,`${name}-${width}x${height}`,route,health);}
   await context.close();
  }

  // Wrong browser clock and foreign time zone: the shown time stays server time in Berlin.
  const skewed=await browser.newContext({viewport:{width:1366,height:768},timezoneId:'America/New_York'});
  await skewed.addInitScript(shift=>{
   const RealDate=Date;
   class SkewedDate extends RealDate{constructor(...values){if(values.length)super(...values);else super(RealDate.now()+shift);}static now(){return RealDate.now()+shift;}}
   window.Date=SkewedDate;
  },(5*3600+17*60+23)*1000);
  const page=await skewed.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/admin');await expect(page.locator('#clock')).toHaveAttribute('data-synced','true');
  const first=await page.locator('#clock').textContent();assertServerTime(first);
  await expect(page.locator('#clock')).not.toHaveText(first,{timeout:2500});
  assertServerTime(await page.locator('#clock').textContent());

  // Outage: the clock keeps running but is marked unsynchronised; reconnecting resyncs.
  for(const route of ['/admin','/calibration']){
   await page.goto(url+route);await expect(page.locator('#clock')).toHaveAttribute('data-synced','true');
   await skewed.setOffline(true);
   await expect(page.locator('#connection')).toHaveAttribute('data-status','offline');
   await expect(page.locator('#clock')).toHaveAttribute('data-synced','false');
   const during=await page.locator('#clock').textContent();
   await expect(page.locator('#clock')).not.toHaveText(during,{timeout:2500});
   assert.match(await page.locator('#clock').getAttribute('title'),/nicht synchronisiert/);
   await skewed.setOffline(false);
   await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
   await expect(page.locator('#clock')).toHaveAttribute('data-synced','true');
   assertServerTime(await page.locator('#clock').textContent());
  }
  // The clock text does not change the header layout while it runs.
  const widths=new Set();for(let i=0;i<3;i++){widths.add(await page.locator('#clock').evaluate(node=>node.getBoundingClientRect().width));await page.waitForTimeout(1000);}
  assert.equal(widths.size,1,'clock width changes');
  await skewed.close();

  // The tablet language also changes the footer; the calibration canvas area stays wide.
  const tablet=await browser.newPage({viewport:{width:1024,height:768}});tablet.on('pageerror',e=>errors.push(e.message));
  await tablet.goto(url);await expect(tablet.locator('#connection')).toHaveAttribute('data-status','online');
  await tablet.locator('#language').selectOption('cs');
  await expect(tablet.locator('#connection')).toHaveText('● Připojeno');
  await expect(tablet.locator('.shell-footer [aria-current=page]')).toHaveText('Obsluha');
  await tablet.goto(url+'/calibration');
  const area=await tablet.evaluate(()=>document.querySelector('.image-area').getBoundingClientRect().width/document.querySelector('main').getBoundingClientRect().width);
  assert.ok(area>.9,'calibration image area uses the work area');
  await expect(tablet.locator('#capture')).toBeVisible();

  assert.deepEqual(errors,[]);
  console.log('Seitenrahmen: vier Ansichten in fünf Größen, Serveruhr, Verbindungsstatus, Version/Commit, Navigation und Ergonomie erfolgreich.');
 }finally{
  await browser.close();server.kill();await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  fs.rmSync(directory,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
