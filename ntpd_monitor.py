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
# Claude Generated: version 1 - NTP monitor MQTT bridge with Home Assistant auto-discovery
#                                Reports NTPd sync, stratum, offset, refid, jitter, clock time
# Claude Generated: version 2 - Add frequency, clk_jitter, clk_wander sensors
# Claude Generated: version 3 - Add version, leap indicator, precision sensors
# Claude Generated: version 4 - Security: env var credentials, TLS support, exception logging
# Claude Generated: version 5 - Replace timedatectl with ntpq leap field to avoid dbus activation spam
# Claude Generated: version 6 - Always include all keys in MQTT payload to prevent HA template warnings
# Claude Generated: version 7 - Security C-1: add MQTT_CA_CERT env var for explicit CA cert verification
# Claude Generated: version 8 - Security C-2: warn at startup when TLS is disabled
# Claude Generated: version 9 - Security S-2: append hostname to MQTT client_id to prevent collisions
# Claude Generated: version 10 - Security S-4: validate port env vars (type and 1-65535 range)
# Claude Generated: version 11 - Security I-3: cap ntpq string fields to prevent oversized HA state values
# Claude Generated: version 12 - Rename ntp_mqtt.py to ntpd_monitor.py
# Claude Generated: version 13 - Add NTP_PUBLISH_INTERVAL env var (default 30s)
# Claude Generated: version 14 - Pass MQTT config explicitly to connect_mqtt() instead of capturing globals
# Claude Generated: version 15 - Fix clock field extraction: use regex on raw output to handle commas in date string
# Claude Generated: version 16 - Add _parse_interval() for validated interval env var parsing
# Claude Generated: version 17 - Security: preflight MQTT_CA_CERT path validation; empty string treated as unset

