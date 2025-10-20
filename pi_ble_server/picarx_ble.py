#!/usr/bin/env python3
"""
PiCarX BLE + Camera server
- BLE (GATT):
    Service 12345678-1234-5678-1234-56789abc0000
      Control   (write w/o response): ...1001  JSON 
{"throttle":-1..1,"steer":-1..1,"mode":"drive|stop"}
      Telemetry (notify)             : ...1002  JSON {"battery":%, 
"speed":cm_s, "temp":C, "distance":cm, "ts":ms}
      Logs      (notify)             : ...1003  UTF-8 lines
      Status    (read+notify)        : ...1004  JSON 
{"camera_url":"http://<ip>:8080/mjpeg","fw":"1.0.0"}
- Camera: MJPEG stream over HTTP at /mjpeg
"""

import json, time, threading, socket
from datetime import datetime
from threading import Event

# ---- HTTP camera (Picamera2) ----
from flask import Flask, Response
from picamera2 import Picamera2

# ---- BLE via BlueZ ----
from bluezero import adapter, peripheral

# Optional: real robot API if available
try:
    from picarx import Picarx
except Exception:
    Picarx = None

SERVICE_UUID = '12345678-1234-5678-1234-56789abc0000'
CTRL_UUID    = '12345678-1234-5678-1234-56789abc1001'
TEL_UUID     = '12345678-1234-5678-1234-56789abc1002'
LOG_UUID     = '12345678-1234-5678-1234-56789abc1003'
STAT_UUID    = '12345678-1234-5678-1234-56789abc1004'

# ---------- Camera ----------
app = Flask(__name__)
picam = Picamera2()

def start_camera():
    # 640x480 is a good default for Wi-Fi; raise if you like
    picam.configure(picam.create_video_configuration(main={"size": (640, 
480)}))
    picam.start()

def mjpeg_generator():
    import cv2
    while True:
        frame = picam.capture_array("main")
        ok, jpg = cv2.imencode('.jpg', frame)
        if ok:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + 
jpg.tobytes() + b'\r\n')

@app.route('/mjpeg')
def mjpeg():
    return Response(mjpeg_generator(), 
mimetype='multipart/x-mixed-replace; boundary=frame')

def run_flask():
    app.run(host='0.0.0.0', port=8080, threaded=True)

# ---------- Robot control / state ----------
px = Picarx() if Picarx else None
drive = {"throttle": 0.0, "steer": 0.0, "mode": "stop"}
ctrl_log = []
stop_evt = Event()

# Failsafe: stop motors if no control in this many seconds
FAILSAFE_SECONDS = 1.0
_last_ctrl_ts = time.time()

def apply_drive():
    if not px:
        return
    if drive["mode"] == "stop":
        px.stop(); return
    steer = max(-1.0, min(1.0, drive["steer"]))
    thr   = max(-1.0, min(1.0, drive["throttle"]))
    # Map steer ±1 → ±30°
    try:
        px.set_dir_servo_angle(int(30 * steer))
        if thr > 0:   px.forward(thr)
        elif thr < 0: px.backward(-thr)
        else:         px.stop()
    except Exception as e:
        ctrl_log.append(f"ERR drive {e}")

def telemetry_read():
    # Replace these stubs with actual sensors if available
    batt = 78.0            # %
    speed = 0.0            # cm/s
    temp = 45.0            # °C (e.g., CPU temp or motor driver)
    dist = 120.0           # cm (e.g., ultrasonic)
    return {"battery": batt, "speed": speed, "temp": temp, "distance": 
dist, "ts": int(time.time()*1000)}

def local_ip():
    # Works even if no DNS/hostname set
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def status_payload():
    return {"camera_url": f"http://{local_ip()}:8080/mjpeg", "fw": 
"1.0.0"}

# ---------- BLE handlers ----------
def on_ctrl_write(value, options):
    global _last_ctrl_ts
    try:
        msg = json.loads(value.decode('utf-8'))
        for k in ("throttle","steer","mode"):
            if k in msg: drive[k] = msg[k]
        _last_ctrl_ts = time.time()
        apply_drive()
        ctrl_log.append(f"{datetime.now().isoformat(timespec='seconds')} 
CTRL {msg}")
    except Exception as e:
        ctrl_log.append(f"ERR ctrl {e}")

def telemetry_loop(tel_char):
    while not stop_evt.is_set():
        tel_char.set_value(json.dumps(telemetry_read()).encode())
        time.sleep(0.2)  # 5 Hz

def log_loop(log_char):
    while not stop_evt.is_set():
        if ctrl_log:
            log_char.set_value(ctrl_log.pop(0).encode())
        else:
            time.sleep(0.1)

def status_loop(stat_char):
    while not stop_evt.is_set():
        stat_char.set_value(json.dumps(status_payload()).encode())
        time.sleep(5)

def failsafe_loop():
    # Stops motors if no control for FAILSAFE_SECONDS
    while not stop_evt.is_set():
        if time.time() - _last_ctrl_ts > FAILSAFE_SECONDS:
            drive["mode"] = "stop"
            try: apply_drive()
            except: pass
        time.sleep(0.05)

def make_peripheral():
    ad = adapter.Adapter()
    peri = peripheral.Peripheral(adapter_addr=ad.address, 
local_name='PiCarX', appearance=0x0080)

    ctrl = peripheral.Characteristic(CTRL_UUID, 
['write-without-response'], value=[], write_callback=on_ctrl_write)
    tel  = peripheral.Characteristic(TEL_UUID,  ['notify'], value=[])
    logc = peripheral.Characteristic(LOG_UUID,  ['notify'], value=[])
    stat = peripheral.Characteristic(STAT_UUID, ['read','notify'], 
value=json.dumps(status_payload()).encode())

    svc = peripheral.Service(SERVICE_UUID, True)
    for ch in (ctrl, tel, logc, stat): svc.add_characteristic(ch)
    peri.add_service(svc)

    threading.Thread(target=telemetry_loop, args=(tel,), 
daemon=True).start()
    threading.Thread(target=log_loop, args=(logc,), daemon=True).start()
    threading.Thread(target=status_loop, args=(stat,), 
daemon=True).start()
    threading.Thread(target=failsafe_loop, daemon=True).start()
    return peri

def main():
    start_camera()
    threading.Thread(target=run_flask, daemon=True).start()
    p = make_peripheral()
    try:
        p.publish()
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try: p.stop()
        except: pass
        try: picam.stop()
        except: pass

if __name__ == "__main__":
    main()

