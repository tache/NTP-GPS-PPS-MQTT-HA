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
# Claude Generated: version 1 - Tests for NTP_PUBLISH_INTERVAL env var
# Claude Generated: version 2 - Add tests for explicit connect_mqtt() parameter passing
# Claude Generated: version 3 - Add tests for parse_ntpq_rv() and collect_ntp_state()
"""Tests for ntpd_monitor.py configurable publish interval and connect_mqtt signature."""

import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

# Required env vars so ntpd_monitor.py doesn't sys.exit on import
os.environ.setdefault('MQTT_BROKER', 'localhost')
os.environ.setdefault('MQTT_USERNAME', 'test')
os.environ.setdefault('MQTT_PASSWORD', 'test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestNTPPublishInterval(unittest.TestCase):
    """Verify NTP_PUBLISH_INTERVAL env var controls UPDATE_INTERVAL."""

    def _reload_module(self):
        """Reload ntpd_monitor to pick up env var changes."""
        import ntpd_monitor
        return importlib.reload(ntpd_monitor)

    def test_default_interval_is_30(self):
        """UPDATE_INTERVAL defaults to 30 when NTP_PUBLISH_INTERVAL is not set."""
        os.environ.pop('NTP_PUBLISH_INTERVAL', None)
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 30)

    def test_interval_reads_from_env(self):
        """UPDATE_INTERVAL reads NTP_PUBLISH_INTERVAL from environment."""
        os.environ['NTP_PUBLISH_INTERVAL'] = '60'
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 60)
        os.environ.pop('NTP_PUBLISH_INTERVAL')

    def test_interval_zero_is_valid(self):
        """NTP_PUBLISH_INTERVAL=0 is a valid value."""
        os.environ['NTP_PUBLISH_INTERVAL'] = '0'
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 0)
        os.environ.pop('NTP_PUBLISH_INTERVAL')


