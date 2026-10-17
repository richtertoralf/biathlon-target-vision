// Regulärer Betrieb ohne Simulation: zwei Tablets, manuelle Erfassung und Kamera-Mischbetrieb.
const {chromium, expect} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const fs = require('node:fs');
const assert = require('node:assert/strict');

async function scenario(browser, manualOnly) {
  const fixture = spawn('.venv/bin/python', ['-u','-m','tests.vision_fixture', ...(manualOnly ? ['--manual-only'] : [])]);
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
    const choose=async mode=>{
      await card(first).locator('.lane-mode').selectOption(mode);
      for(const page of pages) await expect(card(page).locator('.lane-mode')).toHaveValue(mode);
      await expect(card(first).locator('.lane-mode')).toBeEnabled();
    };
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
      await card(first).locator('[data-action="manual-reset"]').click();
      await first.locator('#confirm-action').click();
      await expect(first.locator('#editor')).not.toBeVisible();
      await expect(card(first).locator('.lane-mode')).toBeEnabled();
    };
    const write=data=>{fs.writeFileSync(control+'.new',JSON.stringify(data));fs.renameSync(control+'.new',control);};
    assert.equal((await state()).simulation,false);
    if(manualOnly) {
      assert.equal((await state()).capture.cameras.length,0);
      await choose('manual'); await reset(); await assign(42);
      for(const n of [1,3,5]) {
        await target(first,n).tap();
        await expect(target(second,n)).toHaveAttribute('data-state','fallen');
        await expect(first.locator('#editor')).not.toBeVisible();
      }
      await expect(monitor.locator('#lane-1 .fallen')).toHaveCount(3);
      await expect(monitor.locator('#lane-1 .effective-count')).toContainText('3/5');
      fs.mkdirSync('.test-artifacts',{recursive:true});
      await first.screenshot({path:'.test-artifacts/v07-manual.png',fullPage:true});
      // Unbekannt bleibt ausdrücklich möglich, kein erfundener Fehlschuss.
      await card(second).locator('[data-action="manual-unknown"][data-target="5"]').tap();
      await expect(target(first,5)).toHaveAttribute('data-state','unknown');
      await reset();
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5);
      await card(first).locator('[data-action="release"]').click();
      await first.locator('#confirm-action').click();
      await expect(first.locator('#editor')).not.toBeVisible();
      await assign(43); await target(second,2).tap();
      await expect(target(first,2)).toHaveAttribute('data-state','fallen');
      await first.reload();
      await expect(card(first).locator('.lane-mode')).toHaveValue('manual');
      await expect(target(first,2)).toHaveAttribute('data-state','fallen');
    } else {
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5,{timeout:10000});
      await choose('mixed'); await assign(52);
      write({camera1:{mask:9},camera2:{mask:4}});
      await expect(target(second,1)).toHaveAttribute('data-state','fallen');
      await expect(target(second,4)).toHaveAttribute('data-state','fallen');
      await target(first,3).tap();
      await expect(target(second,3)).toHaveAttribute('data-state','fallen');
      await expect(card(second).locator('[data-target-control="3"]')).toHaveClass(/overridden/);
      await expect(card(second).locator('[data-target-control="3"] .source-detail')).toHaveAttribute('data-automatic-state','standing');
      // Viele unveränderte Bilder und weitere echte Zieländerungen dürfen die Korrektur nicht verdrängen.
      write({camera1:{mask:25},camera2:{mask:12}});
      await expect(target(first,5)).toHaveAttribute('data-state','fallen');
      await expect(monitor.locator('#lane-2 .fallen')).toHaveCount(2);
      await new Promise(resolve=>setTimeout(resolve,800));
      await expect(monitor.locator('#lane-1 .fallen')).toHaveCount(4);
      fs.mkdirSync('.test-artifacts',{recursive:true});
      await second.screenshot({path:'.test-artifacts/v07-mixed.png',fullPage:true});
      await card(second).locator('[data-action="override-release"][data-target="3"]').tap();
      await expect(target(first,3)).toHaveAttribute('data-state','standing');
      await target(first,3).tap();
      const before=(await state()); const bout=before.lanes['1'].current_bout_id;
      write({camera1:{connected:false},camera2:{mask:28}});
      await expect(card(first).locator('.capture-status')).toContainText('disconnected');
      await expect(target(second,1)).toHaveAttribute('data-state','unknown');
      await expect(target(second,3)).toHaveAttribute('data-state','fallen');
      await choose('manual');
      for(const n of [1,4,5]) {await target(first,n).tap(); await expect(target(second,n)).toHaveAttribute('data-state','fallen');}
      await expect(monitor.locator('#lane-2 .fallen')).toHaveCount(3);
      let after=await state();assert.equal(after.lanes['1'].current_bout_id,bout);assert.equal(after.bouts[bout].bib,52);
      assert.deepEqual(after.bouts[bout].fallen_target_ids,before.bouts[bout].fallen_target_ids);
      write({camera1:{mask:9},camera2:{mask:28}});
      await choose('mixed');
      await expect(card(first).locator('.capture-status')).toContainText('connected');
      await expect(card(first).locator('[data-target-control="5"] .source-detail')).toHaveAttribute('data-automatic-state','standing');
      await expect(target(second,5)).toHaveAttribute('data-state','fallen');
      after=await state();assert.deepEqual(after.bouts[bout].fallen_target_ids,before.bouts[bout].fallen_target_ids);
      await card(first).locator('[data-action="override-release"][data-target="5"]').tap();
      await expect(target(second,5)).toHaveAttribute('data-state','standing');
      // Eine echte Rückstellung beendet sämtliche alten Übersteuerungen.
      write({camera1:{mask:0},camera2:{mask:28}});
      await expect(card(first).locator('.overridden')).toHaveCount(0);
      await expect(monitor.locator('#lane-1 .standing')).toHaveCount(5);
      const events=(await (await fetch(url+'/api/events')).json()).events;
      assert(events.some(event=>event.manual_input?.automatic_state==='standing' && event.manual_input.manual_state==='fallen'));
      assert(events.every(event=>!['shot','hit','miss'].includes(event.command.kind)));
    }
    for(const page of pages) assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  } finally {
    for(const context of contexts) await context.close();
    fixture.kill('SIGTERM');if(fixture.exitCode===null) await new Promise(resolve=>fixture.once('exit',resolve));
  }
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {await scenario(browser,true);await scenario(browser,false);
    console.log('Betriebsarten-Browserprüfung erfolgreich: manuell ohne Kamera/Simulation, zwei Tablets, Mischpriorität, Freigabe, Ausfall, Ersatzbetrieb, Rückwechsel und Rückstellung.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
