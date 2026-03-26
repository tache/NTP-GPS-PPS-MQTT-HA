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
# Claude Generated: version 1 - Tests for MQTT message group restructuring
# Claude Generated: version 2 - Update import and references after rename to gpsd_monitor.py
# Claude Generated: version 3 - Rewrite tests to match current group structure (version/sky/tpv/toff/pps)
# Claude Generated: version 4 - Add satellite tracking, sort order, TOFF/PPS fields, error truncation, deprecated sensor clearing
# Claude Generated: version 5 - Add mode field to TPV handler tests; add no-fix position clearing tests

"""Tests for gpsd_monitor.py message group architecture."""

import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Provide dummy MQTT credentials so gpsd_monitor.py doesn't sys.exit on import
os.environ.setdefault('MQTT_BROKER', 'localhost')
os.environ.setdefault('MQTT_USERNAME', 'test')
os.environ.setdefault('MQTT_PASSWORD', 'test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import gpsd_monitor


class TestGroupDefinitions(unittest.TestCase):
    """Verify the five message groups are defined correctly."""

    def test_sky_group_exists(self):
        """Sky group must have the correct topic."""
        sky = gpsd_monitor.MESSAGE_GROUPS['sky']
        self.assertEqual(sky['topic'], 'gps_monitor/sky')

    def test_tpv_group_exists(self):
        """TPV group must have the correct topic."""
        tpv = gpsd_monitor.MESSAGE_GROUPS['tpv']
        self.assertEqual(tpv['topic'], 'gps_monitor/tpv')

    def test_version_group_exists(self):
        """VERSION group must have the correct topic."""
        version = gpsd_monitor.MESSAGE_GROUPS['version']
        self.assertEqual(version['topic'], 'gps_monitor/version')

    def test_toff_group_exists(self):
        """TOFF group must have the correct topic."""
        toff = gpsd_monitor.MESSAGE_GROUPS['toff']
        self.assertEqual(toff['topic'], 'gps_monitor/toff')

    def test_pps_group_exists(self):
        """PPS group must have the correct topic."""
        pps = gpsd_monitor.MESSAGE_GROUPS['pps']
        self.assertEqual(pps['topic'], 'gps_monitor/pps')

    def test_sky_sensor_ids(self):
        """Sky group must contain exactly these sensor IDs."""
        sky = gpsd_monitor.MESSAGE_GROUPS['sky']
        ids = {s['id'] for s in sky['sensors']}
        expected = {
            'gps_satellites_used', 'gps_satellites_visible',
            'gps_nsat', 'gps_usat', 'gps_satellites_detail',
            'gps_hdop', 'gps_vdop', 'gps_pdop', 'gps_tdop',
            'gps_gdop', 'gps_xdop', 'gps_ydop',
        }
        self.assertEqual(ids, expected)

    def test_tpv_sensor_ids(self):
        """TPV group must contain exactly these sensor IDs."""
        tpv = gpsd_monitor.MESSAGE_GROUPS['tpv']
        ids = {s['id'] for s in tpv['sensors']}
        expected = {
            'gps_fix', 'gps_time', 'gps_lat', 'gps_lon',
            'gps_alt', 'gps_alt_hae', 'gps_speed', 'gps_climb',
            'gps_track', 'gps_magtrack', 'gps_ept', 'gps_sep',
            'gps_eph', 'gps_geoid_sep', 'gps_last_error',
        }
        self.assertEqual(ids, expected)

    def test_all_sensors_have_value_template(self):
        """Every sensor in every group must have a value_template."""
        for group_name, group in gpsd_monitor.MESSAGE_GROUPS.items():
            for sensor in group['sensors']:
                self.assertIn('value_template', sensor,
                    f"Sensor {sensor['id']} in {group_name} missing value_template")

    def test_satellites_detail_json_attributes_topic(self):
        """Satellites detail sensor must point json_attributes_topic to sky topic."""
        sky = gpsd_monitor.MESSAGE_GROUPS['sky']
        detail = next(s for s in sky['sensors'] if s['id'] == 'gps_satellites_detail')
        self.assertEqual(detail['json_attributes_topic'], 'gps_monitor/sky')


class TestHandlerStateUpdates(unittest.TestCase):
    """Verify GPSD message handlers update the correct group state dicts."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def test_tpv_updates_tpv_fix(self):
        """TPV message should update tpv group fix mode."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3})
        self.assertEqual(self.bridge.groups['tpv']['state']['fix'], '3D Fix')

    def test_tpv_updates_tpv_time(self):
        """TPV message should update tpv group time."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'time': '2026-03-23T12:00:00.000Z'})
        self.assertEqual(self.bridge.groups['tpv']['state']['time'], '2026-03-23T12:00:00Z')

    def test_tpv_updates_tpv_ept(self):
        """TPV message should update tpv group ept."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'ept': 0.005})
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['ept'], 0.005)

    def test_tpv_updates_tpv_geoid_sep(self):
        """TPV geoidSep maps to tpv group geoid_sep."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'geoidSep': -33.45})
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['geoid_sep'], -33.45)

    def test_tpv_updates_tpv_lat_lon(self):
        """TPV message should update tpv group lat/lon."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'lat': 37.7749, 'lon': -122.4194})
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['lat'], 37.7749)
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['lon'], -122.4194)

    def test_tpv_updates_tpv_alt_hae(self):
        """TPV altHAE maps to tpv group alt_hae."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'altHAE': 100.5})
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['alt_hae'], 100.5)

    def test_tpv_updates_tpv_speed_climb_track(self):
        """TPV speed/climb/track/magtrack update tpv group."""
        self.bridge._handle_tpv({
            'class': 'TPV', 'mode': 3, 'speed': 5.2, 'climb': 0.3,
            'track': 180.5, 'magtrack': 178.2,
        })
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['speed'], 5.2)
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['climb'], 0.3)
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['track'], 180.5)
        self.assertAlmostEqual(self.bridge.groups['tpv']['state']['magtrack'], 178.2)

    def test_tpv_does_not_touch_sky_state(self):
        """TPV message must not modify sky group state."""
        sky_before = dict(self.bridge.groups['sky']['state'])
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'lat': 37.0})
        sky_after = dict(self.bridge.groups['sky']['state'])
        self.assertEqual(sky_before, sky_after)

    def test_sky_full_updates_sky_state(self):
        """SKY with satellites should update sky group sat counts and list."""
        sky_msg = {
            'class': 'SKY',
            'hdop': 1.2,
            'satellites': [
                {'PRN': 1, 'el': 45, 'az': 90, 'ss': 30, 'used': True},
                {'PRN': 2, 'el': 20, 'az': 180, 'ss': 15, 'used': False},
            ],
        }
        self.bridge._handle_sky(sky_msg)
        self.assertEqual(self.bridge.groups['sky']['state']['sat_used'], 1)
        self.assertEqual(self.bridge.groups['sky']['state']['sat_visible'], 2)
        self.assertEqual(len(self.bridge.groups['sky']['state']['satellites']), 2)

    def test_sky_full_updates_sky_dops(self):
        """SKY with satellites should update sky group DOPs."""
        sky_msg = {
            'class': 'SKY',
            'hdop': 1.2, 'vdop': 0.9, 'pdop': 1.5,
            'tdop': 0.8, 'gdop': 1.7, 'xdop': 0.6, 'ydop': 0.7,
            'satellites': [{'PRN': 1, 'el': 45, 'az': 90, 'ss': 30, 'used': True}],
        }
        self.bridge._handle_sky(sky_msg)
        self.assertAlmostEqual(self.bridge.groups['sky']['state']['hdop'], 1.2)
        self.assertAlmostEqual(self.bridge.groups['sky']['state']['tdop'], 0.8)

    def test_sky_dop_only_updates_dops_not_sat_counts(self):
        """DOP-only SKY (no satellites) should update DOPs but not sat counts/list."""
        sky_before = dict(self.bridge.groups['sky']['state'])
        sky_msg = {'class': 'SKY', 'hdop': 2.0, 'vdop': 1.5}
        self.bridge._handle_sky(sky_msg)
        self.assertAlmostEqual(self.bridge.groups['sky']['state']['hdop'], 2.0)
        # Satellite data should be unchanged
        self.assertEqual(self.bridge.groups['sky']['state']['sat_used'], sky_before['sat_used'])

    def test_sky_nsat_usat_update_sky_state(self):
        """nSat/uSat from SKY go to sky group state."""
        self.bridge._handle_sky({'class': 'SKY', 'nSat': 12, 'uSat': 8})
        self.assertEqual(self.bridge.groups['sky']['state']['nsat'], 12)
        self.assertEqual(self.bridge.groups['sky']['state']['usat'], 8)

    def test_version_updates_version_group(self):
        """VERSION message should update version group release and proto."""
        self.bridge._handle_version({'class': 'VERSION', 'release': '3.27.5', 'proto_major': 3, 'proto_minor': 15})
        self.assertEqual(self.bridge.groups['version']['state']['release'], '3.27.5')
        self.assertEqual(self.bridge.groups['version']['state']['proto'], '3.15')

    def test_pps_updates_pps_group(self):
        """PPS message should update pps group offset_ns and precision."""
        self.bridge._handle_pps({
            'class': 'PPS',
            'real_sec': 1000, 'real_nsec': 500,
            'clock_sec': 1000, 'clock_nsec': 100,
            'precision': -20,
        })
        self.assertEqual(self.bridge.groups['pps']['state']['offset_ns'], 400)
        self.assertEqual(self.bridge.groups['pps']['state']['precision'], -20)

    def test_toff_updates_toff_group(self):
        """TOFF message should update toff group offset_ns."""
        self.bridge._handle_toff({
            'class': 'TOFF',
            'real_sec': 1000, 'real_nsec': 500,
            'clock_sec': 1000, 'clock_nsec': 100,
        })
        self.assertEqual(self.bridge.groups['toff']['state']['offset_ns'], 400)

    def test_error_updates_tpv_last_error(self):
        """ERROR message should update tpv group last_error."""
        self.bridge._handle_error({'class': 'ERROR', 'message': 'test error'})
        self.assertEqual(self.bridge.groups['tpv']['state']['last_error'], 'test error')


class TestTpvNoFixClearing(unittest.TestCase):
    """Verify _handle_tpv clears stale position fields when there is no fix."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()
        # Pre-populate position fields with non-None values via a 3D fix
        self.bridge._handle_tpv({
            'class': 'TPV', 'mode': 3,
            'lat': 37.7749, 'lon': -122.4194, 'alt': 50.0, 'altHAE': 75.0,
            'speed': 1.0, 'climb': 0.1, 'track': 90.0, 'magtrack': 88.0,
            'ept': 0.005, 'sep': 5.0, 'eph': 3.0, 'geoidSep': -33.0,
            'time': '2026-01-01T00:00:00.000Z',
        })

    def _tpv_state(self):
        return self.bridge.groups['tpv']['state']

    def _assert_position_fields_none(self):
        for key in ('time', 'lat', 'lon', 'alt', 'alt_hae', 'speed', 'climb',
                    'track', 'magtrack', 'ept', 'sep', 'eph', 'geoid_sep'):
            self.assertIsNone(self._tpv_state()[key],
                              f"Expected {key} to be None after no-fix, got {self._tpv_state()[key]}")

    def test_mode_0_clears_position_fields(self):
        """mode=0 (unknown) clears all position fields to None."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 0})
        self._assert_position_fields_none()

    def test_mode_1_clears_position_fields(self):
        """mode=1 (no fix) clears all position fields to None."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 1})
        self._assert_position_fields_none()

    def test_mode_0_sets_fix_to_no_fix(self):
        """mode=0 sets fix string to 'No Fix'."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 0})
        self.assertEqual(self._tpv_state()['fix'], 'No Fix')

    def test_mode_1_sets_fix_to_no_fix(self):
        """mode=1 sets fix string to 'No Fix'."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 1})
        self.assertEqual(self._tpv_state()['fix'], 'No Fix')

    def test_mode_2_does_not_clear_fields(self):
        """mode=2 (2D fix) does not clear position fields."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 2, 'lat': 37.0, 'lon': -122.0})
        self.assertIsNotNone(self._tpv_state()['lat'])
        self.assertIsNotNone(self._tpv_state()['lon'])

    def test_last_error_not_cleared_on_no_fix(self):
        """last_error is not touched by the no-fix path."""
        self.bridge.groups['tpv']['state']['last_error'] = 'prev error'
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 0})
        self.assertEqual(self._tpv_state()['last_error'], 'prev error')

    def test_position_fields_populated_after_fix_restored(self):
        """After losing and regaining fix, position fields are populated again."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 0})
        self._assert_position_fields_none()
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'lat': 37.5, 'lon': -121.0})
        self.assertAlmostEqual(self._tpv_state()['lat'], 37.5)
        self.assertAlmostEqual(self._tpv_state()['lon'], -121.0)


