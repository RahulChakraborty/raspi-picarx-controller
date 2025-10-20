#!/usr/bin/env python3
# Wi-Fi control server for SunFounder PiCar-X using a non-blocking selector loop.
import atexit
import json
import os
import selectors
import socket
import time
from typing import Dict, Tuple

HOST, PORT = "0.0.0.0", 65432

# ==== Hardware layer (PiCar-X) ================================================
try:
    from picarx import Picarx
    px = Picarx()
except Exception as e:
    print("[ERROR] Failed to import/use picarx:", e)
    px = None

CRUISE_SPEED = 80       # give it enough oomph for testing
DIR_MAX_ANGLE = 22      # degrees

def set_motion(motion: str):
    if not px: return
    m = motion.lower()
    if   m == "forward": px.forward(CRUISE_SPEED)
    elif m == "back":    px.backward(CRUISE_SPEED)
    elif m == "stop":    px.stop()
    else:                px.stop()

def set_steer(direction: str):
    if not px: return
    d = direction.lower()
    if   d == "left":   px.set_dir_servo_angle(-DIR_MAX_ANGLE)
    elif d == "right":  px.set_dir_servo_angle(+DIR_MAX_ANGLE)
    elif d == "center": px.set_dir_servo_angle(0)

def hw_safe_stop():
    try:
        set_motion("stop"); set_steer("center")
    except Exception:
        pass

@atexit.register
def _cleanup():
    hw_safe_stop()

# ==== Telemetry (safe, stubbed if needed) =====================================
def _cpu_temp_c() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 0.0

# Minimal telemetry state we maintain here
_telem = {
    "direction": "stop",
    "speed_mps": 0.0,
    "distance_m": 0.0,
    "tempC": _cpu_temp_c(),
    "wifi_return_value": {"battery": 80, "moving": "stop", "steer": "center"},
}
_last_telem_time = time.time()

def telemetry_tick():
    # very basic odometer estimate
    global _last_telem_time, _telem
    now = time.time()
    dt = now - _last_telem_time
    _last_telem_time = now

    speed = _telem["speed_mps"]
    _telem["distance_m"] = round(_telem["distance_m"] + speed * dt, 2)
    _telem["tempC"] = _cpu_temp_c()
    return json.dumps(_telem)

def apply_cmd(cmd: str):
    """Apply a single command to hardware and update telemetry."""
    c = (cmd or "").strip().lower()
    print(f"[CMD] -> {c}", flush=True)

    if   c == "forward":
        set_motion("forward")
        _telem["direction"] = "forward"
        _telem["wifi_return_value"]["moving"] = "forward"
        _telem["speed_mps"] = 0.55  # nominal test value
    elif c == "back":
        set_motion("back")
        _telem["direction"] = "back"
        _telem["wifi_return_value"]["moving"] = "back"
        _telem["speed_mps"] = 0.55
    elif c == "stop":
        set_motion("stop")
        _telem["direction"] = "stop"
        _telem["wifi_return_value"]["moving"] = "stop"
        _telem["speed_mps"] = 0.0
    elif c == "left":
        set_steer("left")
        _telem["wifi_return_value"]["steer"] = "left"
    elif c == "right":
        set_steer("right")
        _telem["wifi_return_value"]["steer"] = "right"
    elif c == "center":
        set_steer("center")
        _telem["wifi_return_value"]["steer"] = "center"
    elif c == "resetodo":
        _telem["distance_m"] = 0.0
    else:
        print(f"[WARN] unknown cmd: {c}", flush=True)

# ==== Reactor server using selectors =========================================
sel = selectors.DefaultSelector()

class ConnState:
    def __init__(self, sock: socket.socket, addr: Tuple[str, int]):
        self.sock = sock
        self.addr = addr
        self.buf_in = ""     # accumulate until '\n'
        self.last_push = 0.0
        self.closed = False
        # make the socket non-blocking and keepalive-ish
        self.sock.setblocking(False)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass

def accept(sock: socket.socket):
    conn, addr = sock.accept()
    print(f"[+] Client {addr} connected", flush=True)
    state = ConnState(conn, addr)
    sel.register(conn, selectors.EVENT_READ, data=state)

def service(state: ConnState):
    try:
        chunk = state.sock.recv(4096)
        if not chunk:
            raise ConnectionResetError("peer closed")
        s = chunk.decode("utf-8", errors="ignore")
        print(f"[RX {state.addr}] {repr(s)}", flush=True)
        state.buf_in += s.replace("\r\n", "\n")
        while True:
            nl = state.buf_in.find("\n")
            if nl == -1:
                break
            line = state.buf_in[:nl]
            state.buf_in = state.buf_in[nl+1:]
            cmd = line.strip()
            if not cmd:
                continue
            # ACK the command so client can confirm write path
            try:
                state.sock.sendall((f"ACK:{cmd}\n").encode("utf-8"))
            except Exception as e:
                print(f"[ACK ERR {state.addr}] {e}", flush=True)
            apply_cmd(cmd)
    except (BlockingIOError, InterruptedError):
        pass
    except Exception as e:
        print(f"[-] {state.addr} disconnected: {e}", flush=True)
        close_conn(state)

def push_telem_if_due(state: ConnState, hz: float = 3.0):
    now = time.time()
    if now - state.last_push >= 1.0 / hz:
        payload = telemetry_tick() + "\n"
        try:
            state.sock.sendall(payload.encode("utf-8"))
            state.last_push = now
        except Exception as e:
            print(f"[SEND ERR {state.addr}] {e}", flush=True)
            close_conn(state)

def close_conn(state: ConnState):
    if state.closed:
        return
    state.closed = True
    try:
        sel.unregister(state.sock)
    except Exception:
        pass
    try:
        state.sock.close()
    except Exception:
        pass
    hw_safe_stop()

def main():
    # listening socket
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # reduce Nagle delays (optional)
    try:
        lsock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    lsock.bind((HOST, PORT))
    lsock.listen(10)
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)
    print(f"[PiCar-X] Reactor Wi-Fi server on {HOST}:{PORT}", flush=True)

    try:
        while True:
            # 100ms heartbeat – keeps loop responsive
            for key, _ in sel.select(timeout=0.1):
                if key.data is None:
                    accept(key.fileobj)
                else:
                    service(key.data)

            # send telemetry to all active clients ~3 Hz
            for key in list(sel.get_map().values()):
                if key.data and isinstance(key.data, ConnState):
                    push_telem_if_due(key.data, hz=3.0)
    finally:
        # clean shutdown
        for key in list(sel.get_map().values()):
            if key.data and isinstance(key.data, ConnState):
                close_conn(key.data)
        try:
            sel.unregister(lsock); lsock.close()
        except Exception:
            pass
        hw_safe_stop()

if __name__ == "__main__":
    main()
