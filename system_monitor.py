#!/usr/bin/env python3
# Copyright (C) 2026 Tache
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Claude Generated: version 1 - System monitor MQTT bridge with Home Assistant auto-discovery
#                                Reports CPU%, temperature, memory%, uptime, NTPd sync status
# Claude Generated: version 2 - Add NTPd detail: stratum, offset, refid, jitter via ntpq -c rv
# Claude Generated: version 3 - Consolidate NTPd detail into single sensor with JSON attributes
# Claude Generated: version 4 - Security C-1: add MQTT_CA_CERT env var for explicit CA cert verification
# Claude Generated: version 5 - Security C-2: warn at startup when TLS is disabled
# Claude Generated: version 6 - Security S-2: append hostname to MQTT client_id to prevent collisions
# Claude Generated: version 7 - Security S-4: validate port env vars (type and 1-65535 range)
# Claude Generated: version 8 - Split into two HA devices: RPi System Monitor and NTP Monitor
# Claude Generated: version 9 - Add NTPd clock time to NTP Monitor sensor
# Claude Generated: version 10 - Remove NTP (now in ntp_mqtt.py); system health only
# Claude Generated: version 11 - Add DS3231 RTC time, date, and battery status via sysfs and I2C
# Claude Generated: version 12 - Security: env var credentials, TLS support, exception logging
# Claude Generated: version 13 - Rename system_mqtt.py to system_monitor.py
# Claude Generated: version 14 - Add SYSTEM_PUBLISH_INTERVAL env var (default 30s)
# Claude Generated: version 15 - Pass MQTT config explicitly to connect_mqtt() instead of capturing globals
# Claude Generated: version 16 - Add memory detail, swap, disk usage, and load average metrics
# Claude Generated: version 17 - Add sys_time, sys_epoch, rtc_epoch, rtc_iso, rtc_drift fields
# Claude Generated: version 18 - Add _parse_interval() for validated interval env var parsing
# Claude Generated: version 19 - Security: preflight MQTT_CA_CERT path validation; empty string treated as unset
# Claude Generated: version 20 - Fix ruff lint: sort imports (paho before psutil), remove redundant 'r' mode from open() calls

"""
System Monitor MQTT Bridge - Publishes RPi system health metrics
to MQTT with Home Assistant auto-discovery.
"""

import datetime
import json
import os
import socket
import subprocess
import sys
import time

import paho.mqtt.client as mqtt
import psutil

# NOTE: _parse_port() and _parse_interval() are intentionally duplicated across the three
# monitor scripts. Each is deployed as a standalone file on the RPi and must be self-contained.

def _parse_port(env_var, default):
    """Parse a port number from an environment variable with bounds validation."""
    raw = os.environ.get(env_var, str(default))
    try:
        port = int(raw)
    except ValueError:
        sys.exit(f"Error: {env_var} must be an integer, got '{raw}'")
    if not 1 <= port <= 65535:
        sys.exit(f"Error: {env_var} must be between 1 and 65535, got {port}")
    return port


def _parse_interval(env_var, default):
    """Parse a non-negative integer interval (seconds) from an environment variable."""
    raw = os.environ.get(env_var, str(default))
    try:
        interval = int(raw)
    except ValueError:
        sys.exit(f"Error: {env_var} must be an integer, got '{raw}'")
    if interval < 0:
        sys.exit(f"Error: {env_var} must be >= 0, got {interval}")
    return interval

# ---------------------------------------------------------------------------
# Configuration — credentials loaded from environment variables
# Set via systemd EnvironmentFile or export before running
# ---------------------------------------------------------------------------
MQTT_BROKER   = os.environ.get('MQTT_BROKER')
MQTT_PORT     = _parse_port('MQTT_PORT', 8883)
MQTT_USERNAME = os.environ.get('MQTT_USERNAME')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')
MQTT_TLS      = os.environ.get('MQTT_TLS', 'true').lower() != 'false'
MQTT_CA_CERT  = os.environ.get('MQTT_CA_CERT') or None   # empty string treated as unset; None = system trust store