class TestPublishLogic(unittest.TestCase):
    """Verify per-group publish logic with interval throttling."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()
        self.bridge.mqtt_client = MagicMock()

    def test_publish_enabled_group_interval_zero(self):
        """Enabled group with interval=0 should publish on every call."""
        self.bridge.groups['sky']['enabled'] = True
        self.bridge.groups['sky']['interval'] = 0
        self.bridge._maybe_publish('sky')
        self.bridge.mqtt_client.publish.assert_called_once()
        call_args = self.bridge.mqtt_client.publish.call_args
        self.assertEqual(call_args[0][0], 'gps_monitor/sky')

    def test_publish_disabled_group_does_nothing(self):
        """Disabled group should not publish."""
        self.bridge.groups['sky']['enabled'] = False
        self.bridge._maybe_publish('sky')
        self.bridge.mqtt_client.publish.assert_not_called()

    def test_publish_interval_throttling(self):
        """Group with interval > 0 should only publish when interval has elapsed."""
        self.bridge.groups['tpv']['enabled'] = True
        self.bridge.groups['tpv']['interval'] = 60
        self.bridge.groups['tpv']['last_published'] = time.time()

        self.bridge._maybe_publish('tpv')
        self.bridge.mqtt_client.publish.assert_not_called()

    def test_publish_interval_elapsed(self):
        """Group should publish when interval has elapsed."""
        self.bridge.groups['tpv']['enabled'] = True
        self.bridge.groups['tpv']['interval'] = 60
        self.bridge.groups['tpv']['last_published'] = time.time() - 61

        self.bridge._maybe_publish('tpv')
        self.bridge.mqtt_client.publish.assert_called_once()

    def test_publish_updates_last_published(self):
        """Publishing should update last_published timestamp."""
        self.bridge.groups['sky']['enabled'] = True
        self.bridge.groups['sky']['interval'] = 0
        before = time.time()
        self.bridge._maybe_publish('sky')
        after = time.time()
        self.assertGreaterEqual(self.bridge.groups['sky']['last_published'], before)
        self.assertLessEqual(self.bridge.groups['sky']['last_published'], after)

    def test_publish_payload_is_group_state_json(self):
        """Published payload should be JSON of the group's state dict."""
        self.bridge.groups['tpv']['enabled'] = True
        self.bridge.groups['tpv']['interval'] = 0
        self.bridge.groups['tpv']['state']['lat'] = 37.7749
        self.bridge._maybe_publish('tpv')
        call_args = self.bridge.mqtt_client.publish.call_args
        payload = json.loads(call_args[0][1])
        self.assertEqual(payload['lat'], 37.7749)