"""
NTP Monitor MQTT Bridge - Publishes NTPd status and detail to MQTT
with Home Assistant auto-discovery.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

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

UPDATE_INTERVAL  = _parse_interval('NTP_PUBLISH_INTERVAL', 30)  # seconds between publishes
DISCOVERY_PREFIX = 'homeassistant'

# ---------------------------------------------------------------------------
# Device: NTP Monitor
# ---------------------------------------------------------------------------
STATE_TOPIC        = 'ntp_monitor/state'
AVAILABILITY_TOPIC = 'ntp_monitor/availability'

DEVICE_INFO = {
    'identifiers': ['ntp_monitor'],
    'name': 'NTP Monitor',
    'model': 'NTP Bridge',
    'manufacturer': 'Tache',
}

SENSORS = [
    {
        'id': 'ntp_synced',
        'name': 'NTPd Synced',
        'value_template': '{{ value_json.ntp_synced }}',
        'icon': 'mdi:clock-check',
    },
    {
        'id': 'ntp_stratum',
        'name': 'NTPd Stratum',
        'value_template': '{{ value_json.ntp_stratum }}',
        'state_class': 'measurement',
        'icon': 'mdi:layers-triple',
    },
    {
        'id': 'ntp_offset',
        'name': 'NTPd Offset',
        'value_template': '{{ value_json.ntp_offset }}',
        'unit_of_measurement': 'ms',
        'state_class': 'measurement',
        'icon': 'mdi:clock-fast',
    },
    {
        'id': 'ntp_refid',
        'name': 'NTPd Reference',
        'value_template': '{{ value_json.ntp_refid }}',
        'icon': 'mdi:crosshairs-gps',
    },
    {
        'id': 'ntp_jitter',
        'name': 'NTPd Jitter',
        'value_template': '{{ value_json.ntp_jitter }}',
        'unit_of_measurement': 'ms',
        'state_class': 'measurement',
        'icon': 'mdi:chart-bell-curve',
    },
    {
        'id': 'ntp_time',
        'name': 'NTPd Time',
        'value_template': '{{ value_json.ntp_time }}',
        'icon': 'mdi:clock-outline',
    },
    {
        'id': 'ntp_frequency',
        'name': 'NTPd Frequency Offset',
        'value_template': '{{ value_json.ntp_frequency }}',
        'unit_of_measurement': 'PPM',
        'state_class': 'measurement',
        'icon': 'mdi:sine-wave',
    },
    {
        'id': 'ntp_clk_jitter',
        'name': 'NTPd Clock Jitter',
        'value_template': '{{ value_json.ntp_clk_jitter }}',
        'unit_of_measurement': 'ms',
        'state_class': 'measurement',
        'icon': 'mdi:chart-bell-curve-cumulative',
    },
    {
        'id': 'ntp_clk_wander',
        'name': 'NTPd Clock Wander',
        'value_template': '{{ value_json.ntp_clk_wander }}',
        'unit_of_measurement': 'PPM',
        'state_class': 'measurement',
        'icon': 'mdi:wave',
    },
    {
        'id': 'ntp_version',
        'name': 'NTPd Version',
        'value_template': '{{ value_json.ntp_version }}',
        'icon': 'mdi:information-outline',
    },
    {
        'id': 'ntp_leap',
        'name': 'NTPd Leap Indicator',
        'value_template': '{{ value_json.ntp_leap }}',
        'icon': 'mdi:alert-circle-outline',
    },
    {
        'id': 'ntp_precision',
        'name': 'NTPd Precision',
        'value_template': '{{ value_json.ntp_precision }}',
        'unit_of_measurement': 'log2 s',
        'state_class': 'measurement',
        'icon': 'mdi:target',
    },
]

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def parse_ntpq_rv(output):
    """Parse ntpq -c rv key=value output into a dict."""
    result = {}
    for item in ' '.join(output.strip().splitlines()).split(','):
        item = item.strip()
        if '=' in item:
            key, _, value = item.partition('=')
            result[key.strip()] = value.strip()
    return result


def collect_ntp_state():
    """Gather NTPd detail via ntpq -c rv.  All keys are always present to avoid HA template warnings."""
    state = {
        'ntp_synced': 'Unknown',
        'ntp_stratum': None,
        'ntp_offset': None,
        'ntp_refid': None,
        'ntp_jitter': None,
        'ntp_time': None,
        'ntp_frequency': None,
        'ntp_clk_jitter': None,
        'ntp_clk_wander': None,
        'ntp_version': None,
        'ntp_leap': None,
        'ntp_precision': None,
    }
    try:
        result = subprocess.run(
            ['ntpq', '-c', 'rv'],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            fields = parse_ntpq_rv(result.stdout)

            # Derive sync status from leap field: 3 means unsynchronized
            leap = fields.get('leap')
            if leap is not None:
                state['ntp_synced'] = 'No' if leap == '3' else 'Yes'
                leap_labels = {'0': 'None', '1': 'Add Second', '2': 'Delete Second', '3': 'Unsynchronized'}
                state['ntp_leap'] = leap_labels.get(leap, leap)
            else:
                state['ntp_synced'] = 'Unknown'

            stratum = fields.get('stratum')
            offset  = fields.get('offset')
            refid   = fields.get('refid')
            jitter  = fields.get('sys_jitter')

            if stratum is not None:
                state['ntp_stratum'] = int(stratum)
            if offset is not None:
                state['ntp_offset'] = round(float(offset), 4)
            if refid is not None:
                state['ntp_refid'] = refid.strip('"')[:64]
            if jitter is not None:
                state['ntp_jitter'] = round(float(jitter), 4)

            frequency = fields.get('frequency')
            clk_jitter = fields.get('clk_jitter')
            clk_wander = fields.get('clk_wander')

            if frequency is not None:
                state['ntp_frequency'] = round(float(frequency), 4)
            if clk_jitter is not None:
                state['ntp_clk_jitter'] = round(float(clk_jitter), 4)
            if clk_wander is not None:
                state['ntp_clk_wander'] = round(float(clk_wander), 4)

            version = fields.get('version')
            precision = fields.get('precision')

            if version is not None:
                state['ntp_version'] = version.strip('"')[:128]
            if precision is not None:
                state['ntp_precision'] = int(precision)

            # Extract clock field using regex on raw output: the value contains commas in
            # the date string (e.g. "Thu, Mar 21 2026  3:14:05.123") which would be split
            # by parse_ntpq_rv's comma-delimiter logic.
            # Group 1: hex timestamp. Group 2: optional human-readable date portion.
            clock_match = re.search(
                r'\bclock=(\S+)(?:\s+(.+?))?(?=,\s*[a-z]\w*=|\s*$)',
                result.stdout.replace('\n', ' ')
            )
            if clock_match:
                human = clock_match.group(2)
                state['ntp_time'] = (human.strip() if human else clock_match.group(1))[:64]
    except Exception as e:
        print(f"Error reading ntpq: {e}")
    return state


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

def publish_discovery(client):
    """Publish MQTT Discovery configs for NTP sensors."""
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
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'ntp_monitor_bridge_{socket.gethostname()}')
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
    print("NTP Monitor MQTT Bridge")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Update interval: {UPDATE_INTERVAL}s")
    print("Press Ctrl+C to exit\n")

    client = connect_mqtt(MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TLS, MQTT_CA_CERT)
    if not client:
        return

    try:
        while True:
            ntp_state = collect_ntp_state()
            client.publish(STATE_TOPIC, json.dumps(ntp_state))
            print(f"NTP: {json.dumps(ntp_state)}")
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