class TestConnectMqttExplicitParams(unittest.TestCase):
    """Verify connect_mqtt() uses the parameters passed to it, not module globals."""

    def _get_module(self):
        import ntpd_monitor
        return importlib.reload(ntpd_monitor)

    def test_username_pw_set_uses_passed_credentials(self):
        """connect_mqtt passes the provided username and password to the MQTT client."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('ntpd_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker.example.com', 1883, 'myuser', 'mypass', False, None)

        mock_client.username_pw_set.assert_called_once_with('myuser', 'mypass')

    def test_connect_uses_passed_broker_and_port(self):
        """connect_mqtt calls client.connect() with the provided broker and port."""
        mod = self._get_module()
        mock_client = MagicMock()

        with patch('ntpd_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('ha.local', 8883, 'u', 'p', False, None)

        mock_client.connect.assert_called_once_with('ha.local', 8883, keepalive=60)

    def test_tls_set_called_when_tls_true(self):
        """connect_mqtt calls tls_set() with the provided ca_cert when tls=True."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('ntpd_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker', 8883, 'u', 'p', True, '/path/to/ca.crt')

        mock_client.tls_set.assert_called_once_with(ca_certs='/path/to/ca.crt')

    def test_tls_set_not_called_when_tls_false(self):
        """connect_mqtt does not call tls_set() when tls=False."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('ntpd_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker', 1883, 'u', 'p', False, None)

        mock_client.tls_set.assert_not_called()


class TestParseNtpqRv(unittest.TestCase):
    """Tests for parse_ntpq_rv() — the ntpq output parser."""

    def setUp(self):
        import ntpd_monitor
        self.parse = ntpd_monitor.parse_ntpq_rv

    def test_single_line_basic(self):
        """Parses a simple single-line key=value string."""
        result = self.parse("stratum=1, offset=0.123")
        self.assertEqual(result['stratum'], '1')
        self.assertEqual(result['offset'], '0.123')

    def test_multiline_joined(self):
        """Multi-line output is joined and parsed as one stream."""
        output = "stratum=1, offset=0.123,\nfrequency=-12.345, refid=PPS"
        result = self.parse(output)
        self.assertEqual(result['stratum'], '1')
        self.assertEqual(result['frequency'], '-12.345')
        self.assertEqual(result['refid'], 'PPS')

    def test_empty_string_returns_empty_dict(self):
        """Empty input yields an empty dict."""
        self.assertEqual(self.parse(''), {})

    def test_whitespace_only_returns_empty_dict(self):
        """Whitespace-only input yields an empty dict."""
        self.assertEqual(self.parse('   \n  '), {})

    def test_item_without_equals_is_skipped(self):
        """Items with no '=' are silently ignored."""
        result = self.parse("stratum=1, some_flag, offset=0.5")
        self.assertNotIn('some_flag', result)
        self.assertEqual(result['stratum'], '1')
        self.assertEqual(result['offset'], '0.5')

    def test_value_containing_equals_uses_first_only(self):
        """partition('=') ensures only the first '=' splits key from value."""
        result = self.parse('version="ntpd 4.2.8p15 (1)"')
        self.assertEqual(result['version'], '"ntpd 4.2.8p15 (1)"')

    def test_keys_and_values_are_stripped(self):
        """Leading/trailing whitespace is stripped from keys and values."""
        result = self.parse("  stratum = 2 , offset = -0.001 ")
        self.assertEqual(result['stratum'], '2')
        self.assertEqual(result['offset'], '-0.001')

    def test_typical_ntpq_output(self):
        """Parses a representative block of real ntpq -c rv output."""
        output = (
            "associd=0 status=0615 leap_none, sync_ntp, 1 event, clock_sync,\n"
            "version=\"ntpd 4.2.8p15\",\n"
            "leap=0, stratum=1, precision=-20, rootdelay=0.000,\n"
            "refid=PPS, offset=-0.001, sys_jitter=0.005,\n"
            "frequency=-12.345, clk_jitter=0.003, clk_wander=0.001,\n"
            "clock=e7d4b5c3.12345678  Thu, Mar 21 2026  3:14:05.117"
        )
        result = self.parse(output)
        self.assertEqual(result['leap'], '0')
        self.assertEqual(result['stratum'], '1')
        self.assertEqual(result['refid'], 'PPS')
        self.assertEqual(result['offset'], '-0.001')
        self.assertIn('clock', result)


class TestCollectNtpState(unittest.TestCase):
    """Tests for collect_ntp_state() — subprocess wrapper and field extraction."""

    def setUp(self):
        import ntpd_monitor
        self.mod = ntpd_monitor
        self.collect = ntpd_monitor.collect_ntp_state

    def _make_result(self, stdout, returncode=0):
        """Helper: build a fake subprocess.CompletedProcess."""
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        return result

    def test_all_keys_always_present(self):
        """Return dict always contains all expected keys, even on failure."""
        with patch('subprocess.run', side_effect=Exception("ntpq not found")):
            state = self.collect()
        expected_keys = {
            'ntp_synced', 'ntp_stratum', 'ntp_offset', 'ntp_refid',
            'ntp_jitter', 'ntp_time', 'ntp_frequency', 'ntp_clk_jitter',
            'ntp_clk_wander', 'ntp_version', 'ntp_leap', 'ntp_precision',
        }
        self.assertEqual(set(state.keys()), expected_keys)

    def test_subprocess_failure_returns_defaults(self):
        """Non-zero returncode leaves all fields at their defaults."""
        with patch('subprocess.run', return_value=self._make_result('', returncode=1)):
            state = self.collect()
        self.assertEqual(state['ntp_synced'], 'Unknown')
        self.assertIsNone(state['ntp_stratum'])
        self.assertIsNone(state['ntp_offset'])

    def test_subprocess_exception_returns_defaults(self):
        """Exception from subprocess leaves all fields at their defaults."""
        with patch('subprocess.run', side_effect=FileNotFoundError("ntpq")):
            state = self.collect()
        self.assertEqual(state['ntp_synced'], 'Unknown')
        self.assertIsNone(state['ntp_stratum'])


    def test_missing_leap_sets_synced_unknown(self):
        """Output with no leap field → ntp_synced='Unknown'."""
        with patch('subprocess.run', return_value=self._make_result("stratum=1")):
            state = self.collect()
        self.assertEqual(state['ntp_synced'], 'Unknown')

    def test_stratum_parsed_as_int(self):
        """ntp_stratum is returned as an integer."""
        with patch('subprocess.run', return_value=self._make_result("leap=0, stratum=1")):
            state = self.collect()
        self.assertIsInstance(state['ntp_stratum'], int)
        self.assertEqual(state['ntp_stratum'], 1)

    def test_offset_parsed_as_float_rounded_to_4(self):
        """ntp_offset is a float rounded to 4 decimal places."""
        with patch('subprocess.run', return_value=self._make_result("leap=0, offset=-0.0012345")):
            state = self.collect()
        self.assertIsInstance(state['ntp_offset'], float)
        self.assertEqual(state['ntp_offset'], round(-0.0012345, 4))

    def test_refid_quotes_stripped(self):
        """Quoted refid values have surrounding quotes removed."""
        with patch('subprocess.run', return_value=self._make_result('leap=0, refid="PPS"')):
            state = self.collect()
        self.assertEqual(state['ntp_refid'], 'PPS')

    def test_refid_truncated_to_64_chars(self):
        """refid longer than 64 chars is truncated."""
        long_refid = 'X' * 100
        with patch('subprocess.run', return_value=self._make_result(f"leap=0, refid={long_refid}")):
            state = self.collect()
        self.assertEqual(len(state['ntp_refid']), 64)

    def test_version_truncated_to_128_chars(self):
        """version longer than 128 chars is truncated."""
        long_ver = '"' + 'V' * 200 + '"'
        with patch('subprocess.run', return_value=self._make_result(f"leap=0, version={long_ver}")):
            state = self.collect()
        self.assertLessEqual(len(state['ntp_version']), 128)

    def test_jitter_frequency_clk_fields_extracted(self):
        """sys_jitter, frequency, clk_jitter, clk_wander are all extracted."""
        output = "leap=0, sys_jitter=0.005, frequency=-12.345, clk_jitter=0.003, clk_wander=0.001"
        with patch('subprocess.run', return_value=self._make_result(output)):
            state = self.collect()
        self.assertAlmostEqual(state['ntp_jitter'], 0.005, places=4)
        self.assertAlmostEqual(state['ntp_frequency'], -12.345, places=4)
        self.assertAlmostEqual(state['ntp_clk_jitter'], 0.003, places=4)
        self.assertAlmostEqual(state['ntp_clk_wander'], 0.001, places=4)

    def test_precision_parsed_as_int(self):
        """ntp_precision is returned as an integer."""
        with patch('subprocess.run', return_value=self._make_result("leap=0, precision=-20")):
            state = self.collect()
        self.assertIsInstance(state['ntp_precision'], int)
        self.assertEqual(state['ntp_precision'], -20)

    def test_clock_human_part_extracted(self):
        """The human-readable time is extracted from the clock field (after hex timestamp)."""
        clock_val = "e7d4b5c3.12345678  Thu, Mar 21 2026  3:14:05.117"
        with patch('subprocess.run', return_value=self._make_result(f"leap=0, clock={clock_val}")):
            state = self.collect()
        self.assertEqual(state['ntp_time'], "Thu, Mar 21 2026  3:14:05.117")

    def test_clock_no_double_space_uses_full_string(self):
        """If clock field has no double-space separator, the full value (up to 64 chars) is used."""
        clock_val = "e7d4b5c3.12345678"
        with patch('subprocess.run', return_value=self._make_result(f"leap=0, clock={clock_val}")):
            state = self.collect()
        self.assertEqual(state['ntp_time'], clock_val[:64])

    def test_ntp_time_truncated_to_64_chars(self):
        """ntp_time is capped at 64 characters."""
        long_time = "A" * 100
        clock_val = f"e7d4b5c3.12345678  {long_time}"
        with patch('subprocess.run', return_value=self._make_result(f"leap=0, clock={clock_val}")):
            state = self.collect()
        self.assertEqual(len(state['ntp_time']), 64)


@pytest.mark.parametrize("leap_val,expected_synced,expected_leap", [
    ('0', 'Yes',  'None'),
    ('1', 'Yes',  'Add Second'),
    ('2', 'Yes',  'Delete Second'),
    ('3', 'No',   'Unsynchronized'),
])
def test_leap_indicator_mapping(leap_val, expected_synced, expected_leap):
    """Each leap value maps to the correct ntp_synced and ntp_leap strings."""
    import ntpd_monitor
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"leap={leap_val}"
    with patch('subprocess.run', return_value=r):
        state = ntpd_monitor.collect_ntp_state()
    assert state['ntp_synced'] == expected_synced
    assert state['ntp_leap'] == expected_leap


if __name__ == '__main__':
    unittest.main()