class TestHandlerPublishIntegration(unittest.TestCase):
    """Integration tests: GPSD message in → correct MQTT publish out."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()
        self.bridge.mqtt_client = MagicMock()
        # All groups enabled, interval 0
        for group in self.bridge.groups.values():
            group['enabled'] = True
            group['interval'] = 0

    def test_tpv_publishes_to_tpv_topic(self):
        """A TPV message should trigger publish to the tpv topic."""
        self.bridge._handle_tpv({'class': 'TPV', 'mode': 3, 'lat': 37.0, 'lon': -122.0})
        self.bridge._maybe_publish('tpv')

        topics = [call[0][0] for call in self.bridge.mqtt_client.publish.call_args_list]
        self.assertIn('gps_monitor/tpv', topics)
        self.assertNotIn('gps_monitor/sky', topics)

    def test_sky_full_publishes_to_sky_topic(self):
        """A full SKY message should trigger publish to the sky topic."""
        sky_msg = {
            'class': 'SKY', 'hdop': 1.0,
            'satellites': [{'PRN': 1, 'el': 45, 'az': 90, 'ss': 30, 'used': True}],
        }
        self.bridge._handle_sky(sky_msg)
        self.bridge._maybe_publish('sky')

        topics = [call[0][0] for call in self.bridge.mqtt_client.publish.call_args_list]
        self.assertIn('gps_monitor/sky', topics)

    def test_sky_dop_only_does_not_dirty_sat_state(self):
        """A DOP-only SKY message must not change sky group sat counts or satellite list."""
        self.bridge.groups['sky']['state']['sat_used'] = 5
        self.bridge.groups['sky']['state']['sat_visible'] = 10
        self.bridge.groups['sky']['state']['satellites'] = [{'prn': 1}]

        self.bridge._handle_sky({'class': 'SKY', 'hdop': 1.5})

        self.assertEqual(self.bridge.groups['sky']['state']['sat_used'], 5)
        self.assertEqual(self.bridge.groups['sky']['state']['sat_visible'], 10)
        self.assertEqual(len(self.bridge.groups['sky']['state']['satellites']), 1)
        self.assertAlmostEqual(self.bridge.groups['sky']['state']['hdop'], 1.5)

    def test_disabled_group_not_published(self):
        """Disabled groups should not publish even when data arrives."""
        self.bridge.groups['tpv']['enabled'] = False
        self.bridge._handle_tpv({'class': 'TPV', 'lat': 37.0})
        self.bridge._maybe_publish('sky')
        self.bridge._maybe_publish('tpv')

        topics = [call[0][0] for call in self.bridge.mqtt_client.publish.call_args_list]
        self.assertIn('gps_monitor/sky', topics)
        self.assertNotIn('gps_monitor/tpv', topics)

    def test_tpv_payload_contains_all_keys(self):
        """TPV payload should always contain all expected keys, even when null."""
        self.bridge._handle_tpv({'class': 'TPV', 'lat': 37.0})
        self.bridge._maybe_publish('tpv')

        payload = json.loads(self.bridge.mqtt_client.publish.call_args_list[-1][0][1])
        expected_keys = {
            'fix', 'time', 'lat', 'lon', 'alt', 'alt_hae',
            'speed', 'climb', 'track', 'magtrack',
            'ept', 'sep', 'eph', 'geoid_sep', 'last_error',
        }
        self.assertEqual(set(payload.keys()), expected_keys)

    def test_sky_payload_contains_all_keys(self):
        """Sky payload should always contain all expected keys."""
        self.bridge._maybe_publish('sky')
        payload = json.loads(self.bridge.mqtt_client.publish.call_args[0][1])
        expected_keys = {
            'sat_used', 'sat_visible', 'nsat', 'usat', 'satellites',
            'hdop', 'vdop', 'pdop', 'tdop', 'gdop', 'xdop', 'ydop',
        }
        self.assertEqual(set(payload.keys()), expected_keys)


class TestDiscoveryConfig(unittest.TestCase):
    """Verify discovery config publishing behavior of _connect_mqtt per group."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def _run_connect_mqtt_with_mock(self):
        """Run _connect_mqtt with the MQTT client mocked out."""
        mock_client = MagicMock()
        mock_client.connect.return_value = None
        mock_client.loop_start.return_value = None

        with patch('gpsd_monitor.mqtt.Client', return_value=mock_client):
            self.bridge._connect_mqtt()

        return mock_client

    def test_enabled_group_publishes_discovery_configs(self):
        """Each sensor in an enabled group gets a non-empty discovery config."""
        self.bridge.groups['sky']['enabled'] = True

        mock_client = self._run_connect_mqtt_with_mock()

        published_topics = [call[0][0] for call in mock_client.publish.call_args_list]
        sky = self.bridge.groups['sky']
        for sensor in sky['sensors']:
            expected_topic = f"homeassistant/sensor/{sensor['id']}/config"
            self.assertIn(expected_topic, published_topics,
                f"Missing discovery config for {sensor['id']}")

    def test_disabled_group_publishes_empty_discovery_configs(self):
        """Each sensor in a disabled group gets an empty retained message to clear HA."""
        self.bridge.groups['tpv']['enabled'] = False

        mock_client = self._run_connect_mqtt_with_mock()

        published = {call[0][0]: call[0][1]
                     for call in mock_client.publish.call_args_list}
        tpv = self.bridge.groups['tpv']
        for sensor in tpv['sensors']:
            config_topic = f"homeassistant/sensor/{sensor['id']}/config"
            self.assertIn(config_topic, published,
                f"Missing empty clear for disabled sensor {sensor['id']}")
            self.assertEqual(published[config_topic], '',
                f"Expected empty payload for disabled sensor {sensor['id']}")

    def test_enabled_group_state_topic_points_to_group_topic(self):
        """Discovery config state_topic must match the group's topic."""
        self.bridge.groups['tpv']['enabled'] = True

        mock_client = self._run_connect_mqtt_with_mock()

        published = {call[0][0]: call[0][1]
                     for call in mock_client.publish.call_args_list}
        tpv = self.bridge.groups['tpv']
        sensor = tpv['sensors'][0]
        config_topic = f"homeassistant/sensor/{sensor['id']}/config"
        self.assertIn(config_topic, published)
        config = json.loads(published[config_topic])
        self.assertEqual(config['state_topic'], 'gps_monitor/tpv')


