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
# Claude Generated: version 1 - GPSD to MQTT bridge with Home Assistant auto-discovery
# Claude Generated: version 2 - Add satellite array to state payload; fix GPS Time device_class
# Claude Generated: version 3 - Add ept, sep, all DOPs (vdop/pdop/tdop/gdop/xdop/ydop), nSat, uSat
# Claude Generated: version 4 - Add VERSION, PPS, TOFF, ERROR message handling
# Claude Generated: version 5 - Security: env var credentials, TLS support, buffer cap,
#                                input validation, socket timeout, exception logging
# Claude Generated: version 6 - Always include all keys in MQTT payload to prevent HA template warnings
# Claude Generated: version 7 - Fix NameError in _publish_state (payload → self.state)
# Claude Generated: version 8 - Handle GPSD 3.27 split SKY messages (DOP-only vs full with satellites)
# Claude Generated: version 9 - Enable TOFF via timing:true in WATCH; add eph/geoidSep sensors;
#                                default last_error to "None" string to avoid HA "Unknown"
# Claude Generated: version 10 - Add gnssid/svid to satellite payload (available with GPSD 3.27.5)
# Claude Generated: version 11 - Replace flat SENSORS list with MESSAGE_GROUPS dict (sky/status/position)
# Claude Generated: version 12 - Refactor GPSDMQTTBridge to use group-based state (self.groups)
# Claude Generated: version 13 - Implement _maybe_publish; refactor _connect_mqtt for per-group discovery; wire run() loop
# Claude Generated: version 14 - Fix last_error default: 'None' string causes HA to show Unknown; use 'ok' instead
# Claude Generated: version 15 - Correct WATCH command: pps:true is the single flag that enables both TOFF and PPS messages
# Claude Generated: version 16 - Realign MQTT groups to GPSD message classes: VERSION/SKY/TPV/TOFF/PPS;
#                                drop status/position topics; move DOPs to sky; clear deprecated sensors on startup
# Claude Generated: version 17 - Security C-1: add MQTT_CA_CERT env var for explicit CA cert verification
# Claude Generated: version 18 - Security C-2: warn at startup when TLS is disabled
# Claude Generated: version 19 - Security S-2: append hostname to MQTT client_id to prevent collisions
# Claude Generated: version 20 - Security S-4: validate port env vars (type and 1-65535 range)
# Claude Generated: version 21 - Rename gps_mqtt.py to gpsd_monitor.py
# Claude Generated: version 22 - Remove gps_pps_precision from DEPRECATED_SENSOR_IDS (still an active sensor)
# Claude Generated: version 23 - Add _parse_interval() for validated interval env var parsing; clear stale position fields on no-fix
# Claude Generated: version 24 - Security: preflight MQTT_CA_CERT path validation; empty string treated as unset; cap release/shm strings
# Claude Generated: version 25 - Log previously silent excepts: TPV time parse errors and malformed GPSD JSON

"""
GPSD to MQTT Bridge - Publishes GPS data to MQTT with Home Assistant auto-discovery.
Groups align with GPSD message classes: VERSION, SKY, TPV, TOFF, PPS.
"""

import copy
import json
import os
import socket
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
GPSD_HOST = os.environ.get('GPSD_HOST', 'localhost')
GPSD_PORT = _parse_port('GPSD_PORT', 2947)

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

# ---------------------------------------------------------------------------
# Message group configuration — toggles and publish intervals from env vars
# ---------------------------------------------------------------------------
GPS_PUBLISH_VERSION          = os.environ.get('GPS_PUBLISH_VERSION', 'true').lower() != 'false'
GPS_PUBLISH_VERSION_INTERVAL = _parse_interval('GPS_PUBLISH_VERSION_INTERVAL', 0)

GPS_PUBLISH_SKY          = os.environ.get('GPS_PUBLISH_SKY', 'true').lower() != 'false'
GPS_PUBLISH_SKY_INTERVAL = _parse_interval('GPS_PUBLISH_SKY_INTERVAL', 0)

