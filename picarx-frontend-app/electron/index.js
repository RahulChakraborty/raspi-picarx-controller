// index.js — editable IP/Port, persistent socket, camera bound to same IP

let net;
try { net = require("net"); }
catch (e) {
  alert("Electron nodeIntegration disabled. In main.js: webPreferences = { nodeIntegration: true, contextIsolation: false }");
  throw e;
}

// -------- Config (editable via UI) --------
const DEFAULTS = { ip: "10.129.172.9", port: 65432, camPort: 8081 };
function loadConfig() {
  try { return JSON.parse(localStorage.getItem("car_cfg")) || { ...DEFAULTS }; }
  catch { return { ...DEFAULTS }; }
}
function saveConfig(cfg) {
  localStorage.setItem("car_cfg", JSON.stringify(cfg));
}
let CFG = loadConfig();

// -------- DOM helpers --------
const $ = id => document.getElementById(id);
const setText = (id, v) => { const n=$(id); if(n) n.textContent = (v ?? "—"); };
const setDot = ok => { const d=$("statusDot"); if(d) d.classList.toggle("ok", !!ok); };
const setStatus = (t, ok=false)=>{ setText("statusText", t); setDot(ok); };
function rxlog(line) {
  const box = $("rxlog"); if (!box) return;
  if (box.textContent.length > 12000) box.textContent = box.textContent.slice(-9000);
  box.textContent += line + "\n"; box.scrollTop = box.scrollHeight;
}

// -------- Socket state --------
let sock = null, connecting = false, reconnectTimer = null, rxBuf = "";

// -------- Apply config to UI + camera and reconnect --------
function applyConfig() {
  setText("srvAddr", CFG.ip);
  setText("srvPort", CFG.port);
  const camUrl = `http://${CFG.ip}:${CFG.camPort}/stream`;
  setText("camUrlText", camUrl);
  const cam = $("cam"); if (cam) cam.src = camUrl;

  // reconnect socket
  disconnect();
  connect();
}
function saveApplyConfig() {
  const ip = $("cfgIp")?.value?.trim() || CFG.ip;
  const port = parseInt($("cfgPort")?.value || CFG.port, 10);
  CFG = { ...CFG, ip, port: isNaN(port) ? CFG.port : port };
  saveConfig(CFG);
  applyConfig();
}

// -------- Connection --------
function connect() {
  if (connecting || (sock && !sock.destroyed)) return;
  clearTimeout(reconnectTimer);
  connecting = true; setStatus("connecting...");

  sock = net.createConnection({ host: CFG.ip, port: CFG.port }, () => {
    connecting = false; setStatus("connected", true); rxlog("[OK] connected");
    try { sock.setKeepAlive(true, 5000); } catch {}
  });

rxBuf = "";
sock.on("data", (chunk) => {
  const text = chunk.toString("utf8");
  rxlog("[RX] " + JSON.stringify(text));
  rxBuf += text.replace(/\r\n/g, "\n");        // normalize CRLF to LF
  const parts = rxBuf.split("\n");
  rxBuf = parts.pop();                         // keep last partial

  for (const line of parts) {
    if (!line.trim()) continue;
    $("api-response").textContent = line;         // show last line plainly
    setText("lastRx", new Date().toLocaleTimeString());

    if (line.startsWith("ACK:")) {
      rxlog("[ACK] " + line.slice(4));
      continue;
    }
    try {
      const obj = JSON.parse(line);
      setText("direction",  obj.direction);
      setText("speed",      obj.speed_mps);
      setText("distance",   obj.distance_m);
      setText("temperature",obj.tempC);
      const core = obj.wifi_return_value || {};
      setText("battery", core.battery);
      setText("moving",  core.moving);
      setText("steer",   core.steer);
      setText("ts",      new Date().toLocaleTimeString());
    } catch {
      // non-JSON line; already logged above
    }
  }
});


  sock.on("error", (err) => { setStatus("error: " + err.message); rxlog("[ERR] " + err.message); });
  sock.on("close", () => {
    setStatus("disconnected");
    rxlog("[INFO] closed");
    connecting = false; sock = null;
    reconnectTimer = setTimeout(connect, 1500);
  });
}

