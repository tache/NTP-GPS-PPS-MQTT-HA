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
# Claude Generated: version 1 - Tests for SYSTEM_PUBLISH_INTERVAL env var
# Claude Generated: version 2 - Add tests for explicit connect_mqtt() parameter passing
# Claude Generated: version 3 - Add tests for data collection functions and collect_system_state()
# Claude Generated: version 4 - Add tests for memory detail, swap, disk, load average
"""Tests for system_monitor.py configurable publish interval and connect_mqtt signature."""

import importlib
import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Required env vars so system_monitor.py doesn't sys.exit on import
os.environ.setdefault('MQTT_BROKER', 'localhost')
os.environ.setdefault('MQTT_USERNAME', 'test')
os.environ.setdefault('MQTT_PASSWORD', 'test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestSystemPublishInterval(unittest.TestCase):
    """Verify SYSTEM_PUBLISH_INTERVAL env var controls UPDATE_INTERVAL."""

    def _reload_module(self):
        """Reload system_monitor to pick up env var changes."""
        import system_monitor
        return importlib.reload(system_monitor)

    def test_default_interval_is_30(self):
        """UPDATE_INTERVAL defaults to 30 when SYSTEM_PUBLISH_INTERVAL is not set."""
        os.environ.pop('SYSTEM_PUBLISH_INTERVAL', None)
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 30)

    def test_interval_reads_from_env(self):
        """UPDATE_INTERVAL reads SYSTEM_PUBLISH_INTERVAL from environment."""
        os.environ['SYSTEM_PUBLISH_INTERVAL'] = '120'
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 120)
        os.environ.pop('SYSTEM_PUBLISH_INTERVAL')

    def test_interval_zero_is_valid(self):
        """SYSTEM_PUBLISH_INTERVAL=0 is a valid value."""
        os.environ['SYSTEM_PUBLISH_INTERVAL'] = '0'
        mod = self._reload_module()
        self.assertEqual(mod.UPDATE_INTERVAL, 0)
        os.environ.pop('SYSTEM_PUBLISH_INTERVAL')


class TestConnectMqttExplicitParams(unittest.TestCase):
    """Verify connect_mqtt() uses the parameters passed to it, not module globals."""

    def _get_module(self):
        import system_monitor
        return importlib.reload(system_monitor)

    def test_username_pw_set_uses_passed_credentials(self):
        """connect_mqtt passes the provided username and password to the MQTT client."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('system_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker.example.com', 1883, 'myuser', 'mypass', False, None)

        mock_client.username_pw_set.assert_called_once_with('myuser', 'mypass')

    def test_connect_uses_passed_broker_and_port(self):
        """connect_mqtt calls client.connect() with the provided broker and port."""
        mod = self._get_module()
        mock_client = MagicMock()

        with patch('system_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('ha.local', 8883, 'u', 'p', False, None)

        mock_client.connect.assert_called_once_with('ha.local', 8883, keepalive=60)

    def test_tls_set_called_when_tls_true(self):
        """connect_mqtt calls tls_set() with the provided ca_cert when tls=True."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('system_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker', 8883, 'u', 'p', True, '/path/to/ca.crt')

        mock_client.tls_set.assert_called_once_with(ca_certs='/path/to/ca.crt')

    def test_tls_set_not_called_when_tls_false(self):
        """connect_mqtt does not call tls_set() when tls=False."""
        mod = self._get_module()
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("no broker")

        with patch('system_monitor.mqtt') as mock_mqtt:
            mock_mqtt.Client.return_value = mock_client
            mock_mqtt.CallbackAPIVersion.VERSION2 = 2
            mod.connect_mqtt('broker', 1883, 'u', 'p', False, None)

        mock_client.tls_set.assert_not_called()