class TestSatelliteTracking(unittest.TestCase):
    """Verify per-PRN first-seen tracking and stale PRN pruning in _handle_sky."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def _sky_msg(self, prns):
        """Build a SKY message with the given list of PRN numbers (all used=False, ss=20)."""
        return {
            'class': 'SKY',
            'satellites': [{'PRN': p, 'el': 10, 'az': 90, 'ss': 20, 'used': False} for p in prns],
        }

    def test_first_seen_recorded_on_initial_sky(self):
        """PRNs seen for the first time are added to satellite_first_seen."""
        self.bridge._handle_sky(self._sky_msg([1, 2, 3]))
        self.assertIn(1, self.bridge.satellite_first_seen)
        self.assertIn(2, self.bridge.satellite_first_seen)
        self.assertIn(3, self.bridge.satellite_first_seen)

    def test_first_seen_not_overwritten_on_repeat(self):
        """A PRN seen a second time keeps its original first-seen timestamp."""
        self.bridge._handle_sky(self._sky_msg([1]))
        original_ts = self.bridge.satellite_first_seen[1]
        self.bridge._handle_sky(self._sky_msg([1]))
        self.assertEqual(self.bridge.satellite_first_seen[1], original_ts)

    def test_seen_seconds_in_satellite_entry(self):
        """Each satellite entry carries a non-negative integer 'seen' field."""
        self.bridge._handle_sky(self._sky_msg([5]))
        sat = self.bridge.groups['sky']['state']['satellites'][0]
        self.assertIn('seen', sat)
        self.assertIsInstance(sat['seen'], int)
        self.assertGreaterEqual(sat['seen'], 0)

    def test_stale_prns_pruned_when_no_longer_visible(self):
        """PRNs that disappear from the satellite list are removed from satellite_first_seen."""
        self.bridge._handle_sky(self._sky_msg([1, 2, 3]))
        # PRN 2 and 3 disappear
        self.bridge._handle_sky(self._sky_msg([1]))
        self.assertIn(1, self.bridge.satellite_first_seen)
        self.assertNotIn(2, self.bridge.satellite_first_seen)
        self.assertNotIn(3, self.bridge.satellite_first_seen)

    def test_gnssid_included_when_present(self):
        """gnssid is included in the satellite entry when the message provides it."""
        msg = {
            'class': 'SKY',
            'satellites': [{'PRN': 1, 'el': 10, 'az': 90, 'ss': 20, 'used': True, 'gnssid': 0}],
        }
        self.bridge._handle_sky(msg)
        sat = self.bridge.groups['sky']['state']['satellites'][0]
        self.assertIn('gnssid', sat)
        self.assertEqual(sat['gnssid'], 0)

    def test_gnssid_omitted_when_absent(self):
        """gnssid is not included in the satellite entry when the message omits it."""
        self.bridge._handle_sky(self._sky_msg([1]))
        sat = self.bridge.groups['sky']['state']['satellites'][0]
        self.assertNotIn('gnssid', sat)

    def test_svid_included_when_present(self):
        """svid is included in the satellite entry when the message provides it."""
        msg = {
            'class': 'SKY',
            'satellites': [{'PRN': 1, 'el': 10, 'az': 90, 'ss': 20, 'used': True, 'svid': 7}],
        }
        self.bridge._handle_sky(msg)
        sat = self.bridge.groups['sky']['state']['satellites'][0]
        self.assertIn('svid', sat)
        self.assertEqual(sat['svid'], 7)


class TestSatelliteSortOrder(unittest.TestCase):
    """Verify the satellite list is sorted: used first, then by descending SNR."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def test_used_satellites_sorted_before_unused(self):
        """Used satellites appear before unused ones regardless of SNR."""
        msg = {
            'class': 'SKY',
            'satellites': [
                {'PRN': 1, 'el': 10, 'az': 0, 'ss': 10, 'used': False},
                {'PRN': 2, 'el': 10, 'az': 0, 'ss': 40, 'used': True},
                {'PRN': 3, 'el': 10, 'az': 0, 'ss': 5,  'used': False},
                {'PRN': 4, 'el': 10, 'az': 0, 'ss': 30, 'used': True},
            ],
        }
        self.bridge._handle_sky(msg)
        sats = self.bridge.groups['sky']['state']['satellites']
        used_indices = [i for i, s in enumerate(sats) if s['used']]
        unused_indices = [i for i, s in enumerate(sats) if not s['used']]
        self.assertTrue(max(used_indices) < min(unused_indices),
                        "All used sats must appear before all unused sats")

    def test_within_used_sorted_by_descending_snr(self):
        """Among used satellites, higher SNR comes first."""
        msg = {
            'class': 'SKY',
            'satellites': [
                {'PRN': 1, 'el': 10, 'az': 0, 'ss': 20, 'used': True},
                {'PRN': 2, 'el': 10, 'az': 0, 'ss': 40, 'used': True},
                {'PRN': 3, 'el': 10, 'az': 0, 'ss': 30, 'used': True},
            ],
        }
        self.bridge._handle_sky(msg)
        sats = self.bridge.groups['sky']['state']['satellites']
        snrs = [s['ss'] for s in sats]
        self.assertEqual(snrs, sorted(snrs, reverse=True))

    def test_within_unused_sorted_by_descending_snr(self):
        """Among unused satellites, higher SNR comes first."""
        msg = {
            'class': 'SKY',
            'satellites': [
                {'PRN': 1, 'el': 10, 'az': 0, 'ss': 5,  'used': False},
                {'PRN': 2, 'el': 10, 'az': 0, 'ss': 25, 'used': False},
                {'PRN': 3, 'el': 10, 'az': 0, 'ss': 15, 'used': False},
            ],
        }
        self.bridge._handle_sky(msg)
        sats = self.bridge.groups['sky']['state']['satellites']
        snrs = [s['ss'] for s in sats]
        self.assertEqual(snrs, sorted(snrs, reverse=True))


