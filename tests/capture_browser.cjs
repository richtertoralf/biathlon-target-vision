// Regulärer Betrieb ohne Simulation: zwei Tablets, manuelle Erfassung und Kamera-Mischbetrieb.
const {chromium, expect} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const fs = require('node:fs');
const assert = require('node:assert/strict');

async function scenario(browser, manualOnly) {
  const fixture = spawn('.venv/bin/python', ['-u','-m','tests.vision_fixture', '--three-lanes', ...(manualOnly ? ['--manual-only'] : [])]);
  let logs = ''; fixture.stderr.on('data', data => { logs += data; });
  const contexts = [];
  try {
    const line = await new Promise((resolve,reject) => {
      readline.createInterface({input:fixture.stdout}).once('line',resolve);
      fixture.once('exit',() => reject(Error(logs)));
    });
    const {url,control} = JSON.parse(line);
    for (let i=0;i<100;i++) {
      try { if ((await fetch(url+'/api/health')).ok) break; } catch {}
      await new Promise(resolve => setTimeout(resolve,100));
    }
    const pages=[];
    for (const viewport of [{width:1024,height:768},{width:768,height:1024}]) {
      const context=await browser.newContext({viewport,hasTouch:true});contexts.push(context);
      const page=await context.newPage();pages.push(page);
      page.on('pageerror', error => { throw error; });
      await page.goto(url);
      await expect(page.locator('#connection')).toHaveAttribute('data-status','online');
    }
    const [first, second]=pages;
    const monitor=await contexts[1].newPage();await monitor.goto(url+'/monitor');
    const card=(page,lane=1)=>page.locator(`#lane-${lane}`);
    const target=(page,n)=>card(page).locator('.target').nth(n-1);
    const state=async()=> (await (await fetch(url+'/api/state')).json());
    const assign=async bib=>{
      await card(first).locator('[data-action="bib"]').click();
      await first.locator('[data-key="clear"]').click();
      for(const digit of String(bib)) await first.locator(`[data-key="${digit}"]`).click();
      await first.locator('#confirm-bib').click();
      await expect(first.locator('#editor')).not.toBeVisible();
      await expect(card(second).locator('.bib')).toHaveText(String(bib));
    };
    const reset=async()=>{
      const button=card(first).locator('[data-action="manual-reset"]').first();
      if (!await button.isVisible()) await card(first).locator('summary').click();
      await button.click();
      await expect(first.locator('#editor')).not.toBeVisible();
      await expect(card(first).locator('.bib')).toBeEnabled();
    };
    const write=data=>{fs.writeFileSync(control+'.new',JSON.stringify(data));fs.renameSync(control+'.new',control);};
    const capture=(page,lane=1)=>card(page,lane).locator('.capture-status');
    const texts={
      en:{active:'Automatic detection active',uncertain:'Detection pending / uncertain',unavailable:'Manual input required',marker:'Manual',correction:'Manual correction'},
      de:{active:'Automatik aktiv',uncertain:'Erkennung läuft / unsicher',unavailable:'Nur manuell',marker:'Manuell',correction:'Manuelle Korrektur'},
      cs:{active:'Automatické rozpoznávání aktivní',uncertain:'Rozpoznávání probíhá / nejisté',unavailable:'Pouze ruční zadávání',marker:'Ručně',correction:'Ruční oprava'},
    };
    async function captureStatus(lane,status) {
      // Reine Konfigurationsänderungen kommen mit dem Fünf-Sekunden-Lebenszeichen.
      for(const page of pages)await expect(capture(page,lane)).toHaveAttribute('data-status',status,{timeout:10000});
    }
    assert.equal((await state()).simulation,false);
    if(manualOnly) {
      assert.equal((await state()).capture.cameras.length,0);
      await captureStatus(1,'unavailable');
      for(const language of ['de','cs','en']) {
        await first.locator('#language').selectOption(language);
        await expect(capture(first)).toHaveText(texts[language].unavailable);
      }
      await reset(); await assign(42);
      for(const n of [1,3,5]) {
        await target(first,n).tap();
        await expect(target(second,n)).toHaveAttribute('data-state','fallen');
        await expect(first.locator('#editor')).not.toBeVisible();
      }
      await expect(monitor.locator('#lane-1 .fallen')).toHaveCount(3);
      fs.mkdirSync('.test-artifacts',{recursive:true});
      await first.screenshot({path:'.test-artifacts/v07-manual.png',fullPage:true});
      await reset();
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5);
      await card(first).locator('[data-action="release"]').click();
      await expect(first.locator('#editor')).not.toBeVisible();
      await assign(43); await target(second,2).tap();
      await expect(target(first,2)).toHaveAttribute('data-state','fallen');
      await first.reload();
      await expect(card(first).locator('.lane-mode')).toHaveCount(0);
      await expect(target(first,2)).toHaveAttribute('data-state','fallen');
    } else {
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5,{timeout:10000});
      await captureStatus(1,'active');await captureStatus(2,'active');await captureStatus(3,'unavailable');
      // Dieselbe Kamera liefert Bilder für zwei Bahnen, nur eine ist kalibriert.
      const configured=await fetch(url+'/api/cameras/camera1',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:'camera1',name:'Kamera 1',url:'',lane_ids:[1,3]})});
      assert.equal(configured.status,200);
      await captureStatus(1,'active');await captureStatus(3,'uncertain');
      const shared=(await state()).capture.cameras.find(camera=>camera.id==='camera1');
      assert.deepEqual(shared.lane_ids,[1,3]);assert.equal(shared.connected,true);
      await assign(52);
      write({camera1:{mask:9},camera2:{mask:4}});
      await expect(target(second,1)).toHaveAttribute('data-state','fallen');
      await expect(target(second,4)).toHaveAttribute('data-state','fallen');
      await target(first,3).tap();
      await expect(target(second,3)).toHaveAttribute('data-state','fallen');
      for(const page of pages)await expect(target(page,3)).toHaveAttribute('data-manual','true');
      // Viele unveränderte Bilder und weitere echte Zieländerungen dürfen die Korrektur nicht verdrängen.
      write({camera1:{mask:25},camera2:{mask:12}});
      await expect(target(first,5)).toHaveAttribute('data-state','fallen');
      await expect(monitor.locator('#lane-2 .fallen')).toHaveCount(2);
      await new Promise(resolve=>setTimeout(resolve,800));
      await expect(monitor.locator('#lane-1 .fallen')).toHaveCount(4);
      await captureStatus(1,'active');
      fs.mkdirSync('.test-artifacts',{recursive:true});
      for(const language of ['en','de','cs']) {
        await second.locator('#language').selectOption(language);
        await expect(capture(second)).toHaveText(texts[language].active);
        await expect(capture(second,3)).toHaveText(texts[language].uncertain);
        await expect(target(second,3).locator('.manual-marker')).toHaveText(texts[language].marker);
        await expect(target(second,3)).toHaveAttribute('aria-label',new RegExp(texts[language].correction));
        for(const viewport of [{width:600,height:960},{width:960,height:600}]) {
          await second.setViewportSize(viewport);
          assert.equal(await second.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
          const overflow=await capture(second).evaluate(node=>node.scrollHeight>node.clientHeight);
          assert.equal(overflow,false);
          await second.screenshot({path:`.test-artifacts/capture-${language}-${viewport.width}.png`,fullPage:true});
        }
      }
      await second.locator('#language').selectOption('en');
      await second.screenshot({path:'.test-artifacts/v07-mixed.png',fullPage:true});
      // Unsichere automatische Werte bleiben erkennbar, auch bei wirksamer Korrektur.
      write({camera1:{mask:25,missing:2},camera2:{mask:12}});
      await captureStatus(1,'uncertain');await captureStatus(2,'active');
      await expect(target(second,3)).toHaveAttribute('data-state','fallen');
      await second.screenshot({path:'.test-artifacts/capture-uncertain.png',fullPage:true});
      await target(second,3).tap();
      await expect(target(first,3)).toHaveAttribute('data-state','standing');
      await target(first,3).tap();
      const before=(await state()); const bout=before.lanes['1'].current_bout_id;
      write({camera1:{connected:false},camera2:{mask:28}});
      await expect(card(first).locator('.capture-status')).toHaveText('Manual input required');
      await captureStatus(1,'unavailable');await captureStatus(3,'unavailable');await captureStatus(2,'active');
      await expect(target(second,1)).toHaveAttribute('data-state','unknown');
      await expect(target(second,3)).toHaveAttribute('data-state','fallen');
      for(const n of [1,4,5]) {await target(first,n).tap(); await first.locator('[data-target-state=fallen]').tap(); await expect(target(second,n)).toHaveAttribute('data-state','fallen');}
      await expect(monitor.locator('#lane-2 .fallen')).toHaveCount(3);
      let after=await state();assert.equal(after.lanes['1'].current_bout_id,bout);assert.equal(after.bouts[bout].bib,52);
      assert.deepEqual(after.bouts[bout].fallen_target_ids,before.bouts[bout].fallen_target_ids);
      write({camera1:{mask:9},camera2:{mask:28}});
      await expect(card(first).locator('.capture-status')).toHaveText('Automatic detection active');
      await expect(target(second,5)).toHaveAttribute('data-state','fallen');
      after=await state();assert.deepEqual(after.bouts[bout].fallen_target_ids,before.bouts[bout].fallen_target_ids);
      await target(first,5).tap();
      await expect(target(second,5)).toHaveAttribute('data-state','standing');
      // Eine echte Rückstellung beendet sämtliche alten Übersteuerungen.
      write({camera1:{mask:0},camera2:{mask:28}});
      await expect.poll(async()=> (await state()).lanes['1'].manual_targets).toEqual([null,null,null,null,null]);
      for(const page of pages)await expect(card(page).locator('[data-manual="true"]')).toHaveCount(0);
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5);
      const events=(await (await fetch(url+'/api/events')).json()).events;
      assert(events.some(event=>event.manual_input?.automatic_state==='standing' && event.manual_input.manual_state==='fallen'));
      assert(events.every(event=>!['shot','hit','miss'].includes(event.command.kind)));
    }
    // Quellenwahl ist administrativ; die laufende Kachel bleibt unverändert bedienbar.
    const admin=await contexts[0].newPage();await admin.goto(url+'/admin');
    const source=admin.locator('[data-source-lane="1"]');await expect(source).toBeChecked();
    await source.uncheck();await expect.poll(async()=> (await state()).lanes['1'].mode).toBe('manual');
    await captureStatus(1,'unavailable');
    await expect(card(first).locator('.target').first()).toBeEnabled();
    await expect(source).toBeEnabled();await source.check();
    await expect.poll(async()=> (await state()).lanes['1'].mode).toBe('automatic');
    if(!manualOnly)await captureStatus(1,'active');
    await expect(card(first).locator('.lane-mode')).toHaveCount(0);
    await admin.screenshot({path:'.test-artifacts/unified-admin.png',fullPage:true});
    await contexts[0].setOffline(true);
    await expect(capture(first)).toHaveAttribute('data-status','offline');
    await expect(target(first,1)).toBeDisabled();
    await contexts[0].setOffline(false);
    await expect(first.locator('#connection')).toHaveAttribute('data-status','online');
    await captureStatus(1,manualOnly?'unavailable':'active');
    for(const page of pages) assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  } finally {
    for(const context of contexts) await context.close();
    fixture.kill('SIGTERM');if(fixture.exitCode===null) await new Promise(resolve=>fixture.once('exit',resolve));
  }
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {await scenario(browser,true);await scenario(browser,false);
    console.log('Erfassungs-Browserprüfung erfolgreich: manuell ohne Kamera/Simulation, zwei Tablets, Priorität, Korrektur, Ausfall, direkte Weiterarbeit, Wiederverbindung und Rückstellung.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