class TestGetCpuTemp(unittest.TestCase):
    """Tests for get_cpu_temp() — temperature sensor key fallback order."""

    def setUp(self):
        import system_monitor
        self.get_cpu_temp = system_monitor.get_cpu_temp

    def _make_temp(self, current):
        """Return a fake psutil temperature named tuple."""
        t = MagicMock()
        t.current = current
        return t

    def test_returns_none_when_no_known_key(self):
        """Returns None when no recognised temperature sensor key exists."""
        temps = {'unknown_sensor': [self._make_temp(50.0)]}
        with patch('system_monitor.psutil.sensors_temperatures', return_value=temps, create=True):
            result = self.get_cpu_temp()
        self.assertIsNone(result)

    def test_returns_none_when_sensors_raises(self):
        """Returns None when psutil raises an exception."""
        with patch('system_monitor.psutil.sensors_temperatures', side_effect=Exception("no sensors"), create=True):
            result = self.get_cpu_temp()
        self.assertIsNone(result)

    def test_value_rounded_to_one_decimal(self):
        """Temperature is rounded to one decimal place."""
        temps = {'cpu_thermal': [self._make_temp(55.678)]}
        with patch('system_monitor.psutil.sensors_temperatures', return_value=temps, create=True):
            result = self.get_cpu_temp()
        self.assertEqual(result, 55.7)


class TestGetUptime(unittest.TestCase):
    """Tests for get_uptime() — uptime string formatting."""

    def setUp(self):
        import system_monitor
        self.get_uptime = system_monitor.get_uptime

    def test_format_days_hours_minutes(self):
        """Formats uptime as 'Xd Yh Zm'."""
        import time
        # Fake boot_time: 1 day, 2 hours, 3 minutes ago
        boot_offset = 1 * 86400 + 2 * 3600 + 3 * 60
        with patch('psutil.boot_time', return_value=time.time() - boot_offset):
            result = self.get_uptime()
        self.assertEqual(result, '1d 2h 3m')

    def test_zero_uptime(self):
        """Handles zero uptime (just booted)."""
        import time
        with patch('psutil.boot_time', return_value=time.time()):
            result = self.get_uptime()
        self.assertEqual(result, '0d 0h 0m')

    def test_minutes_only(self):
        """Shows 0d 0h Nm when uptime is under an hour."""
        import time
        with patch('psutil.boot_time', return_value=time.time() - 15 * 60):
            result = self.get_uptime()
        self.assertEqual(result, '0d 0h 15m')


class TestGetRtcSysfs(unittest.TestCase):
    """Tests for get_rtc_time() and get_rtc_date() — sysfs reads."""

    def setUp(self):
        import system_monitor
        self.get_rtc_time = system_monitor.get_rtc_time
        self.get_rtc_date = system_monitor.get_rtc_date

    def test_rtc_time_returns_stripped_string(self):
        """get_rtc_time() returns the stripped content of the sysfs file."""
        with patch('builtins.open', mock_open(read_data='12:34:56\n')):
            result = self.get_rtc_time()
        self.assertEqual(result, '12:34:56')

    def test_rtc_time_returns_none_on_file_not_found(self):
        """get_rtc_time() returns None when the sysfs file doesn't exist."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = self.get_rtc_time()
        self.assertIsNone(result)

    def test_rtc_time_returns_none_on_permission_error(self):
        """get_rtc_time() returns None on PermissionError."""
        with patch('builtins.open', side_effect=PermissionError):
            result = self.get_rtc_time()
        self.assertIsNone(result)

    def test_rtc_date_returns_stripped_string(self):
        """get_rtc_date() returns the stripped content of the sysfs file."""
        with patch('builtins.open', mock_open(read_data='2026-03-25\n')):
            result = self.get_rtc_date()
        self.assertEqual(result, '2026-03-25')

    def test_rtc_date_returns_none_on_file_not_found(self):
        """get_rtc_date() returns None when the sysfs file doesn't exist."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = self.get_rtc_date()
        self.assertIsNone(result)