class TestToffPpsFields(unittest.TestCase):
    """Verify that TOFF and PPS handlers populate all state fields."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def test_toff_all_raw_fields_stored(self):
        """TOFF handler stores real_sec, real_nsec, clock_sec, clock_nsec."""
        self.bridge._handle_toff({
            'class': 'TOFF',
            'real_sec': 1000, 'real_nsec': 500,
            'clock_sec': 999, 'clock_nsec': 100,
        })
        toff = self.bridge.groups['toff']['state']
        self.assertEqual(toff['real_sec'], 1000)
        self.assertEqual(toff['real_nsec'], 500)
        self.assertEqual(toff['clock_sec'], 999)
        self.assertEqual(toff['clock_nsec'], 100)

    def test_toff_precision_stored_when_present(self):
        """TOFF handler stores precision when provided."""
        self.bridge._handle_toff({
            'class': 'TOFF',
            'real_sec': 0, 'real_nsec': 0, 'clock_sec': 0, 'clock_nsec': 0,
            'precision': -20,
        })
        self.assertEqual(self.bridge.groups['toff']['state']['precision'], -20)

    def test_toff_shm_stored_when_present(self):
        """TOFF handler stores shm when provided."""
        self.bridge._handle_toff({
            'class': 'TOFF',
            'real_sec': 0, 'real_nsec': 0, 'clock_sec': 0, 'clock_nsec': 0,
            'shm': 'PPS0',
        })
        self.assertEqual(self.bridge.groups['toff']['state']['shm'], 'PPS0')

    def test_toff_payload_contains_all_keys(self):
        """TOFF published payload contains all expected keys."""
        self.bridge.mqtt_client = MagicMock()
        self.bridge.groups['toff']['enabled'] = True
        self.bridge.groups['toff']['interval'] = 0
        self.bridge._maybe_publish('toff')
        payload = json.loads(self.bridge.mqtt_client.publish.call_args[0][1])
        expected_keys = {
            'real_sec', 'real_nsec', 'clock_sec', 'clock_nsec',
            'offset_ns', 'precision', 'shm',
        }
        self.assertEqual(set(payload.keys()), expected_keys)

    def test_pps_all_raw_fields_stored(self):
        """PPS handler stores real_sec, real_nsec, clock_sec, clock_nsec."""
        self.bridge._handle_pps({
            'class': 'PPS',
            'real_sec': 2000, 'real_nsec': 800,
            'clock_sec': 2000, 'clock_nsec': 200,
        })
        pps = self.bridge.groups['pps']['state']
        self.assertEqual(pps['real_sec'], 2000)
        self.assertEqual(pps['real_nsec'], 800)
        self.assertEqual(pps['clock_sec'], 2000)
        self.assertEqual(pps['clock_nsec'], 200)

    def test_pps_shm_stored_when_present(self):
        """PPS handler stores shm when provided."""
        self.bridge._handle_pps({
            'class': 'PPS',
            'real_sec': 0, 'real_nsec': 0, 'clock_sec': 0, 'clock_nsec': 0,
            'shm': 'PPS0',
        })
        self.assertEqual(self.bridge.groups['pps']['state']['shm'], 'PPS0')

    def test_pps_payload_contains_all_keys(self):
        """PPS published payload contains all expected keys."""
        self.bridge.mqtt_client = MagicMock()
        self.bridge.groups['pps']['enabled'] = True
        self.bridge.groups['pps']['interval'] = 0
        self.bridge._maybe_publish('pps')
        payload = json.loads(self.bridge.mqtt_client.publish.call_args[0][1])
        expected_keys = {
            'real_sec', 'real_nsec', 'clock_sec', 'clock_nsec',
            'offset_ns', 'precision', 'shm',
        }
        self.assertEqual(set(payload.keys()), expected_keys)


class TestHandleErrorTruncation(unittest.TestCase):
    """Verify _handle_error stores the message and truncates at 256 chars."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def test_short_error_stored_verbatim(self):
        """Error messages shorter than 256 chars are stored as-is."""
        self.bridge._handle_error({'class': 'ERROR', 'message': 'short error'})
        self.assertEqual(self.bridge.groups['tpv']['state']['last_error'], 'short error')

    def test_long_error_truncated_to_256(self):
        """Error messages longer than 256 chars are truncated to 256."""
        long_msg = 'E' * 300
        self.bridge._handle_error({'class': 'ERROR', 'message': long_msg})
        stored = self.bridge.groups['tpv']['state']['last_error']
        self.assertEqual(len(stored), 256)
        self.assertEqual(stored, long_msg[:256])

    def test_missing_message_key_defaults_to_unknown(self):
        """ERROR message without 'message' key stores 'Unknown'."""
        self.bridge._handle_error({'class': 'ERROR'})
        self.assertEqual(self.bridge.groups['tpv']['state']['last_error'], 'Unknown')


class TestDeprecatedSensorClearing(unittest.TestCase):
    """Verify _connect_mqtt publishes empty retained messages for deprecated sensor IDs."""

    def setUp(self):
        self.bridge = gpsd_monitor.GPSDMQTTBridge()

    def _run_connect_mqtt_with_mock(self):
        mock_client = MagicMock()
        mock_client.connect.return_value = None
        mock_client.loop_start.return_value = None
        with patch('gpsd_monitor.mqtt.Client', return_value=mock_client):
            self.bridge._connect_mqtt()
        return mock_client

    def test_deprecated_ids_get_empty_retained_publish(self):
        """Each deprecated sensor ID receives an empty retained discovery publish on connect."""
        mock_client = self._run_connect_mqtt_with_mock()
        published = {call[0][0]: call[0][1] for call in mock_client.publish.call_args_list}
        for sensor_id in gpsd_monitor.DEPRECATED_SENSOR_IDS:
            config_topic = f"homeassistant/sensor/{sensor_id}/config"
            self.assertIn(config_topic, published,
                f"Missing clear publish for deprecated sensor {sensor_id}")
            self.assertEqual(published[config_topic], '',
                f"Expected empty payload for deprecated sensor {sensor_id}")


if __name__ == '__main__':
    unittest.main()
