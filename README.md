# NTP-GPS-PPS-MQTT-HA

Home Assistant status dashboard for a GPS/PPS-disciplined NTP server running on a Raspberry Pi.

## Overview

A collection of Python bridge scripts that read live data from a GPS receiver, NTP daemon, and system health metrics — then publish everything to Home Assistant via MQTT with full auto-discovery. The end goal is an ESP32-based hardware display showing GPS satellite and time data in real time.

## Architecture

```
RPi: GPSD   → gps_mqtt.py    → MQTT → HA device: "GPS Monitor"
RPi: psutil → system_mqtt.py → MQTT → HA device: "RPi System Monitor"
RPi: ntpq   → ntp_mqtt.py    → MQTT → HA device: "NTP Monitor"
```

## Scripts

| Script | Purpose | Runs on |
|--------|---------|---------|
| `gps_monitor.py` | Terminal display — live satellite table + TPV | Mac (dev/test) |
| `gps_mqtt.py` | GPSD → MQTT bridge with HA auto-discovery | RPi (systemd) |
| `system_mqtt.py` | System health → MQTT bridge with HA auto-discovery | RPi (systemd) |
| `ntp_mqtt.py` | NTPd status → MQTT bridge with HA auto-discovery | RPi (systemd) |

## Infrastructure

| Component | Details |
|-----------|---------|
| GPS Server | RPi hostname `hawk`, IP `192.168.1.167`, Raspbian |
| GPS Device | `/dev/ttyAMA0` (MTK-3301, GPS-only) |
| GPSD Version | 3.17 |
| MQTT Broker | Home Assistant at `homeassistant.iot.home.arpa:8883` (TLS) |

## Requirements

- Python 3.6+
- `gps_monitor.py` — no external dependencies (standard library only)
- `gps_mqtt.py`, `system_mqtt.py`, `ntp_mqtt.py` — require `paho-mqtt` and `psutil`

## Usage

### Terminal Monitor (Mac / dev)

```bash
./gps_monitor.py                  # default host 192.168.1.167
./gps_monitor.py 192.168.1.100    # custom host
```

### RPi Services

The three MQTT bridge scripts run as systemd services on the RPi. Copy and fill in credentials first:

```bash
sudo cp monitoring.env.example /etc/monitoring/monitoring.env
sudo chmod 600 /etc/monitoring/monitoring.env
```

Each service uses this unit file pattern (save to `/etc/systemd/system/<service-name>.service`):

```ini
[Unit]
Description=<description>
After=network.target
# Also add: gpsd.service — for gps-monitor.service only

[Service]
EnvironmentFile=/etc/monitoring/monitoring.env
ExecStart=/usr/bin/python3 /etc/monitoring/<script>.py
Restart=on-failure
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

Enable and start each service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gps-monitor.service system-monitor.service ntp-monitor.service
sudo systemctl start gps-monitor.service system-monitor.service ntp-monitor.service
```

Check status:

```bash
sudo systemctl status gps-monitor.service
journalctl -u gps-monitor.service -f
```

## Configuration

MQTT publish groups are controlled via environment variables in `monitoring.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GPS_PUBLISH_SKY` | `true` | Enable satellite sky data |
| `GPS_PUBLISH_SKY_INTERVAL` | `0` | Publish interval in seconds (0 = every message) |
| `GPS_PUBLISH_STATUS` | `true` | Enable GPS status/DOP data |
| `GPS_PUBLISH_STATUS_INTERVAL` | `0` | Publish interval in seconds |
| `GPS_PUBLISH_POSITION` | `true` | Enable position data |
| `GPS_PUBLISH_POSITION_INTERVAL` | `0` | Publish interval in seconds |

See `monitoring.env.example` for all available options:

```ini
# MQTT Broker Configuration
# Copy this file to /etc/monitoring/monitoring.env and fill in your values
# Set permissions: chmod 600 /etc/monitoring/monitoring.env

MQTT_BROKER=<host>
MQTT_PORT=<port>
MQTT_USERNAME=<username>
MQTT_PASSWORD=<changeme>
MQTT_TLS=false

# GPS Monitor only
GPSD_HOST=localhost
GPSD_PORT=2947

# GPS Monitor message groups — toggle and set publish interval per group
# Set to false to disable a group entirely (removes sensors from HA)
# Interval in seconds: 0 = publish every message, N = publish at most once every N seconds
GPS_PUBLISH_SKY=true
GPS_PUBLISH_SKY_INTERVAL=0

GPS_PUBLISH_STATUS=true
GPS_PUBLISH_STATUS_INTERVAL=0

GPS_PUBLISH_POSITION=true
GPS_PUBLISH_POSITION_INTERVAL=0
```

## Testing

```bash
python3 -m pytest tests/ -v
```

## Next Phase — ESP32 Display

The ESP32 will subscribe to `gps_monitor/sky`, `gps_monitor/status`, and `gps_monitor/position` over WiFi and drive an IPS LCD or e-ink display. Candidate libraries: `TFT_eSPI` (ILI9341), `PubSubClient`/`ESP-MQTT`, `ArduinoJson`.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