class TestGetRtcBattery(unittest.TestCase):
    """Tests for get_rtc_battery() — i2cget subprocess + OSF bit parsing."""

    def setUp(self):
        import system_monitor
        self.get_rtc_battery = system_monitor.get_rtc_battery

    def _make_result(self, stdout, returncode=0):
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    def test_returns_unknown_on_nonzero_returncode(self):
        """Non-zero returncode from i2cget → 'Unknown'."""
        with patch('subprocess.run', return_value=self._make_result('', returncode=1)):
            self.assertEqual(self.get_rtc_battery(), 'Unknown')

    def test_returns_unknown_on_exception(self):
        """Exception from subprocess → 'Unknown'."""
        with patch('subprocess.run', side_effect=FileNotFoundError("i2cget")):
            self.assertEqual(self.get_rtc_battery(), 'Unknown')

    def test_returns_unknown_on_empty_stdout(self):
        """Empty stdout from i2cget → 'Unknown'."""
        with patch('subprocess.run', return_value=self._make_result('')):
            self.assertEqual(self.get_rtc_battery(), 'Unknown')


class TestCollectSystemState(unittest.TestCase):
    """Tests for collect_system_state() — field assembly and conditional inclusion."""

    def setUp(self):
        import system_monitor
        self.collect = system_monitor.collect_system_state

    def _patch_all(self, cpu_percent=10.0, memory_percent=50.0, uptime='0d 1h 0m',
                   cpu_temp=None, rtc_time=None, rtc_date=None, rtc_battery=None,
                   sys_time_data=None, rtc_epoch=None, rtc_iso_val=None):
        """Patch all data-collection helpers with controllable return values."""
        default_sys_time = {'sys_time': '2026-01-01T00:00:00+00:00', 'sys_epoch': 1735689600}
        return [
            patch('system_monitor.get_cpu_percent', return_value=cpu_percent),
            patch('system_monitor.get_memory_percent', return_value=memory_percent),
            patch('system_monitor.get_uptime', return_value=uptime),
            patch('system_monitor.get_cpu_temp', return_value=cpu_temp),
            patch('system_monitor.get_rtc_time', return_value=rtc_time),
            patch('system_monitor.get_rtc_date', return_value=rtc_date),
            patch('system_monitor.get_rtc_battery', return_value=rtc_battery),
            patch('system_monitor.get_memory_detail', return_value={}),
            patch('system_monitor.get_swap_detail', return_value={}),
            patch('system_monitor.get_disk_usage', return_value={}),
            patch('system_monitor.get_load_average', return_value=None),
            patch('system_monitor.get_system_time', return_value=sys_time_data or default_sys_time),
            patch('system_monitor.get_rtc_epoch', return_value=rtc_epoch),
            patch('system_monitor.get_rtc_iso', return_value=rtc_iso_val),
        ]

    def _run(self, patches):
        """Apply all patches via ExitStack and call collect_system_state()."""
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return self.collect()

    def test_always_includes_core_fields(self):
        """cpu_percent, memory_percent, and uptime are always in the state dict."""
        state = self._run(self._patch_all())
        self.assertIn('cpu_percent', state)
        self.assertIn('memory_percent', state)
        self.assertIn('uptime', state)

    def test_cpu_temp_included_when_available(self):
        """cpu_temp is included in state when get_cpu_temp() returns a value."""
        state = self._run(self._patch_all(cpu_temp=55.0))
        self.assertIn('cpu_temp', state)
        self.assertEqual(state['cpu_temp'], 55.0)

    def test_cpu_temp_omitted_when_none(self):
        """cpu_temp is omitted from state when get_cpu_temp() returns None."""
        state = self._run(self._patch_all(cpu_temp=None))
        self.assertNotIn('cpu_temp', state)

    def test_rtc_fields_included_when_available(self):
        """rtc_time, rtc_date, rtc_battery are included when their getters return values."""
        state = self._run(self._patch_all(rtc_time='12:34:56', rtc_date='2026-03-25', rtc_battery='OK'))
        self.assertEqual(state['rtc_time'], '12:34:56')
        self.assertEqual(state['rtc_date'], '2026-03-25')
        self.assertEqual(state['rtc_battery'], 'OK')

    def test_rtc_fields_omitted_when_none(self):
        """rtc_time, rtc_date, rtc_battery are omitted when their getters return None."""
        state = self._run(self._patch_all(rtc_time=None, rtc_date=None, rtc_battery=None))
        self.assertNotIn('rtc_time', state)
        self.assertNotIn('rtc_date', state)
        self.assertNotIn('rtc_battery', state)

    def test_core_field_values_match_helpers(self):
        """State dict values come from the helper functions."""
        state = self._run(self._patch_all(cpu_percent=25.5, memory_percent=70.2, uptime='3d 4h 5m'))
        self.assertEqual(state['cpu_percent'], 25.5)
        self.assertEqual(state['memory_percent'], 70.2)
        self.assertEqual(state['uptime'], '3d 4h 5m')

    def test_sys_time_and_epoch_always_present(self):
        """sys_time and sys_epoch are always present in state."""
        state = self._run(self._patch_all())
        self.assertIn('sys_time', state)
        self.assertIn('sys_epoch', state)
        self.assertEqual(state['sys_time'], '2026-01-01T00:00:00+00:00')
        self.assertEqual(state['sys_epoch'], 1735689600)

    def test_rtc_derived_fields_present_when_both_available(self):
        """rtc_epoch, rtc_iso, rtc_drift all present when get_rtc_epoch and get_rtc_iso return values."""
        state = self._run(self._patch_all(
            rtc_epoch=1742930519,
            rtc_iso_val='2026-03-25T18:42:01+00:00',
        ))
        self.assertIn('rtc_epoch', state)
        self.assertIn('rtc_iso', state)
        self.assertIn('rtc_drift', state)
        self.assertEqual(state['rtc_epoch'], 1742930519)
        self.assertEqual(state['rtc_iso'], '2026-03-25T18:42:01+00:00')
        # drift = sys_epoch(1735689600) - rtc_epoch(1742930519) = -7240919
        self.assertEqual(state['rtc_drift'], 1735689600 - 1742930519)

    def test_rtc_derived_fields_omitted_when_epoch_none(self):
        """rtc_epoch, rtc_iso, rtc_drift all omitted when get_rtc_epoch returns None."""
        state = self._run(self._patch_all(
            rtc_epoch=None,
            rtc_iso_val='2026-03-25T18:42:01+00:00',
        ))
        self.assertNotIn('rtc_epoch', state)
        self.assertNotIn('rtc_iso', state)
        self.assertNotIn('rtc_drift', state)

    def test_rtc_derived_fields_omitted_when_iso_none(self):
        """rtc_epoch, rtc_iso, rtc_drift all omitted when get_rtc_iso returns None."""
        state = self._run(self._patch_all(
            rtc_epoch=1742930519,
            rtc_iso_val=None,
        ))
        self.assertNotIn('rtc_epoch', state)
        self.assertNotIn('rtc_iso', state)
        self.assertNotIn('rtc_drift', state)