function disconnect() {
  clearTimeout(reconnectTimer);
  if (sock && !sock.destroyed) { try { sock.end(); } catch {} try { sock.destroy(); } catch {} }
  sock = null; setStatus("disconnected"); rxlog("[INFO] manual disconnect");
}

function sendLine(cmd) {
  if (!cmd || !cmd.trim()) return;
  if (!sock || sock.destroyed) {
    rxlog("[WARN] no socket — connecting then sending: " + cmd);
    connect();
    setTimeout(() => sendLine(cmd), 250);
    return;
  }
  try {
    sock.write(cmd + "\n");         // <-- newline REQUIRED
    setText("lastTx", cmd);
    rxlog("[TX] " + cmd);
  } catch (e) {
    rxlog("[ERR] send: " + e.message);
  }
}


function sendOnce() {
  const input = $("message")?.value?.trim();
  if (!input) return;
  sendLine(input);
}


// -------- Arrow + keyboard controls --------
const pressed = new Set();
function motionFromKeys(){ if(pressed.has("KeyW")) return "forward"; if(pressed.has("KeyS")) return "back"; return null; }
function steerFromKeys(){ if(pressed.has("KeyA")) return "left"; if(pressed.has("KeyD")) return "right"; return null; }

document.addEventListener("keydown", e => {
  if (pressed.has(e.code)) return; pressed.add(e.code);
  const map = { KeyW:"upArrow", KeyS:"downArrow", KeyA:"leftArrow", KeyD:"rightArrow" };
  if (map[e.code]) $(map[e.code]).classList.add("pressed");
  const m = motionFromKeys(); if (m) sendLine(m);
  const s = steerFromKeys();  if (s) sendLine(s);
});
document.addEventListener("keyup", e => {
  pressed.delete(e.code);
  const map = { KeyW:"upArrow", KeyS:"downArrow", KeyA:"leftArrow", KeyD:"rightArrow" };
  if (map[e.code]) $(map[e.code]).classList.remove("pressed");
  if (e.code === "KeyW" || e.code === "KeyS") sendLine("stop");
  // if (e.code === "KeyA" || e.code === "KeyD") sendLine("center");
});

// arrows (pointer)
function attachArrowHandlers() {
  [
    { id:"upArrow", down:"forward", up:"stop" },
    { id:"downArrow", down:"back",  up:"stop" },
    { id:"leftArrow", down:"left",  up:null },
    { id:"rightArrow",down:"right", up:null }
  ].forEach(({id,down,up})=>{
    const el = $(id); if (!el) return;
    el.addEventListener("pointerdown", e => { e.preventDefault(); el.classList.add("pressed"); sendLine(down); });
    ["pointerup","pointerleave","pointercancel"].forEach(ev =>
      el.addEventListener(ev, e => { e.preventDefault(); el.classList.remove("pressed"); sendLine(up); })
    );
  });
}

// keyboard (W/A/S/D)
document.addEventListener("keydown", e => {
  if (pressed.has(e.code)) return; pressed.add(e.code);
  const map = { KeyW:"upArrow", KeyS:"downArrow", KeyA:"leftArrow", KeyD:"rightArrow" };
  if (map[e.code]) 
    $(map[e.code]).classList.add("pressed");
  const m = motionFromKeys(); if (m) sendLine(m);
  const s = steerFromKeys();  if (s) sendLine(s);
});
document.addEventListener("keyup", e => {
  pressed.delete(e.code);
  const map = { KeyW:"upArrow", KeyS:"downArrow", KeyA:"leftArrow", KeyD:"rightArrow" };
  if (map[e.code]) $(map[e.code]).classList.remove("pressed");
  if (e.code === "KeyW" || e.code === "KeyS") sendLine("stop");
  if (e.code === "KeyA" || e.code === "KeyD") sendLine("center");
});


// -------- Boot --------
window.addEventListener("DOMContentLoaded", () => {
  // seed form
  if ($("cfgIp"))   $("cfgIp").value = CFG.ip;
  if ($("cfgPort")) $("cfgPort").value = CFG.port;

  // show current server/camera targets and connect
  applyConfig();
  attachArrowHandlers();
});

// Expose to HTML
window.connect = connect;
window.disconnect = disconnect;
window.sendOnce = sendOnce;
window.saveApplyConfig = saveApplyConfig;