if not MQTT_BROKER or not MQTT_USERNAME or not MQTT_PASSWORD:
    sys.exit("Error: MQTT_BROKER, MQTT_USERNAME, and MQTT_PASSWORD environment variables required")
if not MQTT_TLS:
    print("Warning: MQTT_TLS is disabled — credentials and data transmitted in plaintext", file=sys.stderr)
if MQTT_CA_CERT and not os.path.isfile(MQTT_CA_CERT):
    sys.exit(f"Error: MQTT_CA_CERT path does not exist or is not a file: '{MQTT_CA_CERT}'")

UPDATE_INTERVAL  = _parse_interval('SYSTEM_PUBLISH_INTERVAL', 30)  # seconds between publishes
DISCOVERY_PREFIX = 'homeassistant'

# ---------------------------------------------------------------------------
# Device: RPi System Monitor
# ---------------------------------------------------------------------------
STATE_TOPIC        = 'system_monitor/state'
AVAILABILITY_TOPIC = 'system_monitor/availability'

DEVICE_INFO = {
    'identifiers': ['system_monitor'],
    'name': 'RPi System Monitor',
    'model': 'Raspberry Pi Bridge',
    'manufacturer': 'Tache',
}

SENSORS = [
    {
        'id': 'system_cpu_percent',
        'name': 'CPU Usage',
        'value_template': '{{ value_json.cpu_percent }}',
        'unit_of_measurement': '%',
        'state_class': 'measurement',
        'icon': 'mdi:cpu-64-bit',
    },
    {
        'id': 'system_cpu_temp',
        'name': 'CPU Temperature',
        'value_template': '{{ value_json.cpu_temp }}',
        'device_class': 'temperature',
        'unit_of_measurement': '°C',
        'state_class': 'measurement',
    },
    {
        'id': 'system_memory_percent',
        'name': 'Memory Usage',
        'value_template': '{{ value_json.memory_percent }}',
        'unit_of_measurement': '%',
        'state_class': 'measurement',
        'icon': 'mdi:memory',
    },
    {
        'id': 'system_uptime',
        'name': 'System Uptime',
        'value_template': '{{ value_json.uptime }}',
        'icon': 'mdi:timer-outline',
    },
    {
        'id': 'system_memory_total_mb',
        'name': 'Memory Total',
        'value_template': '{{ value_json.memory_total_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:memory',
    },
    {
        'id': 'system_memory_available_mb',
        'name': 'Memory Available',
        'value_template': '{{ value_json.memory_available_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:memory',
    },
    {
        'id': 'system_memory_used_mb',
        'name': 'Memory Used',
        'value_template': '{{ value_json.memory_used_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:memory',
    },
    {
        'id': 'system_memory_free_mb',
        'name': 'Memory Free',
        'value_template': '{{ value_json.memory_free_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:memory',
    },
    {
        'id': 'system_swap_percent',
        'name': 'Swap Usage',
        'value_template': '{{ value_json.swap_percent }}',
        'unit_of_measurement': '%',
        'state_class': 'measurement',
        'icon': 'mdi:swap-horizontal',
    },
    {
        'id': 'system_swap_total_mb',
        'name': 'Swap Total',
        'value_template': '{{ value_json.swap_total_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:swap-horizontal',
    },
    {
        'id': 'system_swap_used_mb',
        'name': 'Swap Used',
        'value_template': '{{ value_json.swap_used_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:swap-horizontal',
    },
    {
        'id': 'system_swap_free_mb',
        'name': 'Swap Free',
        'value_template': '{{ value_json.swap_free_mb }}',
        'unit_of_measurement': 'MB',
        'state_class': 'measurement',
        'icon': 'mdi:swap-horizontal',
    },
    {
        'id': 'system_disk_percent',
        'name': 'Disk Usage',
        'value_template': '{{ value_json.disk_percent }}',
        'unit_of_measurement': '%',
        'state_class': 'measurement',
        'icon': 'mdi:harddisk',
    },
    {
        'id': 'system_disk_total_gb',
        'name': 'Disk Total',
        'value_template': '{{ value_json.disk_total_gb }}',
        'unit_of_measurement': 'GB',
        'state_class': 'measurement',
        'icon': 'mdi:harddisk',
    },
    {
        'id': 'system_disk_used_gb',
        'name': 'Disk Used',
        'value_template': '{{ value_json.disk_used_gb }}',
        'unit_of_measurement': 'GB',
        'state_class': 'measurement',
        'icon': 'mdi:harddisk',
    },
    {
        'id': 'system_disk_free_gb',
        'name': 'Disk Free',
        'value_template': '{{ value_json.disk_free_gb }}',
        'unit_of_measurement': 'GB',
        'state_class': 'measurement',
        'icon': 'mdi:harddisk',
    },
    {
        'id': 'system_load_1m',
        'name': 'Load Average 1m',
        'value_template': '{{ value_json.load_1m }}',
        'state_class': 'measurement',
        'icon': 'mdi:gauge',
    },
    {
        'id': 'system_load_5m',
        'name': 'Load Average 5m',
        'value_template': '{{ value_json.load_5m }}',
        'state_class': 'measurement',
        'icon': 'mdi:gauge',
    },
    {
        'id': 'system_load_15m',
        'name': 'Load Average 15m',
        'value_template': '{{ value_json.load_15m }}',
        'state_class': 'measurement',
        'icon': 'mdi:gauge',
    },
    {
        'id': 'system_rtc_time',
        'name': 'RTC Time',
        'value_template': '{{ value_json.rtc_time }}',
        'icon': 'mdi:clock-digital',
    },
    {
        'id': 'system_rtc_date',
        'name': 'RTC Date',
        'value_template': '{{ value_json.rtc_date }}',
        'icon': 'mdi:calendar-clock',
    },
    {
        'id': 'system_rtc_battery',
        'name': 'RTC Battery',
        'value_template': '{{ value_json.rtc_battery }}',
        'icon': 'mdi:battery-clock-outline',
    },
    {
        'id': 'system_sys_time',
        'name': 'System Time',
        'value_template': '{{ value_json.sys_time }}',
        'icon': 'mdi:clock-outline',
    },
    {
        'id': 'system_sys_epoch',
        'name': 'System Epoch',
        'value_template': '{{ value_json.sys_epoch }}',
        'icon': 'mdi:timer-sand',
    },
    {
        'id': 'system_rtc_epoch',
        'name': 'RTC Epoch',
        'value_template': '{{ value_json.rtc_epoch }}',
        'icon': 'mdi:timer-sand',
    },
    {
        'id': 'system_rtc_iso',
        'name': 'RTC ISO Time',
        'value_template': '{{ value_json.rtc_iso }}',
        'icon': 'mdi:clock-digital',
    },
    {
        'id': 'system_rtc_drift',
        'name': 'RTC Drift',
        'value_template': '{{ value_json.rtc_drift }}',
        'unit_of_measurement': 's',
        'state_class': 'measurement',
        'icon': 'mdi:clock-alert-outline',
    },
]

