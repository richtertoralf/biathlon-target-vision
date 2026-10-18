// Eigene Sprachdateien ohne Browserübersetzung: Schutz, Sprachattribute und Dialogtexte.
const {chromium,expect}=require(process.env.PLAYWRIGHT_MODULE||'@playwright/test');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
(async()=>{
 const fixture=spawn('.venv/bin/python',['-u','-m','tests.vision_fixture','--manual-only']);
 let browser,logs='';fixture.stderr.on('data',data=>logs+=data);const errors=[];
 try{
  const line=await new Promise((resolve,reject)=>{
   readline.createInterface({input:fixture.stdout}).once('line',resolve);
   fixture.once('exit',()=>reject(Error(logs)));
  });
  const {url}=JSON.parse(line);
  for(let i=0;i<100;i++){
   try{if((await fetch(url+'/api/health')).ok)break;}catch{}
   await new Promise(resolve=>setTimeout(resolve,100));
  }
  // Der Check untersucht Originaltexte, nicht den externen Google-Dienst.
  browser=await chromium.launch({headless:true,args:['--disable-features=Translate']});
  const context=await browser.newContext({locale:'en-US',viewport:{width:1024,height:768},hasTouch:true});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  async function protectedDocument(language){
   await expect(page.locator('html')).toHaveAttribute('lang',language);
   await expect(page.locator('html')).toHaveAttribute('translate','no');
   await expect(page.locator('html')).toHaveClass(/\bnotranslate\b/);
   await expect(page.locator('meta[name="google"]')).toHaveAttribute('content','notranslate');
   assert.equal(await page.locator('h1').evaluate(element=>element.translate),false);
   assert.doesNotMatch(await page.locator('body').innerText(),/Fahrspuren|Strecke\s+\d+|Errichtet|Bevorzugt/i);
  }
  for(const route of ['/','/monitor','/admin','/calibration']){
   await page.goto(url+route);await protectedDocument(route==='/'?'en':'de');
  }
  await page.goto(url);await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
  const expected={
   en:{range:'Range control',overview:'Shooting lanes',lane:'Lane 1',target:'Target 1',bib:'Bib',bout:'Bout 1',states:['Standing','Fallen','Unknown']},
   de:{range:'Schießstand',overview:'Schießbahnen',lane:'Bahn 1',target:'Scheibe 1',bib:'Startnummer',bout:'Einlage 1',states:['Aufgerichtet','Gefallen','Unbekannt']},
   cs:{range:'Střelnice',overview:'Střelecké stavy',lane:'Stav 1',target:'Terč 1',bib:'Startovní číslo',bout:'Položka 1',states:['Vztyčený','Sklopený','Neznámý']},
  };
  const valid=await page.evaluate(()=>{
   const all=window.BTV_I18N,keys=Object.keys(all.en).sort();
   return ['en','de','cs'].every(language=>JSON.stringify(Object.keys(all[language]).sort())===JSON.stringify(keys)
    &&keys.every(key=>typeof all[language][key]==='string'&&all[language][key].length
     &&JSON.stringify(all[language][key].match(/\{\w+\}/g)?.sort())===JSON.stringify(all.en[key].match(/\{\w+\}/g)?.sort())));
  });assert.equal(valid,true);
  // Sichtbare Belegung ohne Kamera; die folgenden Sprachwechsel dürfen nichts buchen.
  await page.locator('#lane-1 summary').click();
  await page.locator('#lane-1 [data-action="bib"]').click();
  await page.locator('[data-key="4"]').click();await page.locator('[data-key="2"]').click();
  await page.locator('#confirm-bib').click();await expect(page.locator('#editor')).not.toBeVisible();
  const sequence=(await(await fetch(url+'/api/state')).json()).sequence;
  for(const language of ['de','cs','en']){
   await page.locator('#language').selectOption(language);await protectedDocument(language);
   const text=expected[language];
   await expect(page.locator('h1')).toHaveText(text.overview);
   await expect(page.locator('.eyebrow')).toHaveText(text.range);
   await expect(page.locator('#lane-1 h2')).toHaveText(text.lane);
   await expect(page.locator('#lane-1 .bib-line > span')).toHaveText(text.bib);
   if (!await page.locator('#lane-1 .lane-options').evaluate(node=>node.open)) await page.locator('#lane-1 summary').click();
   await expect(page.locator('#lane-1 .bout-line')).toContainText(text.bout);
   await expect(page.locator('#lane-1 .target').first()).toHaveAttribute('aria-label',text.target+': '+text.states[2]);
   await expect(page.locator('.legend [data-i18n]')).toHaveText(text.states);
   for(const action of ['bib','history','manual-target']){
    await page.locator(`#lane-1 [data-action="${action}"]`).first().click();
    await expect(page.locator('#editor')).toBeVisible();
    const body=await page.locator('#editor').innerText();
    assert.doesNotMatch(body,/Fahrspuren|Strecke\s+\d+|Errichtet|Bevorzugt/i);
    const dictionary=await page.evaluate(language=>window.BTV_I18N[language],language);
    if(action==='manual-target'){
     await expect(page.locator('#dialog-context')).toHaveText(dictionary.confirmTarget);
     await expect(page.locator('[data-target-state]')).toContainText(text.states.slice(0,2));
    }
    await page.locator('#close-dialog').click();await expect(page.locator('#editor')).not.toBeVisible();
   }
   const dictionary=await page.evaluate(language=>window.BTV_I18N[language],language);
   await expect(page.locator('#lane-1 [data-action=release]')).toHaveText(dictionary.leaveLane);
   await expect(page.locator('#lane-1 [data-action=manual-reset]')).toHaveText(dictionary.allStanding);
   await page.reload();await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
   await protectedDocument(language);await expect(page.locator('h1')).toHaveText(text.overview);
  }
  assert.equal((await(await fetch(url+'/api/state')).json()).sequence,sequence);
  assert.deepEqual(errors,[]);
  console.log('Übersetzungs-Browserprüfung erfolgreich: vier geschützte Seiten, Originaltexte EN/DE/CS, Sprachattribute, Persistenz, Scheiben/Bahnen/Einlagen und Dialoge ohne Journaländerung.');
 }finally{
  if(browser)await browser.close();fixture.kill('SIGTERM');
  if(fixture.exitCode===null)await new Promise(resolve=>fixture.once('exit',resolve));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
