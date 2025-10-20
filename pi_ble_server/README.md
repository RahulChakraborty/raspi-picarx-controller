PiCarX Bluetooth + Electron Control System

This project enables real-time control and telemetry of a PiCar-X robot using Bluetooth Low Energy (BLE) and a cross-platform Electron desktop application. The Raspberry Pi runs a Python server (picarx_ble.py) that exposes a custom GATT service with characteristics for movement control, telemetry, logs, and status, while streaming live camera video through a lightweight Flask web server.

The Electron app connects via BLE, displays sensor data, live video, and control buttons for forward, reverse, steering, and stop. Communication is secured over BLE using custom 128-bit UUIDs.

Installation on the Pi is automated with install.sh, which sets up BlueZ, Picamera2, Bluezero, and a systemd service (picarx-ble.service) for auto-startup. The desktop app uses @abandonware/noble for BLE connectivity and supports Node v14+.

To run:

Enable Bluetooth (bluetoothctl power on).

Start the server: sudo systemctl start picarx-ble.

Launch the node connect app (node quick-connect).

Optionally set PICARX_ADDR=<MAC> to connect directly.

The system demonstrates seamless hardware–software integration, live telemetry, and IoT communication principles, providing an extendable base for autonomous navigation and multi-sensor robotics projects.