# ---------------------------------------------------------------------------
# DS3231 RTC — I2C address 0x68
# ---------------------------------------------------------------------------
RTC_I2C_BUS     = 1
RTC_I2C_ADDRESS = 0x68
RTC_STATUS_REG  = 0x0F

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def get_cpu_percent():
    """CPU usage averaged over 1 second."""
    return round(psutil.cpu_percent(interval=1), 1)


def get_cpu_temp():
    """CPU temperature in Celsius. Returns None if unavailable."""
    try:
        temps = psutil.sensors_temperatures()
        for key in ('cpu_thermal', 'coretemp', 'k10temp', 'acpitz'):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
    except Exception as e:
        print(f"Error reading CPU temp: {e}")
    return None


def get_memory_percent():
    """Memory usage as a percentage."""
    return round(psutil.virtual_memory().percent, 1)


def get_memory_detail():
    """Memory breakdown: total, available, used, free in integer MB.
    'available' is preferable to 'free' — it includes reclaimable cache."""
    vm = psutil.virtual_memory()
    mb = 1024 * 1024
    return {
        'memory_total_mb':     vm.total     // mb,
        'memory_available_mb': vm.available // mb,
        'memory_used_mb':      vm.used      // mb,
        'memory_free_mb':      vm.free      // mb,
    }


