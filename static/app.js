const $ = (id) => document.getElementById(id);
const LABELS = {
  beneficiary: "Beneficiary", visit_type: "Visit type", weight_kg: "Weight",
  vaccines_given_today: "Vaccines given today", vaccines_due: "Vaccines due",
  next_visit_date: "Next visit", danger_signs: "Danger signs", notes: "Notes",
};
const STATES = { AWAIT_ID: "Waiting for ID", DICTATION: "Listening to notes", READBACK: "Confirm read-back" };
const VISIT = { ANC: "ANC checkup", HBNC: "Newborn visit (HBNC)", PNC: "Postnatal visit", IMMUNISATION: "Immunisation" };

let ws = null, ctx = null, micStream = null, worklet = null, running = false;
let playing = [], playHead = 0, playChain = Promise.resolve();

function setStatus(text) { $("status").textContent = text; }

function ensureCtx() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

function connect() {
  if (ws && ws.readyState <= 1) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws?lang=${$("lang").value}`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => resolve();
    ws.onerror = () => reject(new Error("WebSocket error"));
    ws.onmessage = onMessage;
    ws.onclose = () => { if (running) stopMic(); setStatus("Disconnected. Tap to start again."); ws = null; };
  });
}

async function startMic() {
  ensureCtx();
  await ctx.audioWorklet.addModule("/static/pcm-worklet.js");
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  await connect();
  const src = ctx.createMediaStreamSource(micStream);
  worklet = new AudioWorkletNode(ctx, "pcm16k");
  const mute = ctx.createGain(); mute.gain.value = 0;   // keeps the node running without echoing the mic
  src.connect(worklet).connect(mute).connect(ctx.destination);
  worklet.port.onmessage = (e) => { if (ws && ws.readyState === 1) ws.send(e.data); };
  running = true;
  $("mic").classList.add("live"); $("mic").setAttribute("aria-pressed", "true");
  $("mic-label").textContent = "End visit";
  setStatus("Listening… speak naturally.");
}

function stopMic() {
  running = false;
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "commit" }));
  if (worklet) { worklet.port.onmessage = null; worklet.disconnect(); worklet = null; }
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
  $("mic").classList.remove("live"); $("mic").setAttribute("aria-pressed", "false");
  $("mic-label").textContent = "Start visit";
  setStatus("Paused. Tap to continue.");
}

$("mic").addEventListener("click", async () => {
  try { running ? stopMic() : await startMic(); }
  catch (e) { setStatus("Microphone not available: " + e.message); }
});

$("lang").addEventListener("change", () => {
  if (ws) { ws.close(); ws = null; }
  if (running) stopMic();
  $("log").replaceChildren();
  setStatus("Language changed. Tap to start.");
});

$("typed").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("typed-input").value.trim();
  if (!text) return;
  ensureCtx();
  await connect();
  ws.send(JSON.stringify({ type: "text", text }));
  $("typed-input").value = "";
});

// ---------- audio playback ----------
function b64ToBuffer(b64) {
  const bin = atob(b64); const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}
async function play(b64) {
  ensureCtx();
  const audio = await ctx.decodeAudioData(b64ToBuffer(b64));
  const src = ctx.createBufferSource();
  src.buffer = audio; src.connect(ctx.destination);
  const t = Math.max(ctx.currentTime, playHead);
  src.start(t); playHead = t + audio.duration;
  playing.push(src);
  src.onended = () => { playing = playing.filter((s) => s !== src); };
}
function stopPlayback() {
  playing.forEach((s) => { try { s.stop(); } catch (_) {} });
  playing = []; playHead = 0;
}

// ---------- messages ----------
function onMessage(ev) {
  const m = JSON.parse(ev.data);
  switch (m.type) {
    case "say":
      addLog("agent", m.text);
      if (m.audio) playChain = playChain.then(() => play(m.audio)).catch(() => {});
      if (m.agent_ms != null) {
        const stt = m.stt_ms != null ? `STT ${m.stt_ms} ms + ` : "";
        $("metric").textContent = `${stt}agent ${m.agent_ms} ms to first reply`;
      }
      break;
    case "transcript": addLog("user", m.text, m.lang); break;
    case "speech_start": if ($("bargein").checked && playing.length) stopPlayback(); break;
    case "form": renderForm(m); break;
    case "followups": renderFollowups(m.items || []); break;
    case "error": setStatus(m.message); break;
  }
}

function addLog(who, text, lang) {
  const div = document.createElement("div");
  const isAlert = who === "agent" && /PHC/.test(text) && /(खतरे|ಅಪಾಯ)/.test(text);
  div.className = `msg ${who}${isAlert ? " alert" : ""}`;
  const small = document.createElement("small");
  small.textContent = who === "user" ? `You${lang ? " · " + lang : ""}` : "ASHA Vaani (AI)";
  div.append(small, document.createTextNode(text));
  $("log").append(div); $("log").scrollTop = $("log").scrollHeight;
}

function chips(list, cls = "") {
  const frag = document.createDocumentFragment();
  if (!list || !list.length) { const s = document.createElement("span"); s.className = "empty"; s.textContent = "None"; return s; }
  list.forEach((v) => { const c = document.createElement("span"); c.className = "chip " + cls; c.textContent = v; frag.append(c); });
  return frag;
}

function renderForm(m) {
  $("state").textContent = STATES[m.state] || m.state;
  const f = m.form || {}; const dl = $("form"); dl.replaceChildren();
  const row = (key, value) => {
    const dt = document.createElement("dt"); dt.textContent = LABELS[key];
    const dd = document.createElement("dd");
    if (value instanceof Node) dd.append(value);
    else if (value == null || value === "") { dd.className = "empty"; dd.textContent = "—"; }
    else dd.textContent = value;
    dl.append(dt, dd);
  };
  row("beneficiary", m.beneficiary ? `${m.beneficiary.name} · ID ${m.beneficiary.id} · ${m.beneficiary.type}` : null);
  row("visit_type", VISIT[f.visit_type] || f.visit_type);
  row("weight_kg", f.weight_kg != null ? `${f.weight_kg} kg` : null);
  row("vaccines_given_today", chips(f.vaccines_given_today));
  row("vaccines_due", chips(f.vaccines_due));
  row("next_visit_date", f.next_visit_date);
  row("danger_signs", chips(f.danger_labels, "danger"));
  row("notes", f.notes && f.notes.length ? f.notes.join("; ") : null);

  const banner = $("banner");
  if (f.danger_labels && f.danger_labels.length) {
    banner.textContent = `Danger sign: ${f.danger_labels.join(", ")}. Refer to PHC now. Record flagged.`;
    banner.hidden = false;
  } else banner.hidden = true;
}

function renderFollowups(items) {
  const ol = $("followups"); ol.replaceChildren();
  if (!items.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = "No saved visits yet."; ol.append(li); return; }
  items.forEach((r) => {
    const li = document.createElement("li");
    const flag = r.danger_signs && r.danger_signs.length;
    if (flag) { const s = document.createElement("span"); s.className = "flag"; s.textContent = "REFER TO PHC · "; li.append(s); }
    li.append(document.createTextNode(`${r.beneficiary_name} (ID ${r.beneficiary_id}) — next visit ${r.next_visit_date}`
      + (flag ? ` — ${r.danger_labels.join(", ")}` : "")));
    ol.append(li);
  });
}

fetch("/api/followups").then((r) => r.json()).then((d) => renderFollowups(d.items || [])).catch(() => {});
renderForm({ state: "AWAIT_ID", form: {} });