@pytest.mark.parametrize("sensor_key,temp_value", [
    ('cpu_thermal', 55.0),
    ('coretemp',    60.0),
    ('k10temp',     45.0),
    ('acpitz',      40.0),
])
def test_cpu_temp_recognised_sensor_key(sensor_key, temp_value):
    """get_cpu_temp() returns the reading for each recognised sensor key."""
    import system_monitor
    t = MagicMock()
    t.current = temp_value
    temps = {sensor_key: [t]}
    with patch('system_monitor.psutil.sensors_temperatures', return_value=temps, create=True):
        assert system_monitor.get_cpu_temp() == temp_value


@pytest.mark.parametrize("hex_byte,expected", [
    ('0x00\n', 'OK'),
    ('0x80\n', 'Replace'),
    ('0x88\n', 'Replace'),
])
def test_rtc_battery_osf_bit(hex_byte, expected):
    """OSF bit (0x80) determines 'OK' vs 'Replace'; other bits don't affect result."""
    import system_monitor
    r = MagicMock()
    r.returncode = 0
    r.stdout = hex_byte
    with patch('subprocess.run', return_value=r):
        assert system_monitor.get_rtc_battery() == expected


class TestGetMemoryDetail(unittest.TestCase):
    """Tests for get_memory_detail() — virtual memory breakdown in MB."""

    def setUp(self):
        import system_monitor
        self.get_memory_detail = system_monitor.get_memory_detail

    def _make_vmem(self, total, available, used, free):
        m = MagicMock()
        m.total = total
        m.available = available
        m.used = used
        m.free = free
        return m

    def test_returns_all_four_keys(self):
        """Returns dict with memory_total_mb, available_mb, used_mb, free_mb."""
        m = self._make_vmem(1024 ** 2, 1024 ** 2, 1024 ** 2, 1024 ** 2)
        with patch('system_monitor.psutil.virtual_memory', return_value=m):
            result = self.get_memory_detail()
        for key in ('memory_total_mb', 'memory_available_mb', 'memory_used_mb', 'memory_free_mb'):
            self.assertIn(key, result)

    def test_converts_bytes_to_integer_mb(self):
        """Bytes are floor-divided to integer MB."""
        m = self._make_vmem(
            total=1024 * 1024 * 1024,     # 1024 MB
            available=512 * 1024 * 1024,
            used=512 * 1024 * 1024,
            free=256 * 1024 * 1024,
        )
        with patch('system_monitor.psutil.virtual_memory', return_value=m):
            result = self.get_memory_detail()
        self.assertEqual(result['memory_total_mb'], 1024)
        self.assertEqual(result['memory_available_mb'], 512)
        self.assertEqual(result['memory_used_mb'], 512)
        self.assertEqual(result['memory_free_mb'], 256)
        for key in ('memory_total_mb', 'memory_available_mb', 'memory_used_mb', 'memory_free_mb'):
            self.assertIsInstance(result[key], int)


