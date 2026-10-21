// Gesamt-ROI erfassen; erkannte Zielpolygone im Originalbild kontrollieren.
const byId = id => document.getElementById(id);
const canvas = byId("image"), context = canvas.getContext("2d");
let bitmap = null, quad = [], result = null, saved = null, busy = true, cameraId = null;

function status(text, error = false) {
  byId("status").textContent = text;
  byId("status").classList.toggle("error", error);
}

function controls() {
  byId("detect").disabled = busy || !bitmap || quad.length !== 4;
  byId("clear").disabled = busy || !bitmap;
  byId("align").disabled = busy || !bitmap || !saved;
  byId("file").disabled = busy;
  byId("capture").disabled = busy || !cameraId;
  byId("lane").disabled = busy;
}

function draw() {
  if (!bitmap) return;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0);
  const scale = Math.max(1, canvas.width / 700);
  function polygon(points, color, close, width = 2 * scale) {
    if (!points.length) return;
    context.strokeStyle = color;
    context.lineWidth = width;
    context.beginPath();
    points.forEach(([x, y], i) => i ? context.lineTo(x, y) : context.moveTo(x, y));
    if (close) context.closePath();
    context.stroke();
  }
  polygon(quad, "#ffd06b", quad.length === 4);
  context.font = `bold ${16 * scale}px system-ui`;
  quad.forEach(([x, y], i) => {
    context.fillStyle = "#ffd06b";
    context.beginPath(); context.arc(x, y, 4 * scale, 0, 2 * Math.PI); context.fill();
    context.fillText(String(i + 1), x + 6 * scale, y - 6 * scale);
  });
  // Targets can be only ~15 px wide in 4K overview images, so outline and label
  // follow the target size and the label sits above the target, not on it.
  context.textAlign = "center";
  for (const target of result?.targets || []) {
    const xs = target.polygon.map(([x]) => x), ys = target.polygon.map(([, y]) => y);
    const size = Math.max(...xs) - Math.min(...xs);
    const s = Math.min(scale, size / 8);
    polygon(target.polygon, "#4cffae", true, Math.max(1, s));
    context.font = `bold ${16 * s}px system-ui`;
    context.fillStyle = "#4cffae";
    context.fillText(String(target.target_id), target.center[0], Math.min(...ys) - 3 * s);
  }
  context.textAlign = "start";
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

async function loadSaved() {
  saved = null;
  byId("saved").textContent = "";
  const response = await request(`/api/lanes/${byId("lane").value}/calibration`);
  saved = response.calibration; cameraId = response.camera_id;
  if (cameraId && saved && !response.valid_for_camera) {
    status("Kamerazuordnung geändert. Neu kalibrieren.", true);
    saved = null;
  }
  byId("saved").textContent = saved
    ? `Grundkalibrierung gespeichert: ${new Date(saved.created_at).toLocaleString("de-DE")}.`
    : "Für diese Bahn ist noch keine Kalibrierung gespeichert.";
  if (bitmap && saved && saved.image_size[0] === bitmap.width && saved.image_size[1] === bitmap.height) {
    quad = saved.quad.map(point => [...point]);
    // Gespeicherte Koordinaten sind noch kein Erkennungsergebnis für das neue Bild.
    status("Gespeicherte ROI geladen. Bildverschiebung prüfen oder ROI neu markieren.");
  }
  controls(); draw();
}

canvas.addEventListener("pointerdown", event => {
  if (!bitmap || busy || quad.length === 4) return;
  const bounds = canvas.getBoundingClientRect();
  quad.push([Math.min(canvas.width - 1, Math.max(0, (event.clientX - bounds.left) * canvas.width / bounds.width)),
             Math.min(canvas.height - 1, Math.max(0, (event.clientY - bounds.top) * canvas.height / bounds.height))]);
  result = null;
  status(quad.length === 4 ? "ROI vollständig. Automatische Erkennung starten." : `${quad.length} von 4 ROI-Ecken markiert.`);
  controls(); draw();
});

byId("clear").onclick = () => { quad = []; result = null; status("Vier Ecken des gesamten Scheibenbereichs markieren."); controls(); draw(); };
byId("lane").onchange = async () => {
  quad = []; result = null; busy = true; controls(); draw();
  try { await loadSaved(); } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
};
async function loadImage(file) {
  quad = []; result = null;
  if (bitmap) bitmap.close();
  bitmap = null;
  canvas.style.display = "none";
  byId("placeholder").hidden = false;
  busy = true; controls();
  try {
    if (!file) return;
    bitmap = await createImageBitmap(file, {imageOrientation: "none"});
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    canvas.style.display = "block";
    byId("placeholder").hidden = true;
    status("Vier Ecken des gesamten Scheibenbereichs markieren.");
    await loadSaved();
  } catch (error) { status(`Bild konnte nicht geladen werden: ${error.message}`, true); }
  finally { busy = false; controls(); draw(); }
}
byId("file").onchange = event => loadImage(event.target.files[0] || null);
byId("capture").onclick = async () => {
  busy = true; controls();
  try {
    const response = await fetch(`/api/cameras/${cameraId}/frame`, {cache: "no-store"});
    if (!response.ok) throw new Error("Kein aktuelles Kamerabild verfügbar.");
    await loadImage(await response.blob());
  } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
};

async function detect(alignment) {
  busy = true; result = null; controls(); draw();
  status(alignment ? "Bildverschiebung wird geprüft …" : "Scheiben werden gesucht …");
  try {
    const form = new FormData();
    // Das Arbeitsbild darf keine eingezeichneten Kontrollbereiche enthalten.
    const plain = document.createElement("canvas");
    plain.width = bitmap.width; plain.height = bitmap.height;
    plain.getContext("2d").drawImage(bitmap, 0, 0);
    const image = await new Promise(resolve => plain.toBlob(resolve, "image/png"));
    if (!image) throw new Error("Bild konnte nicht übertragen werden.");
    form.append("image", image, "standbild.png");
    if (!alignment) form.append("quad", JSON.stringify(quad));
    result = (await request(`/api/lanes/${byId("lane").value}/calibration${alignment ? "/align" : ""}`, {method: "POST", body: form})).calibration;
    if (!alignment) {
      saved = result;
      byId("saved").textContent = `Grundkalibrierung gespeichert: ${new Date(result.created_at).toLocaleString("de-DE")}.`;
    }
    status(alignment ? `Fünf Scheiben bestätigt. Versatz: ${result.offset.map(x => x.toFixed(1)).join(" / ")} Pixel.`
      : "Fünf Scheiben erkannt und gespeichert. Grüne Scheibenbereiche 1–5 bitte visuell kontrollieren.");
  } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); draw(); }
}
byId("detect").onclick = () => detect(false);
byId("align").onclick = () => detect(true);

(async () => {
  controls();
  try {
    const state = await request("/api/state");
    Object.values(state.lanes).forEach(lane => {
      const option = document.createElement("option");
      option.value = lane.lane_id; option.textContent = `Bahn ${lane.lane_id}`;
      byId("lane").append(option);
    });
    const requestedLane = new URLSearchParams(location.search).get("lane");
    if ([...byId("lane").options].some(option => option.value === requestedLane)) byId("lane").value = requestedLane;
    await loadSaved();
  } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
})();