GPS_PUBLISH_TPV          = os.environ.get('GPS_PUBLISH_TPV', 'true').lower() != 'false'
GPS_PUBLISH_TPV_INTERVAL = _parse_interval('GPS_PUBLISH_TPV_INTERVAL', 0)

GPS_PUBLISH_TOFF          = os.environ.get('GPS_PUBLISH_TOFF', 'true').lower() != 'false'
GPS_PUBLISH_TOFF_INTERVAL = _parse_interval('GPS_PUBLISH_TOFF_INTERVAL', 0)

GPS_PUBLISH_PPS          = os.environ.get('GPS_PUBLISH_PPS', 'true').lower() != 'false'
GPS_PUBLISH_PPS_INTERVAL = _parse_interval('GPS_PUBLISH_PPS_INTERVAL', 0)

AVAILABILITY_TOPIC = 'gps_monitor/availability'
DISCOVERY_PREFIX   = 'homeassistant'

# ---------------------------------------------------------------------------
# Deprecated sensor IDs — discovery configs cleared on startup
# These were removed or renamed in the version 16 group realignment
# ---------------------------------------------------------------------------
DEPRECATED_SENSOR_IDS = [
    # Removed: MTK-3301 does not emit velocity components
    'gps_vel_e', 'gps_vel_n', 'gps_vel_d',
    # Removed: old status/position topics replaced by tpv
    'gps_gpsd_version', 'gps_gpsd_proto',
    'gps_pps_offset',
    'gps_toff',
]

# ---------------------------------------------------------------------------
# Home Assistant MQTT Discovery sensor definitions
# ---------------------------------------------------------------------------
DEVICE_INFO = {
    'identifiers': ['gps_monitor'],
    'name': 'GPS Monitor',
    'model': 'GPS with PPS Bridge',
    'manufacturer': 'Tache',
}

