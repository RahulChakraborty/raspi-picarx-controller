PiCar-X Wi-Fi Control and Telemetry System

This project implements a full network-controlled interface for the SunFounder PiCar-X using Python on Raspberry Pi and an Electron-based frontend on a laptop or desktop. The system allows real-time driving, live video streaming, and continuous telemetry updates over Wi-Fi. It demonstrates key IoT concepts such as bidirectional socket communication, asynchronous control, and live data visualization.

Features

Bidirectional Wi-Fi Control:
Custom TCP server receives driving commands (forward, back, left, right, center, stop) from an Electron client and sends continuous telemetry (~3 Hz).

Live Telemetry:
Reports direction, speed, distance, CPU temperature, and simulated battery status in JSON form for display in the web dashboard.

Persistent Steering:
Steering holds its position until a new direction command or an explicit “Center” command is sent.

Real-Time Camera Feed:
Picamera2 captures a live MJPEG stream served via Flask at http://<Pi IP>:8081/stream, embedded directly in the Electron UI.

Responsive Electron Dashboard:
Four tiles show (1) live camera, (2) connect/disconnect status and manual command input, (3) telemetry metrics, and (4) rolling logs.

Cross-Platform Client:
Electron app runs on Windows, macOS, and Linux with Node JS support.

System Architecture
Layer	Technology	Function
Hardware	Raspberry Pi 4 + PiCar-X HAT	Motor, steering, sensors
Camera Server	Flask + Picamera2	MJPEG stream on port 8081
Control Server	Python socket + selectors	Receives commands and pushes telemetry
Frontend	Electron JS (HTML + JS)	User interface with keyboard and arrow controls
Protocol	Plain TCP (line-based)	Commands terminated by \n; telemetry as JSON
Installation and Setup

On Raspberry Pi

sudo apt update
sudo apt install -y python3-picamera2 python3-flask python3-pil
git clone <repo_url> && cd Lab_2
sudo -E python3 wifi_server_reactor.py
sudo -E python3 cam_server_picamera2.py


The Wi-Fi server listens on port 65432; the camera feed runs on 8081.
Both can be enabled as systemd services for auto-start.

On Desktop (Electron Client)

npm install
npm start


Enter the Pi’s IP and ports in the Connection tile, press Save & Reconnect, and control the car with arrow keys or W/A/S/D.
The Live Camera tile automatically binds to the Pi’s /stream endpoint.

Operation

Hold W/S or ↑/↓ to drive forward/back.

Press A/D or ←/→ to turn and maintain that steering until “Center.”

Observe telemetry values updating every few seconds.

Logs show [TX], [ACK], and [CMD] confirmations for every command.

Troubleshooting

No movement: verify battery ON, run printf "forward\n" | nc <Pi IP> 65432 to test.

No camera: check libcamera-hello -t 2000; adjust ribbon or permissions.

High latency: lower camera resolution to 640×480 or reduce telemetry rate.
