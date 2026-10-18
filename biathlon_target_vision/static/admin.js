// RTSP-Zugangsdaten nur schreiben; Status und JPEG-Vorschau ohne URL lesen.
(() => {
 const el=id=>document.getElementById(id); let cameras=[], selected='', previewBusy=false, sourceBusy=false;
 async function request(url, options) {const r=await fetch(url, options);const data=await r.json();if(!r.ok)throw Error(data.detail);return data;}
 function display() {
  const camera=cameras.find(c=>c.id===selected);
  el('camera-id').value=camera?.id||'';el('camera-id').readOnly=!!camera;
  el('camera-name').value=camera?.name||'';el('camera-url').value='';el('camera-lanes').value=camera?.lane_ids.join(',')||'';
  el('remove').disabled=!camera;el('preview').hidden=true;el('calibrations').replaceChildren();
  for(const lane of camera?.lane_ids||[]){const a=document.createElement('a');a.href=`/calibration?lane=${lane}`;a.textContent=`Bahn ${lane} kalibrieren`;el('calibrations').append(a);}
 }
 async function load() {
  cameras=(await request('/api/cameras')).cameras;
  el('camera').replaceChildren(new Option('Neue Kamera',''),...cameras.map(c=>new Option(c.name,c.id)));
  el('camera').value=selected;const camera=cameras.find(c=>c.id===selected);
  el('connection').textContent=camera ? (camera.connected?'Kamera verbunden':'Kein aktuelles Kamerabild – Verbindung wird erneut versucht') : '';
 }
 el('camera').onchange=()=>{selected=el('camera').value;display();load().catch(showError);};
 function showError(error){el('status').textContent=error.message;}
 el('camera-form').onsubmit=async event=>{event.preventDefault();try{
  const id=el('camera-id').value;
  await request(selected?`/api/cameras/${selected}`:'/api/cameras',{method:selected?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,name:el('camera-name').value,url:el('camera-url').value,lane_ids:el('camera-lanes').value.trim()?el('camera-lanes').value.split(',').map(x=>Number(x.trim())):[]})});
  selected=id;await load();display();el('status').textContent='Kamera gespeichert.';
 }catch(error){showError(error);}};
 el('remove').onclick=async()=>{try{await request(`/api/cameras/${selected}`,{method:'DELETE'});selected='';await load();display();el('status').textContent='Kamera entfernt.';}catch(error){showError(error);}};
 setInterval(async()=>{if(!selected||previewBusy)return;previewBusy=true;try{
  await load();const r=await fetch(`/api/cameras/${selected}/frame`,{cache:'no-store'});
  if(r.ok){const url=URL.createObjectURL(await r.blob());const old=el('preview').src;el('preview').src=url;el('preview').hidden=false;if(old.startsWith('blob:'))URL.revokeObjectURL(old);}else el('preview').hidden=true;
 }catch(error){showError(error);}finally{previewBusy=false;}},1000);
 // Vorhandener Quellenbefehl bleibt administrativ; keine zweite Konfiguration.
 const states={standing:'aufgerichtet',fallen:'gefallen',unknown:'unbekannt'};
 let lanes={};
 async function loadSources(){
  if(sourceBusy)return;
  const state=await request('/api/state');lanes=state.lanes;
  const content=Object.values(lanes).map(lane=>{
   const camera=state.capture.cameras.find(item=>item.lane_ids.includes(lane.lane_id));
   const status=!camera?'Keine Kamera zugeordnet':!state.capture.running?'Erfassung gestoppt':!camera.connected?'Kamera getrennt':lane.automatic_targets.includes('unknown')?'Beobachtung unklar':'Kamera liefert Zustände';
   const corrections=lane.manual_targets.map((value,index)=>value===null?'':`Scheibe ${index+1}: ${states[value]}`).filter(Boolean);
   return `<section><h3>Bahn ${lane.lane_id}</h3>
    <label><input type="checkbox" data-source-lane="${lane.lane_id}" ${lane.mode!=='manual'?'checked':''}> Automatische Beobachtungen verwenden</label>
    <p>${status}</p><p>Automatisch: ${lane.automatic_targets.map(value=>states[value]).join(' · ')}</p>
    <p>Manuelle Korrekturen: ${corrections.join(' · ')||'keine'}</p></section>`;
  }).join('');
  if(el('sources').innerHTML!==content)el('sources').innerHTML=content;
 }
 el('sources').onchange=async event=>{
  const id=event.target.dataset.sourceLane;if(!id||sourceBusy)return;
  sourceBusy=true;event.target.disabled=true;
  try{await request(`/api/lanes/${id}/mode`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({lane_id:Number(id),mode:event.target.checked?'automatic':'manual',expected_control_revision:lanes[id].control_revision})});}
  catch(error){showError(error);}
  finally{sourceBusy=false;await loadSources().catch(showError);}
 };
 setInterval(()=>loadSources().catch(showError),2000);
 loadSources().catch(showError);
 load().then(display).catch(showError);
})();