class TestGetSwapDetail(unittest.TestCase):
    """Tests for get_swap_detail() — swap memory breakdown."""

    def setUp(self):
        import system_monitor
        self.get_swap_detail = system_monitor.get_swap_detail

    def _make_swap(self, total, used, free, percent):
        s = MagicMock()
        s.total = total
        s.used = used
        s.free = free
        s.percent = percent
        return s

    def test_returns_all_four_keys(self):
        """Returns dict with swap_percent, total_mb, used_mb, free_mb."""
        s = self._make_swap(0, 0, 0, 0.0)
        with patch('system_monitor.psutil.swap_memory', return_value=s):
            result = self.get_swap_detail()
        for key in ('swap_percent', 'swap_total_mb', 'swap_used_mb', 'swap_free_mb'):
            self.assertIn(key, result)

    def test_converts_bytes_to_integer_mb(self):
        """Bytes are floor-divided to integer MB."""
        s = self._make_swap(
            total=2 * 1024 * 1024 * 1024,  # 2048 MB
            used=256 * 1024 * 1024,
            free=1792 * 1024 * 1024,
            percent=12.5,
        )
        with patch('system_monitor.psutil.swap_memory', return_value=s):
            result = self.get_swap_detail()
        self.assertEqual(result['swap_total_mb'], 2048)
        self.assertEqual(result['swap_used_mb'], 256)
        self.assertEqual(result['swap_free_mb'], 1792)
        for key in ('swap_total_mb', 'swap_used_mb', 'swap_free_mb'):
            self.assertIsInstance(result[key], int)

    def test_percent_rounded_to_one_decimal(self):
        """Swap percent is rounded to 1 decimal place."""
        s = self._make_swap(0, 0, 0, 33.333)
        with patch('system_monitor.psutil.swap_memory', return_value=s):
            result = self.get_swap_detail()
        self.assertEqual(result['swap_percent'], 33.3)