def get_swap_detail():
    """Swap breakdown: percent, total, used, free. Bytes converted to integer MB."""
    sw = psutil.swap_memory()
    mb = 1024 * 1024
    return {
        'swap_percent':  round(sw.percent, 1),
        'swap_total_mb': sw.total // mb,
        'swap_used_mb':  sw.used  // mb,
        'swap_free_mb':  sw.free  // mb,
    }


def get_disk_usage():
    """Root filesystem usage: percent, total, used, free. Bytes converted to float GB."""
    du = psutil.disk_usage('/')
    gb = 1024 ** 3
    return {
        'disk_percent':  du.percent,
        'disk_total_gb': round(du.total / gb, 1),
        'disk_used_gb':  round(du.used  / gb, 1),
        'disk_free_gb':  round(du.free  / gb, 1),
    }


def get_load_average():
    """1/5/15-minute load averages. Returns None on platforms without support."""
    try:
        one, five, fifteen = psutil.getloadavg()
        return {
            'load_1m':  round(one,     2),
            'load_5m':  round(five,    2),
            'load_15m': round(fifteen, 2),
        }
    except AttributeError:
        return None


def get_uptime():
    """System uptime formatted as '3d 14h 22m'."""
    seconds = int(time.time() - psutil.boot_time())
    days    = seconds // 86400
    hours   = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"