MESSAGE_GROUPS = {
    'version': {
        'topic': 'gps_monitor/version',
        'enabled': GPS_PUBLISH_VERSION,
        'interval': GPS_PUBLISH_VERSION_INTERVAL,
        'last_published': 0.0,
        'sensors': [
            {
                'id': 'gpsd_version',
                'name': 'GPSD Version',
                'value_template': '{{ value_json.release }}',
                'icon': 'mdi:information-outline',
            },
            {
                'id': 'gpsd_proto',
                'name': 'GPSD Protocol',
                'value_template': '{{ value_json.proto }}',
                'icon': 'mdi:protocol',
            },
        ],
        'state': {
            'release': None,
            'proto': None,
        },
    },
    'sky': {
        'topic': 'gps_monitor/sky',
        'enabled': GPS_PUBLISH_SKY,
        'interval': GPS_PUBLISH_SKY_INTERVAL,
        'last_published': 0.0,
        'sensors': [
            {
                'id': 'gps_satellites_used',
                'name': 'GPS Satellites Used',
                'value_template': '{{ value_json.sat_used }}',
                'unit_of_measurement': 'satellites',
                'state_class': 'measurement',
                'icon': 'mdi:satellite-variant',
            },
            {
                'id': 'gps_satellites_visible',
                'name': 'GPS Satellites Visible',
                'value_template': '{{ value_json.sat_visible }}',
                'unit_of_measurement': 'satellites',
                'state_class': 'measurement',
                'icon': 'mdi:satellite-variant',
            },
            {
                'id': 'gps_nsat',
                'name': 'GPS nSat',
                'value_template': '{{ value_json.nsat }}',
                'unit_of_measurement': 'satellites',
                'state_class': 'measurement',
                'icon': 'mdi:satellite-variant',
            },
            {
                'id': 'gps_usat',
                'name': 'GPS uSat',
                'value_template': '{{ value_json.usat }}',
                'unit_of_measurement': 'satellites',
                'state_class': 'measurement',
                'icon': 'mdi:satellite-variant',
            },
            {
                'id': 'gps_satellites_detail',
                'name': 'GPS Satellites Detail',
                'value_template': '{{ value_json.sat_used }}',
                'json_attributes_topic': 'gps_monitor/sky',
                'unit_of_measurement': 'used',
                'icon': 'mdi:satellite-variant',
            },
            {
                'id': 'gps_hdop',
                'name': 'GPS HDOP',
                'value_template': '{{ value_json.hdop }}',
                'unit_of_measurement': 'HDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_vdop',
                'name': 'GPS VDOP',
                'value_template': '{{ value_json.vdop }}',
                'unit_of_measurement': 'VDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_pdop',
                'name': 'GPS PDOP',
                'value_template': '{{ value_json.pdop }}',
                'unit_of_measurement': 'PDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_tdop',
                'name': 'GPS TDOP',
                'value_template': '{{ value_json.tdop }}',
                'unit_of_measurement': 'TDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_gdop',
                'name': 'GPS GDOP',
                'value_template': '{{ value_json.gdop }}',
                'unit_of_measurement': 'GDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_xdop',
                'name': 'GPS XDOP',
                'value_template': '{{ value_json.xdop }}',
                'unit_of_measurement': 'XDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
            {
                'id': 'gps_ydop',
                'name': 'GPS YDOP',
                'value_template': '{{ value_json.ydop }}',
                'unit_of_measurement': 'YDOP',
                'state_class': 'measurement',
                'icon': 'mdi:chart-bell-curve',
            },
        ],
        'state': {
            'sat_used': 0,
            'sat_visible': 0,
            'nsat': None,
            'usat': None,
            'satellites': [],
            'hdop': None,
            'vdop': None,
            'pdop': None,
            'tdop': None,
            'gdop': None,
            'xdop': None,
            'ydop': None,
        },
    },
    'tpv': {
        'topic': 'gps_monitor/tpv',
        'enabled': GPS_PUBLISH_TPV,
        'interval': GPS_PUBLISH_TPV_INTERVAL,
        'last_published': 0.0,
        'sensors': [
            {
                'id': 'gps_fix',
                'name': 'GPS Fix',
                'value_template': '{{ value_json.fix }}',
                'icon': 'mdi:crosshairs-gps',
            },
            {
                'id': 'gps_time',
                'name': 'GPS Time',
                'value_template': '{{ value_json.time }}',
                'icon': 'mdi:clock-outline',
            },
            {
                'id': 'gps_lat',
                'name': 'GPS Latitude',
                'value_template': '{{ value_json.lat }}',
                'unit_of_measurement': '°',
                'state_class': 'measurement',
                'icon': 'mdi:latitude',
            },
            {
                'id': 'gps_lon',
                'name': 'GPS Longitude',
                'value_template': '{{ value_json.lon }}',
                'unit_of_measurement': '°',
                'state_class': 'measurement',
                'icon': 'mdi:longitude',
            },
            {
                'id': 'gps_alt',
                'name': 'GPS Altitude (MSL)',
                'value_template': '{{ value_json.alt }}',
                'unit_of_measurement': 'm',
                'state_class': 'measurement',
                'icon': 'mdi:arrow-expand-vertical',
            },
            {
                'id': 'gps_alt_hae',
                'name': 'GPS Altitude (HAE)',
                'value_template': '{{ value_json.alt_hae }}',
                'unit_of_measurement': 'm',
                'state_class': 'measurement',
                'icon': 'mdi:arrow-expand-vertical',
            },
            {
                'id': 'gps_speed',
                'name': 'GPS Speed',
                'value_template': '{{ value_json.speed }}',
                'unit_of_measurement': 'm/s',
                'state_class': 'measurement',
                'icon': 'mdi:speedometer',
            },
            {
                'id': 'gps_climb',
                'name': 'GPS Climb Rate',
                'value_template': '{{ value_json.climb }}',
                'unit_of_measurement': 'm/s',
                'state_class': 'measurement',
                'icon': 'mdi:elevation-rise',
            },
            {
                'id': 'gps_track',
                'name': 'GPS Track',
                'value_template': '{{ value_json.track }}',
                'unit_of_measurement': '°',
                'state_class': 'measurement',
                'icon': 'mdi:compass-outline',
            },
            {
                'id': 'gps_magtrack',
                'name': 'GPS Magnetic Track',
                'value_template': '{{ value_json.magtrack }}',
                'unit_of_measurement': '°',
                'state_class': 'measurement',
                'icon': 'mdi:compass',
            },
            {
                'id': 'gps_ept',
                'name': 'GPS Time Error',
                'value_template': '{{ value_json.ept }}',
                'unit_of_measurement': 's',
                'state_class': 'measurement',
                'icon': 'mdi:clock-alert-outline',
            },
            {
                'id': 'gps_sep',
                'name': 'GPS Spherical Error',
                'value_template': '{{ value_json.sep }}',
                'unit_of_measurement': 'm',
                'state_class': 'measurement',
                'icon': 'mdi:crosshairs-question',
            },
            {
                'id': 'gps_eph',
                'name': 'GPS Horizontal Error',
                'value_template': '{{ value_json.eph }}',
                'unit_of_measurement': 'm',
                'state_class': 'measurement',
                'icon': 'mdi:arrow-left-right',
            },
            {
                'id': 'gps_geoid_sep',
                'name': 'GPS Geoid Separation',
                'value_template': '{{ value_json.geoid_sep }}',
                'unit_of_measurement': 'm',
                'state_class': 'measurement',
                'icon': 'mdi:earth',
            },
            {
                'id': 'gps_last_error',
                'name': 'GPSD Last Error',
                'value_template': '{{ value_json.last_error }}',
                'icon': 'mdi:alert-outline',
            },
        ],
        'state': {
            'fix': 'No Fix',
            'time': None,
            'lat': None,
            'lon': None,
            'alt': None,
            'alt_hae': None,
            'speed': None,
            'climb': None,
            'track': None,
            'magtrack': None,
            'ept': None,
            'sep': None,
            'eph': None,
            'geoid_sep': None,
            'last_error': 'ok',
        },
    },
    'toff': {
        'topic': 'gps_monitor/toff',
        'enabled': GPS_PUBLISH_TOFF,
        'interval': GPS_PUBLISH_TOFF_INTERVAL,
        'last_published': 0.0,
        'sensors': [
            {
                'id': 'gps_toff_real_sec',
                'name': 'TOFF Real Seconds',
                'value_template': '{{ value_json.real_sec }}',
                'icon': 'mdi:timer-outline',
            },
            {
                'id': 'gps_toff_real_nsec',
                'name': 'TOFF Real Nanoseconds',
                'value_template': '{{ value_json.real_nsec }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:timer-outline',
            },
            {
                'id': 'gps_toff_clock_sec',
                'name': 'TOFF Clock Seconds',
                'value_template': '{{ value_json.clock_sec }}',
                'icon': 'mdi:clock-outline',
            },
            {
                'id': 'gps_toff_clock_nsec',
                'name': 'TOFF Clock Nanoseconds',
                'value_template': '{{ value_json.clock_nsec }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:clock-outline',
            },
            {
                'id': 'gps_toff_offset_ns',
                'name': 'TOFF Offset',
                'value_template': '{{ value_json.offset_ns }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:timer-sand',
            },
            {
                'id': 'gps_toff_precision',
                'name': 'TOFF Precision',
                'value_template': '{{ value_json.precision }}',
                'icon': 'mdi:target',
            },
            {
                'id': 'gps_toff_shm',
                'name': 'TOFF SHM',
                'value_template': '{{ value_json.shm }}',
                'icon': 'mdi:memory',
            },
        ],
        'state': {
            'real_sec': None,
            'real_nsec': None,
            'clock_sec': None,
            'clock_nsec': None,
            'offset_ns': None,
            'precision': None,
            'shm': None,
        },
    },
    'pps': {
        'topic': 'gps_monitor/pps',
        'enabled': GPS_PUBLISH_PPS,
        'interval': GPS_PUBLISH_PPS_INTERVAL,
        'last_published': 0.0,
        'sensors': [
            {
                'id': 'gps_pps_real_sec',
                'name': 'PPS Real Seconds',
                'value_template': '{{ value_json.real_sec }}',
                'icon': 'mdi:pulse',
            },
            {
                'id': 'gps_pps_real_nsec',
                'name': 'PPS Real Nanoseconds',
                'value_template': '{{ value_json.real_nsec }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:pulse',
            },
            {
                'id': 'gps_pps_clock_sec',
                'name': 'PPS Clock Seconds',
                'value_template': '{{ value_json.clock_sec }}',
                'icon': 'mdi:clock-outline',
            },
            {
                'id': 'gps_pps_clock_nsec',
                'name': 'PPS Clock Nanoseconds',
                'value_template': '{{ value_json.clock_nsec }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:clock-outline',
            },
            {
                'id': 'gps_pps_offset_ns',
                'name': 'PPS Offset',
                'value_template': '{{ value_json.offset_ns }}',
                'unit_of_measurement': 'ns',
                'state_class': 'measurement',
                'icon': 'mdi:target',
            },
            {
                'id': 'gps_pps_precision',
                'name': 'PPS Precision',
                'value_template': '{{ value_json.precision }}',
                'icon': 'mdi:target',
            },
            {
                'id': 'gps_pps_shm',
                'name': 'PPS SHM',
                'value_template': '{{ value_json.shm }}',
                'icon': 'mdi:memory',
            },
        ],
        'state': {
            'real_sec': None,
            'real_nsec': None,
            'clock_sec': None,
            'clock_nsec': None,
            'offset_ns': None,
            'precision': None,
            'shm': None,
        },
    },
}

FIX_MODES = {0: 'No Fix', 1: 'No Fix', 2: '2D Fix', 3: '3D Fix'}

# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class GPSDMQTTBridge:

    def __init__(self):
        self.mqtt_client = None
        self.gpsd_sock = None
        # Deep copy group definitions so each bridge instance has independent state
        self.groups = copy.deepcopy(MESSAGE_GROUPS)
        for group in self.groups.values():
            group['last_published'] = 0.0
        # Tracks first-seen timestamp per PRN for the seen_secs field
        self.satellite_first_seen = {}

    def _connect_mqtt(self):
        """Connect to broker, clear deprecated sensors, register LWT, and publish discovery configs."""
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'gps_monitor_bridge_{socket.gethostname()}')
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_TLS:
            client.tls_set(ca_certs=MQTT_CA_CERT)   # None = verify against system trust store
        # Last Will — broker publishes this automatically if we disconnect ungracefully
        client.will_set(AVAILABILITY_TOPIC, 'offline', retain=True)

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            return False

        # Clear discovery configs for sensors removed in this version
        for sensor_id in DEPRECATED_SENSOR_IDS:
            config_topic = f"{DISCOVERY_PREFIX}/sensor/{sensor_id}/config"
            client.publish(config_topic, '', retain=True)
        print(f"  Cleared {len(DEPRECATED_SENSOR_IDS)} deprecated sensor configs")

        for group_name, group in self.groups.items():
            for sensor in group['sensors']:
                config_topic = f"{DISCOVERY_PREFIX}/sensor/{sensor['id']}/config"

                if group['enabled']:
                    config_payload = {
                        'name': sensor['name'],
                        'unique_id': sensor['id'],
                        'state_topic': group['topic'],
                        'availability_topic': AVAILABILITY_TOPIC,
                        'value_template': sensor['value_template'],
                        'device': DEVICE_INFO,
                    }
                    for key in ('device_class', 'unit_of_measurement', 'state_class',
                                'icon', 'json_attributes_topic'):
                        if key in sensor:
                            config_payload[key] = sensor[key]
                    client.publish(config_topic, json.dumps(config_payload), retain=True)
                else:
                    # Clear stale discovery configs for disabled groups
                    client.publish(config_topic, '', retain=True)

            state_label = "enabled" if group['enabled'] else "disabled"
            interval_label = f"interval={group['interval']}s" if group['enabled'] else ""
            print(f"  Group '{group_name}': {state_label} {interval_label}".rstrip())

        client.publish(AVAILABILITY_TOPIC, 'online', retain=True)
        print(f"Connected to MQTT at {MQTT_BROKER}:{MQTT_PORT}")
        self.mqtt_client = client
        return True

    def _maybe_publish(self, group_name):
        """Publish group state if enabled and publish interval has elapsed."""
        group = self.groups[group_name]
        if not group['enabled']:
            return

        now = time.time()
        # interval == 0 means publish on every message (no rate limiting)
        if group['interval'] > 0 and (now - group['last_published']) < group['interval']:
            return

        payload = json.dumps(group['state'])
        self.mqtt_client.publish(group['topic'], payload)
        group['last_published'] = now
        print(f"  >> Published {group_name}: {payload}")

    def _connect_gpsd(self):
        """Connect to GPSD and start the JSON watch stream."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(60)
            sock.connect((GPSD_HOST, GPSD_PORT))
            # pps:true enables both TOFF and PPS JSON messages per the GPSD spec
            sock.send(b'?WATCH={"enable":true,"json":true,"pps":true};')
            print(f"Connected to GPSD at {GPSD_HOST}:{GPSD_PORT}")
            self.gpsd_sock = sock
            return True
        except Exception as e:
            print(f"GPSD connection failed: {e}")
            return False

    def _handle_tpv(self, obj):
        """Update TPV group from TPV message."""
        tpv = self.groups['tpv']['state']

        mode = obj.get('mode', 0)
        tpv['fix'] = FIX_MODES.get(mode, 'No Fix')

        # No fix — clear stale position fields so HA shows 'unavailable' rather than old data
        if mode <= 1:
            for key in ('time', 'lat', 'lon', 'alt', 'alt_hae', 'speed', 'climb',
                        'track', 'magtrack', 'ept', 'sep', 'eph', 'geoid_sep'):
                tpv[key] = None
            return

        if 'time' in obj:
            try:
                # Strip sub-seconds; keep Z suffix for valid ISO 8601 timestamp
                time_str = obj['time']
                if '.' in time_str:
                    time_str = time_str.split('.')[0] + 'Z'
                tpv['time'] = time_str
            except (ValueError, AttributeError) as e:
                print(f"  WARN  Could not parse TPV time field: {e}")

        # Direct float field mapping: (gpsd_key, state_key, decimal_places)
        for gpsd_key, state_key, decimals in (
            ('lat',      'lat',      6),
            ('lon',      'lon',      6),
            ('alt',      'alt',      2),
            ('speed',    'speed',    6),
            ('climb',    'climb',    6),
            ('track',    'track',    6),
            ('magtrack', 'magtrack', 6),
            ('ept',      'ept',      6),
            ('sep',      'sep',      2),
            ('eph',      'eph',      2),
        ):
            if gpsd_key in obj and isinstance(obj[gpsd_key], (int, float)):
                tpv[state_key] = round(obj[gpsd_key], decimals)

        # camelCase to snake_case mapping
        for gpsd_key, state_key, decimals in (
            ('altHAE',   'alt_hae',   2),
            ('geoidSep', 'geoid_sep', 2),
        ):
            if gpsd_key in obj and isinstance(obj[gpsd_key], (int, float)):
                tpv[state_key] = round(obj[gpsd_key], decimals)

    def _handle_sky(self, obj):
        """Update SKY group from SKY message.

        GPSD 3.27+ can send SKY in two forms:
        - DOP-only (no satellites array) — update DOPs only
        - Full (with satellites array) — update DOPs and satellite data
        """
        sky = self.groups['sky']['state']

        # DOPs
        for dop_key in ('hdop', 'vdop', 'pdop', 'tdop', 'gdop', 'xdop', 'ydop'):
            if dop_key in obj and isinstance(obj[dop_key], (int, float)):
                sky[dop_key] = round(obj[dop_key], 2)

        # Satellite counts
        if 'nSat' in obj:
            sky['nsat'] = obj['nSat']
        if 'uSat' in obj:
            sky['usat'] = obj['uSat']

        # Full satellite list — only present in non-DOP-only SKY messages
        if 'satellites' in obj:
            satellites = obj['satellites']
            now = time.time()

            sky['sat_visible'] = len(satellites)
            sky['sat_used'] = sum(1 for s in satellites if s.get('used', False))

            # Build satellite list sorted: used first, then by descending SNR
            current_prns = set()
            satellite_list = []
            for sat in sorted(satellites, key=lambda x: (not x.get('used', False), -x.get('ss', 0))):
                prn = sat.get('PRN')
                if prn is None:
                    continue
                current_prns.add(prn)
                if prn not in self.satellite_first_seen:
                    self.satellite_first_seen[prn] = now
                sat_entry = {
                    'prn':  prn,
                    'el':   sat.get('el', 0),
                    'az':   sat.get('az', 0),
                    'ss':   sat.get('ss', 0),
                    'used': sat.get('used', False),
                    'seen': int(now - self.satellite_first_seen[prn]),
                }
                if 'gnssid' in sat:
                    sat_entry['gnssid'] = sat['gnssid']
                if 'svid' in sat:
                    sat_entry['svid'] = sat['svid']
                satellite_list.append(sat_entry)
            sky['satellites'] = satellite_list

            # Prune PRNs no longer visible to prevent unbounded dict growth
            stale_prns = set(self.satellite_first_seen.keys()) - current_prns
            for prn in stale_prns:
                del self.satellite_first_seen[prn]

    def _handle_version(self, obj):
        """Update VERSION group from VERSION message."""
        version = self.groups['version']['state']
        if 'release' in obj:
            version['release'] = obj['release'][:64]
        proto_major = obj.get('proto_major')
        proto_minor = obj.get('proto_minor')
        if proto_major is not None and proto_minor is not None:
            version['proto'] = f"{proto_major}.{proto_minor}"

    def _handle_pps(self, obj):
        """Update PPS group from PPS message."""
        pps = self.groups['pps']['state']
        real_sec   = obj.get('real_sec', 0)
        real_nsec  = obj.get('real_nsec', 0)
        clock_sec  = obj.get('clock_sec', 0)
        clock_nsec = obj.get('clock_nsec', 0)
        pps['real_sec']   = real_sec
        pps['real_nsec']  = real_nsec
        pps['clock_sec']  = clock_sec
        pps['clock_nsec'] = clock_nsec
        pps['offset_ns']  = (real_sec - clock_sec) * 1_000_000_000 + (real_nsec - clock_nsec)
        if 'precision' in obj:
            pps['precision'] = obj['precision']
        if 'shm' in obj:
            pps['shm'] = obj['shm'][:64]

    def _handle_toff(self, obj):
        """Update TOFF group from TOFF message."""
        toff = self.groups['toff']['state']
        real_sec   = obj.get('real_sec', 0)
        real_nsec  = obj.get('real_nsec', 0)
        clock_sec  = obj.get('clock_sec', 0)
        clock_nsec = obj.get('clock_nsec', 0)
        toff['real_sec']   = real_sec
        toff['real_nsec']  = real_nsec
        toff['clock_sec']  = clock_sec
        toff['clock_nsec'] = clock_nsec
        toff['offset_ns']  = (real_sec - clock_sec) * 1_000_000_000 + (real_nsec - clock_nsec)
        if 'precision' in obj:
            toff['precision'] = obj['precision']
        if 'shm' in obj:
            toff['shm'] = obj['shm'][:64]

    def _handle_error(self, obj):
        """Cache last GPSD error in TPV group."""
        msg = obj.get('message', 'Unknown')
        self.groups['tpv']['state']['last_error'] = msg[:256]

    def run(self):
        """Main receive loop."""
        if not self._connect_mqtt():
            return
        if not self._connect_gpsd():
            return

        buffer = ''
        max_buffer = 65536
        known_ignored = {'DEVICES', 'WATCH', 'ATT'}

        try:
            while True:
                raw = self.gpsd_sock.recv(4096)
                if not raw:
                    print("GPSD connection closed.")
                    break

                buffer += raw.decode('utf-8', errors='replace')
                if len(buffer) > max_buffer:
                    print(f"  WARN  Buffer exceeded {max_buffer} bytes, truncating")
                    buffer = buffer[-max_buffer:]

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        obj = json.loads(line)
                        msg_class = obj.get('class')

                        if msg_class == 'TPV':
                            print(f"  TPV  fix={obj.get('mode', '?')} time={obj.get('time', 'N/A')}")
                            self._handle_tpv(obj)
                            self._maybe_publish('tpv')
                        elif msg_class == 'SKY':
                            if 'satellites' in obj:
                                sats = obj['satellites']
                                used = sum(1 for s in sats if s.get('used', False))
                                print(f"  SKY  {used}/{len(sats)} sats  hdop={obj.get('hdop', 'N/A')}")
                            else:
                                print(f"  SKY  (DOP-only)  hdop={obj.get('hdop', 'N/A')}")
                            self._handle_sky(obj)
                            self._maybe_publish('sky')
                        elif msg_class == 'VERSION':
                            print(f"  VER  {obj.get('release', '?')} proto={obj.get('proto_major', '?')}.{obj.get('proto_minor', '?')}")
                            self._handle_version(obj)
                            self._maybe_publish('version')
                        elif msg_class == 'PPS':
                            print(f"  PPS  precision={obj.get('precision', 'N/A')} shm={obj.get('shm', 'N/A')}")
                            self._handle_pps(obj)
                            self._maybe_publish('pps')
                        elif msg_class == 'TOFF':
                            real_sec   = obj.get('real_sec', 0)
                            real_nsec  = obj.get('real_nsec', 0)
                            clock_sec  = obj.get('clock_sec', 0)
                            clock_nsec = obj.get('clock_nsec', 0)
                            offset_ns  = (real_sec - clock_sec) * 1_000_000_000 + (real_nsec - clock_nsec)
                            print(f"  TOFF offset={offset_ns}ns shm={obj.get('shm', 'N/A')}")
                            self._handle_toff(obj)
                            self._maybe_publish('toff')
                        elif msg_class == 'ERROR':
                            print(f"  ERR  {obj.get('message', 'Unknown')}")
                            self._handle_error(obj)
                            self._maybe_publish('tpv')
                        elif msg_class not in known_ignored:
                            print(f"  ???  Unhandled class: {msg_class}")

                    except json.JSONDecodeError as e:
                        print(f"  WARN  Malformed JSON from GPSD: {e}")

        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if self.mqtt_client:
                self.mqtt_client.publish(AVAILABILITY_TOPIC, 'offline', retain=True)
                time.sleep(0.5)  # Allow the offline message to flush before disconnect
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            if self.gpsd_sock:
                self.gpsd_sock.close()
            print("Connections closed.")


def main():
    print("GPSD to MQTT Bridge")
    print(f"GPSD: {GPSD_HOST}:{GPSD_PORT}")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print("Press Ctrl+C to exit\n")

    bridge = GPSDMQTTBridge()
    bridge.run()


if __name__ == '__main__':
    main()