class TestGetDiskUsage(unittest.TestCase):
    """Tests for get_disk_usage() — root filesystem usage."""

    def setUp(self):
        import system_monitor
        self.get_disk_usage = system_monitor.get_disk_usage

    def _make_disk(self, total, used, free, percent):
        d = MagicMock()
        d.total = total
        d.used = used
        d.free = free
        d.percent = percent
        return d

    def test_returns_all_four_keys(self):
        """Returns dict with disk_percent, total_gb, used_gb, free_gb."""
        d = self._make_disk(0, 0, 0, 0.0)
        with patch('system_monitor.psutil.disk_usage', return_value=d):
            result = self.get_disk_usage()
        for key in ('disk_percent', 'disk_total_gb', 'disk_used_gb', 'disk_free_gb'):
            self.assertIn(key, result)

    def test_queries_root_filesystem(self):
        """Always queries '/' as the path."""
        d = self._make_disk(0, 0, 0, 0.0)
        with patch('system_monitor.psutil.disk_usage', return_value=d) as mock_du:
            self.get_disk_usage()
        mock_du.assert_called_once_with('/')

    def test_converts_bytes_to_float_gb(self):
        """Bytes are converted to float GB rounded to 1 decimal."""
        d = self._make_disk(
            total=32 * 1024 ** 3,
            used=16 * 1024 ** 3,
            free=16 * 1024 ** 3,
            percent=50.0,
        )
        with patch('system_monitor.psutil.disk_usage', return_value=d):
            result = self.get_disk_usage()
        self.assertEqual(result['disk_total_gb'], 32.0)
        self.assertEqual(result['disk_used_gb'], 16.0)
        self.assertEqual(result['disk_free_gb'], 16.0)
        for key in ('disk_total_gb', 'disk_used_gb', 'disk_free_gb'):
            self.assertIsInstance(result[key], float)

    def test_percent_comes_from_psutil(self):
        """disk_percent uses the value psutil reports directly."""
        d = self._make_disk(0, 0, 0, 75.5)
        with patch('system_monitor.psutil.disk_usage', return_value=d):
            result = self.get_disk_usage()
        self.assertEqual(result['disk_percent'], 75.5)


class TestGetLoadAverage(unittest.TestCase):
    """Tests for get_load_average() — 1/5/15 minute load averages."""

    def setUp(self):
        import system_monitor
        self.get_load_average = system_monitor.get_load_average

    def test_returns_three_keys(self):
        """Returns dict with load_1m, load_5m, load_15m."""
        with patch('system_monitor.psutil.getloadavg', return_value=(0.5, 0.8, 1.2)):
            result = self.get_load_average()
        for key in ('load_1m', 'load_5m', 'load_15m'):
            self.assertIn(key, result)

    def test_values_match_psutil_output(self):
        """Load values map 1m/5m/15m from psutil tuple in order."""
        with patch('system_monitor.psutil.getloadavg', return_value=(0.5, 0.8, 1.2)):
            result = self.get_load_average()
        self.assertAlmostEqual(result['load_1m'], 0.5, places=2)
        self.assertAlmostEqual(result['load_5m'], 0.8, places=2)
        self.assertAlmostEqual(result['load_15m'], 1.2, places=2)

    def test_values_rounded_to_two_decimal_places(self):
        """Load values are rounded to 2 decimal places."""
        with patch('system_monitor.psutil.getloadavg', return_value=(0.126, 0.654, 1.999)):
            result = self.get_load_average()
        self.assertEqual(result['load_1m'], 0.13)
        self.assertEqual(result['load_5m'], 0.65)
        self.assertEqual(result['load_15m'], 2.0)

    def test_returns_none_when_not_available(self):
        """Returns None when psutil.getloadavg raises AttributeError (Windows)."""
        with patch('system_monitor.psutil.getloadavg', side_effect=AttributeError):
            result = self.get_load_average()
        self.assertIsNone(result)