def get_rtc_time():
    """RTC time from sysfs. Returns time string or None."""
    try:
        with open('/sys/class/rtc/rtc0/time') as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def get_rtc_date():
    """RTC date from sysfs. Returns date string or None."""
    try:
        with open('/sys/class/rtc/rtc0/date') as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def get_rtc_battery():
    """DS3231 battery status via I2C status register.
    Reads the OSF (Oscillator Stop Flag) bit — if set, the oscillator
    stopped at some point, indicating the battery died or was removed.
    Returns 'OK' or 'Replace'."""
    try:
        result = subprocess.run(
            ['i2cget', '-y', '-f', str(RTC_I2C_BUS), hex(RTC_I2C_ADDRESS), hex(RTC_STATUS_REG)],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            status = int(result.stdout.strip(), 16)
            # Bit 7 (0x80) is the Oscillator Stop Flag
            return 'Replace' if (status & 0x80) else 'OK'
    except Exception as e:
        print(f"Error reading RTC battery status: {e}")
    return 'Unknown'


def get_system_time():
    """System clock time and epoch. Uses the NTP-disciplined kernel clock.
    Always succeeds on POSIX systems."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        'sys_time':  now.isoformat(timespec='seconds'),
        'sys_epoch': int(time.time()),
    }


def get_rtc_epoch():
    """RTC time as Unix epoch integer from sysfs.
    Returns None on FileNotFoundError, PermissionError, ValueError, or OSError."""
    try:
        with open('/sys/class/rtc/rtc0/since_epoch') as f:
            return int(f.read().strip())
    except (FileNotFoundError, PermissionError, ValueError, OSError):
        return None


def get_rtc_iso(rtc_date, rtc_time):
    """Build ISO 8601 UTC string from already-read sysfs date and time strings.
    Accepts pre-read values to avoid the midnight-rollover race that would occur
    if date and time were read in separate sysfs calls.
    Returns None if either argument is None."""
    if rtc_date is None or rtc_time is None:
        return None
    return f"{rtc_date}T{rtc_time}+00:00"


def get_rtc_drift(sys_epoch, rtc_epoch):
    """Integer seconds the RTC is behind (+) or ahead (-) of the system clock.
    Pure arithmetic: sys_epoch - rtc_epoch.
    Callers must ensure both arguments are non-None before calling."""
    return sys_epoch - rtc_epoch


def collect_system_state():
    """Gather system health metrics and RTC status."""
    state = {
        'cpu_percent':    get_cpu_percent(),
        'memory_percent': get_memory_percent(),
        'uptime':         get_uptime(),
    }

    state.update(get_memory_detail())
    state.update(get_swap_detail())
    state.update(get_disk_usage())

    # System clock (NTP-disciplined) — always available on POSIX
    state.update(get_system_time())

    cpu_temp = get_cpu_temp()
    if cpu_temp is not None:
        state['cpu_temp'] = cpu_temp

    load = get_load_average()
    if load is not None:
        state.update(load)

    rtc_time = get_rtc_time()
    if rtc_time is not None:
        state['rtc_time'] = rtc_time
    rtc_date = get_rtc_date()
    if rtc_date is not None:
        state['rtc_date'] = rtc_date
    rtc_battery = get_rtc_battery()
    if rtc_battery is not None:
        state['rtc_battery'] = rtc_battery

    # RTC-derived fields — all three omitted together if either source is unavailable
    rtc_epoch = get_rtc_epoch()
    rtc_iso   = get_rtc_iso(rtc_date, rtc_time)
    if rtc_epoch is not None and rtc_iso is not None:
        state['rtc_epoch'] = rtc_epoch
        state['rtc_iso']   = rtc_iso
        state['rtc_drift'] = get_rtc_drift(state['sys_epoch'], rtc_epoch)

    return state


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

def publish_discovery(client):
    """Publish MQTT Discovery configs for system sensors."""
    for sensor in SENSORS:
        config_topic = f"{DISCOVERY_PREFIX}/sensor/{sensor['id']}/config"
        config_payload = {
            'name':               sensor['name'],
            'unique_id':          sensor['id'],
            'state_topic':        STATE_TOPIC,
            'availability_topic': AVAILABILITY_TOPIC,
            'value_template':     sensor['value_template'],
            'device':             DEVICE_INFO,
        }
        for key in ('device_class', 'unit_of_measurement', 'state_class', 'icon', 'json_attributes_topic'):
            if key in sensor:
                config_payload[key] = sensor[key]

        client.publish(config_topic, json.dumps(config_payload), retain=True)


def connect_mqtt(broker, port, username, password, tls, ca_cert):
    """Connect to broker and publish discovery configs."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'system_monitor_bridge_{socket.gethostname()}')
    client.username_pw_set(username, password)
    if tls:
        client.tls_set(ca_certs=ca_cert)   # None = verify against system trust store
    client.will_set(AVAILABILITY_TOPIC, 'offline', retain=True)

    try:
        client.connect(broker, port, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return None

    publish_discovery(client)
    client.publish(AVAILABILITY_TOPIC, 'online', retain=True)
    print(f"Connected to MQTT at {broker}:{port}")
    return client


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    print("System Monitor MQTT Bridge")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Update interval: {UPDATE_INTERVAL}s")
    print("Press Ctrl+C to exit\n")

    client = connect_mqtt(MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TLS, MQTT_CA_CERT)
    if not client:
        return

    try:
        while True:
            sys_state = collect_system_state()
            client.publish(STATE_TOPIC, json.dumps(sys_state))
            print(f"System: {json.dumps(sys_state)}")
            time.sleep(UPDATE_INTERVAL)

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.publish(AVAILABILITY_TOPIC, 'offline', retain=True)
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        print("Connections closed.")


if __name__ == '__main__':
    main()
