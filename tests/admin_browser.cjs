// Kamera-CRUD, echte RTSP-Vorschau und automatische ROI-Kalibrierung im Browser.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');const readline=require('node:readline');
(async()=>{
 const fixture=spawn('.venv/bin/python',['-u','-m','tests.camera_fixture']);let browser;
 try{
  const line=await new Promise((resolve,reject)=>{readline.createInterface({input:fixture.stdout}).once('line',resolve);fixture.once('exit',()=>reject(Error('Kamerafixture vorzeitig beendet')));});
  const {url,rtsp,quad}=JSON.parse(line);
  for(let i=0;i<100;i++){try{if((await fetch(url+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true});const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/admin');await page.locator('#camera-id').fill('test');await page.locator('#camera-name').fill('Testkamera');await page.locator('#camera-url').fill(rtsp);await page.locator('#camera-lanes').fill('1,2');await page.locator('button[type=submit]').click();
  await expect(page.locator('#status')).toHaveText('Kamera gespeichert.');await expect(page.locator('#connection')).toHaveText('Kamera verbunden',{timeout:20000});await expect(page.locator('#preview')).toBeVisible();
  await expect(page.locator('#camera-url')).toHaveValue('');
  await page.locator('#calibrations a').first().click();await expect(page.locator('#capture')).toBeEnabled();await page.locator('#capture').click();await expect(page.locator('#image')).toBeVisible();
  const canvas=page.locator('#image');const box=await canvas.boundingBox();
  for(const [x,y]of quad)await canvas.click({position:{x:x*box.width/960,y:y*box.height/440}});
  await page.locator('#detect').click();await expect(page.locator('#status')).toContainText('Fünf Ziele erkannt und gespeichert');
  await page.reload();await expect(page.locator('#saved')).toContainText('Grundkalibrierung gespeichert');
  await page.goto(url+'/admin');await page.locator('#camera').selectOption('test');await page.locator('#camera-name').fill('Umbenannt');await page.locator('button[type=submit]').click();await expect(page.locator('#status')).toHaveText('Kamera gespeichert.');
  await page.locator('#remove').click();await expect(page.locator('#status')).toHaveText('Kamera entfernt.');
  if(errors.length)throw Error(errors.join('\n'));console.log('Kamera-Browserprüfung erfolgreich: RTSP, CRUD, Vorschau, Gesamt-ROI, fünf Ziele, Wiederladen.');
 }finally{if(browser)await browser.close();fixture.stdin.end('\n');if(fixture.exitCode===null)await new Promise(r=>fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