class TestCollectSystemStateNewFields(unittest.TestCase):
    """Tests that new metric fields are included in collect_system_state()."""

    def setUp(self):
        import system_monitor
        self.collect = system_monitor.collect_system_state

    def _all_patches(self, mem=None, swap=None, disk=None, load=None,
                     sys_time_data=None, rtc_epoch=None, rtc_iso_val=None):
        """Return patches for all helpers; callers override specific return values."""
        default_sys_time = {'sys_time': '2026-01-01T00:00:00+00:00', 'sys_epoch': 1735689600}
        return [
            patch('system_monitor.get_cpu_percent', return_value=10.0),
            patch('system_monitor.get_memory_percent', return_value=50.0),
            patch('system_monitor.get_uptime', return_value='0d 1h 0m'),
            patch('system_monitor.get_cpu_temp', return_value=None),
            patch('system_monitor.get_rtc_time', return_value=None),
            patch('system_monitor.get_rtc_date', return_value=None),
            patch('system_monitor.get_rtc_battery', return_value=None),
            patch('system_monitor.get_memory_detail', return_value=mem or {}),
            patch('system_monitor.get_swap_detail', return_value=swap or {}),
            patch('system_monitor.get_disk_usage', return_value=disk or {}),
            patch('system_monitor.get_load_average', return_value=load),
            patch('system_monitor.get_system_time', return_value=sys_time_data or default_sys_time),
            patch('system_monitor.get_rtc_epoch', return_value=rtc_epoch),
            patch('system_monitor.get_rtc_iso', return_value=rtc_iso_val),
        ]

    def test_memory_detail_fields_merged_into_state(self):
        """Memory breakdown fields from get_memory_detail() appear in the state dict."""
        mock_mem = {'memory_total_mb': 4096, 'memory_available_mb': 2048,
                    'memory_used_mb': 2048, 'memory_free_mb': 1024}
        with ExitStack() as stack:
            for p in self._all_patches(mem=mock_mem):
                stack.enter_context(p)
            state = self.collect()
        self.assertIn('memory_total_mb', state)
        self.assertEqual(state['memory_available_mb'], 2048)

    def test_swap_fields_merged_into_state(self):
        """Swap fields from get_swap_detail() appear in the state dict."""
        mock_swap = {'swap_percent': 5.0, 'swap_total_mb': 1024,
                     'swap_used_mb': 50, 'swap_free_mb': 974}
        with ExitStack() as stack:
            for p in self._all_patches(swap=mock_swap):
                stack.enter_context(p)
            state = self.collect()
        self.assertIn('swap_percent', state)
        self.assertEqual(state['swap_used_mb'], 50)

    def test_disk_fields_merged_into_state(self):
        """Disk fields from get_disk_usage() appear in the state dict."""
        mock_disk = {'disk_percent': 62.5, 'disk_total_gb': 32.0,
                     'disk_used_gb': 20.0, 'disk_free_gb': 12.0}
        with ExitStack() as stack:
            for p in self._all_patches(disk=mock_disk):
                stack.enter_context(p)
            state = self.collect()
        self.assertIn('disk_percent', state)
        self.assertEqual(state['disk_free_gb'], 12.0)

    def test_load_average_merged_when_available(self):
        """Load average fields appear in state when get_load_average() returns a dict."""
        mock_load = {'load_1m': 0.5, 'load_5m': 0.8, 'load_15m': 1.2}
        with ExitStack() as stack:
            for p in self._all_patches(load=mock_load):
                stack.enter_context(p)
            state = self.collect()
        self.assertIn('load_1m', state)
        self.assertEqual(state['load_5m'], 0.8)

    def test_load_average_omitted_when_none(self):
        """Load fields are absent when get_load_average() returns None."""
        with ExitStack() as stack:
            for p in self._all_patches(load=None):
                stack.enter_context(p)
            state = self.collect()
        self.assertNotIn('load_1m', state)
        self.assertNotIn('load_5m', state)
        self.assertNotIn('load_15m', state)


class TestGetSystemTime(unittest.TestCase):
    """Tests for get_system_time() — system clock fields."""

    def setUp(self):
        import system_monitor
        self.get_system_time = system_monitor.get_system_time

    def test_returns_both_keys(self):
        """Returns dict with sys_time and sys_epoch."""
        result = self.get_system_time()
        self.assertIn('sys_time', result)
        self.assertIn('sys_epoch', result)

    def test_sys_epoch_is_int(self):
        """sys_epoch is an integer."""
        result = self.get_system_time()
        self.assertIsInstance(result['sys_epoch'], int)

    def test_sys_epoch_matches_mocked_time(self):
        """sys_epoch equals int(time.time()) at call time."""
        with patch('system_monitor.time.time', return_value=1742930521.9):
            result = self.get_system_time()
        self.assertEqual(result['sys_epoch'], 1742930521)

    def test_sys_time_is_iso8601_utc(self):
        """sys_time is an ISO 8601 UTC string ending with +00:00."""
        result = self.get_system_time()
        self.assertIsInstance(result['sys_time'], str)
        self.assertTrue(result['sys_time'].endswith('+00:00'),
                        f"Expected +00:00 suffix, got: {result['sys_time']}")


class TestGetRtcEpoch(unittest.TestCase):
    """Tests for get_rtc_epoch() — sysfs since_epoch read."""

    def setUp(self):
        import system_monitor
        self.get_rtc_epoch = system_monitor.get_rtc_epoch

    def test_returns_integer_from_sysfs(self):
        """Returns the integer contents of /sys/class/rtc/rtc0/since_epoch."""
        with patch('builtins.open', mock_open(read_data='1742930521\n')):
            result = self.get_rtc_epoch()
        self.assertEqual(result, 1742930521)
        self.assertIsInstance(result, int)

    def test_returns_none_on_file_not_found(self):
        """Returns None when the sysfs file does not exist."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = self.get_rtc_epoch()
        self.assertIsNone(result)

    def test_returns_none_on_permission_error(self):
        """Returns None on PermissionError."""
        with patch('builtins.open', side_effect=PermissionError):
            result = self.get_rtc_epoch()
        self.assertIsNone(result)

    def test_returns_none_on_value_error(self):
        """Returns None when sysfs content cannot be parsed as int."""
        with patch('builtins.open', mock_open(read_data='bad\n')):
            result = self.get_rtc_epoch()
        self.assertIsNone(result)

    def test_returns_none_on_os_error(self):
        """Returns None on generic OSError."""
        with patch('builtins.open', side_effect=OSError("io error")):
            result = self.get_rtc_epoch()
        self.assertIsNone(result)


class TestGetRtcIso(unittest.TestCase):
    """Tests for get_rtc_iso() — combine sysfs date+time into ISO 8601 UTC."""

    def setUp(self):
        import system_monitor
        self.get_rtc_iso = system_monitor.get_rtc_iso

    def test_returns_iso_string_when_both_provided(self):
        """Returns correctly formatted ISO 8601 UTC string when both args are non-None."""
        result = self.get_rtc_iso('2026-03-25', '18:42:01')
        self.assertEqual(result, '2026-03-25T18:42:01+00:00')

    def test_returns_none_when_date_is_none(self):
        """Returns None when rtc_date is None."""
        result = self.get_rtc_iso(None, '18:42:01')
        self.assertIsNone(result)

    def test_returns_none_when_time_is_none(self):
        """Returns None when rtc_time is None."""
        result = self.get_rtc_iso('2026-03-25', None)
        self.assertIsNone(result)

    def test_returns_none_when_both_none(self):
        """Returns None when both args are None."""
        result = self.get_rtc_iso(None, None)
        self.assertIsNone(result)


class TestGetRtcDrift(unittest.TestCase):
    """Tests for get_rtc_drift() — integer second difference between clocks."""

    def setUp(self):
        import system_monitor
        self.get_rtc_drift = system_monitor.get_rtc_drift

    def test_positive_drift_rtc_behind(self):
        """Returns positive when system clock is ahead of RTC (RTC behind)."""
        self.assertEqual(self.get_rtc_drift(100, 99), 1)

    def test_negative_drift_rtc_ahead(self):
        """Returns negative when system clock is behind RTC (RTC ahead)."""
        self.assertEqual(self.get_rtc_drift(99, 100), -1)

    def test_zero_drift_clocks_match(self):
        """Returns 0 when both clocks agree."""
        self.assertEqual(self.get_rtc_drift(100, 100), 0)

    def test_returns_int(self):
        """Return type is int."""
        self.assertIsInstance(self.get_rtc_drift(1742930521, 1742930519), int)


if __name__ == '__main__':
    unittest.main()
