# Available Variables Reference

Complete reference of all fields available from GPSD, NTPd, psutil, and the DS3231 RTC module.
Fields marked **Yes** in the "Used" column are currently published to MQTT.

---

## GPSD (TCP port 2947, JSON stream, protocol 16.1)

> **GPSD 3.27 breaking change:** SKY messages can arrive in two forms — DOP-only
> (no `satellites` array) and full (with `satellites[]`). Code must check for the
> presence of `satellites` before processing the array to avoid blanking the list.
> TOFF messages require `"pps":true` in the WATCH command.

### TPV — Time-Position-Velocity

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `class` | string | Always `"TPV"` | - |
| `device` | string | Device path (e.g. `/dev/ttyAMA0`) | |
| `mode` | int | Fix type: 0/1=none, 2=2D, 3=3D — published as string `fix` via `FIX_MODES` | Yes¹ |
| `time` | string | ISO 8601 timestamp from GPS — sub-seconds stripped, `Z` suffix kept | Yes |
| `ept` | float | Estimated time error (seconds) | Yes |
| `lat` | float | Latitude (degrees, 6 dp) | Yes |
| `lon` | float | Longitude (degrees, 6 dp) | Yes |
| `alt` | float | Altitude (meters MSL, 2 dp) | Yes |
| `altHAE` | float | Altitude (meters HAE — WGS84 ellipsoid, 2 dp) — published as `alt_hae` | Yes |
| `epx` | float | Longitude error estimate (meters) | |
| `epy` | float | Latitude error estimate (meters) | |
| `epv` | float | Altitude error estimate (meters) | |
| `speed` | float | Speed over ground (m/s, 6 dp) | Yes |
| `climb` | float | Vertical speed (m/s, 6 dp) | Yes |
| `track` | float | Course over ground (degrees from true north, 6 dp) | Yes |
| `magtrack` | float | Course (degrees from magnetic north, 6 dp) | Yes |
| `magvar` | float | Magnetic variation (degrees) | |
| `eps` | float | Speed error estimate (m/s) | |
| `epc` | float | Climb error estimate (m/s) | |
| `ecefx` | float | ECEF X position (meters) | |
| `ecefy` | float | ECEF Y position (meters) | |
| `ecefz` | float | ECEF Z position (meters) | |
| `ecefvx` | float | ECEF X velocity (m/s) | |
| `ecefvy` | float | ECEF Y velocity (m/s) | |
| `ecefvz` | float | ECEF Z velocity (m/s) | |
| `sep` | float | Spherical error (3D, meters, 2 dp) | Yes |
| `eph` | float | Estimated horizontal position error (meters, 2 dp, GPSD 3.20+) | Yes |
| `geoidSep` | float | Geoid separation: WGS84 ellipsoid minus MSL (meters, 2 dp) — published as `geoid_sep` | Yes |
| `status` | int | Fix status: 0=unknown, 1=normal, 2=DGPS, etc. | |
| `leapseconds` | int | Current leap second count | |
| `vel_e` | float | East velocity component (m/s, GPSD 3.20+) | |
| `vel_n` | float | North velocity component (m/s, GPSD 3.20+) | |
| `vel_d` | float | Down velocity component (m/s, GPSD 3.20+) | |
| `last_error` | string | *(computed)* Most recent GPSD ERROR message, capped to 256 chars; default `"ok"` | Yes |

> ¹ Raw `mode` integer is not published. It is mapped via `FIX_MODES` to a string: 0/1 → `"No Fix"`, 2 → `"2D Fix"`, 3 → `"3D Fix"`, published as `fix`.

> **Note:** `altHAE`/`altMSL` distinction, `eph`, `geoidSep`, and NED velocity fields
> became available in GPSD 3.20+. ECEF fields require receivers that output GST sentences.
> The MTK-3301 receiver reliably provides: `mode`, `time`, `lat`, `lon`, `alt`, `altHAE`,
> `altMSL`, `speed`, `track`, `climb`, `epx`, `epy`, `epv`, `ept`, `eps`, `epc`, `eph`,
> `sep`, `geoidSep`, `magtrack`, `magvar`.

### SKY — Satellite View

> **GPSD 3.27+:** SKY messages alternate between two forms: DOP-only messages
> (containing DOPs and `uSat`/`nSat` but no `satellites` array) and full messages
> (containing both DOPs and the `satellites[]` array). Both forms update DOPs,
> but only full messages should update the satellite list.

#### Top-level fields

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `class` | string | Always `"SKY"` | - |
| `device` | string | Device path | |
| `hdop` | float | Horizontal dilution of precision | Yes |
| `vdop` | float | Vertical dilution of precision | Yes |
| `pdop` | float | Position (3D) dilution of precision | Yes |
| `tdop` | float | Time dilution of precision | Yes |
| `gdop` | float | Geometric dilution of precision | Yes |
| `xdop` | float | Longitudinal DOP | Yes |
| `ydop` | float | Latitudinal DOP | Yes |
| `nSat` | int | Satellites visible (GPSD 3.22+) | Yes |
| `uSat` | int | Satellites used (GPSD 3.22+) | Yes |

#### Per-satellite fields (in `satellites[]`)

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `PRN` | int | Satellite PRN/ID number | Yes |
| `el` | float | Elevation (degrees, 0-90) | Yes |
| `az` | float | Azimuth (degrees, 0-359) | Yes |
| `ss` | float | Signal strength/SNR (dB-Hz) | Yes |
| `used` | bool | Used in current fix | Yes |
| `seen` | int | *(computed)* Seconds since this PRN was first observed in the current session | Yes |
| `gnssid` | int | GNSS system ID (0=GPS, 1=SBAS, 2=Galileo, 3=BeiDou, 5=QZSS, 6=GLONASS, 7=NavIC) | Yes |
| `svid` | int | Satellite vehicle ID within constellation | Yes |
| `sigid` | int | Signal/frequency ID | |
| `freqid` | int | GLONASS frequency slot | |
| `health` | int | Satellite health status | |

> **Note:** With GPSD 3.27.5, the MTK-3301 now provides `gnssid` and `svid` per satellite.
> Observed values: `gnssid=0` (GPS) for standard satellites, `gnssid=1` (SBAS) for
> augmentation satellites (e.g. PRN 34 / svid 121). `sigid`, `freqid`, and `health`
> require multi-constellation receivers.

### VERSION

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `release` | string | GPSD version string (e.g. `"3.27.5"`) | Yes |
| `rev` | string | Internal revision | |
| `proto_major` | int | Protocol major version — combined with `proto_minor` into `proto` (e.g. `"16.1"`) | Yes² |
| `proto_minor` | int | Protocol minor version — combined with `proto_major` into `proto` (e.g. `"16.1"`) | Yes² |

> ² `proto_major` and `proto_minor` are not published individually. They are combined into a single `proto` string: `f"{proto_major}.{proto_minor}"` (e.g. `"16.1"`).

### PPS — Pulse Per Second

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `device` | string | Device path | |
| `real_sec` | int | GPS PPS seconds (epoch) | Yes |
| `real_nsec` | int | GPS PPS nanoseconds | Yes |
| `clock_sec` | int | System clock seconds (epoch) | Yes |
| `clock_nsec` | int | System clock nanoseconds | Yes |
| `precision` | int | PPS precision (nanoseconds, optional) | Yes |
| `shm` | string | Shared memory segment name (optional) | Yes |
| `offset_ns` | int | *(computed)* `(real_sec - clock_sec) * 1_000_000_000 + (real_nsec - clock_nsec)` | Yes |

> All raw fields plus `offset_ns` are published to `gps_monitor/pps`.
> `precision` and `shm` are included only when present in the GPSD message.

### TOFF — Time Offset

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `device` | string | Device path | |
| `real_sec` | int | GPS time seconds (epoch) | Yes |
| `real_nsec` | int | GPS time nanoseconds | Yes |
| `clock_sec` | int | System clock seconds (epoch) | Yes |
| `clock_nsec` | int | System clock nanoseconds | Yes |
| `precision` | int | TOFF precision (nanoseconds, optional) | Yes |
| `shm` | string | Shared memory segment name (optional) | Yes |
| `offset_ns` | int | *(computed)* `(real_sec - clock_sec) * 1_000_000_000 + (real_nsec - clock_nsec)` | Yes |

> All raw fields plus `offset_ns` are published to `gps_monitor/toff`.
> `precision` and `shm` are included only when present in the GPSD message.
> **Requires** `"pps":true` in the WATCH command (`?WATCH={"enable":true,"json":true,"pps":true}`) — this single flag enables both TOFF and PPS messages. The `timing` and `toff` flags are undocumented developer-only options; do not use them.

### ERROR

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `message` | string | Error description from GPSD | Yes |

> Published as `last_error` — most recent error string.

### Other GPSD message classes (not used)

| Class | Description |
|-------|-------------|
| `DEVICES` | List of connected GPS devices |
| `WATCH` | Echo of watch settings |
| `ATT` | Attitude (heading/pitch/roll — compass-equipped receivers) |
| `GST` | Pseudorange noise report (error statistics per satellite) |

---

## NTPd (`ntpq -c rv` system variables)

| Field | Type | Description | Used |
|-------|------|-------------|:----:|
| `associd` | int | Association ID (0 = system) | |
| `status` | hex | System status word | |
| `version` | string | NTPd version string | Yes |
| `processor` | string | CPU architecture | |
| `system` | string | OS name | |
| `leap` | int | Leap indicator (0=none, 1=add, 2=del, 3=unsync) | Yes |
| `stratum` | int | Stratum level (1=GPS/PPS reference) | Yes |
| `precision` | int | Clock precision (log2 seconds) | Yes |
| `rootdelay` | float | Total round-trip delay to reference (ms) | |
| `rootdisp` | float | Total root dispersion (ms) | |
| `refid` | string | Reference clock ID (e.g. `GPS`, `PPS`, `.INIT.`) | Yes |
| `reftime` | string | Last time the reference clock was updated (hex + readable) | |
| `clock` | string | Current NTPd system clock (hex + readable) | Yes |
| `peer` | int | Association ID of current sync source | |
| `tc` | int | Time constant / poll exponent | |
| `mintc` | int | Minimum time constant | |
| `offset` | float | Current clock offset from reference (ms) | Yes |
| `frequency` | float | Clock frequency offset (PPM) | Yes |
| `sys_jitter` | float | System jitter — RMS of offset differences (ms) | Yes |
| `clk_jitter` | float | Clock jitter — RMS of clock reading noise (ms) | Yes |
| `clk_wander` | float | Clock frequency wander (PPM) | Yes |
| `tai` | int | TAI-UTC offset (leap seconds count) | |
| `expire` | string | Leap second schedule expiration | |
| `ntp_synced` | string | *(derived)* `"Yes"` when `leap` ≠ 3, `"No"` when `leap` = 3, `"Unknown"` on parse error | Yes |

> `ntp_synced` is not a raw ntpq field — it is derived from the `leap` value and always published.

---

## psutil — System Health

### Published to `system_monitor/state`

All fields below are published as JSON to the `system_monitor/state` MQTT topic.
Fields marked with \* are omitted from the payload (not published as null) when
the underlying source is unavailable.

| Field | Type | Description |
|-------|------|-------------|
| `sys_time` | string | System (NTP-synced) clock as ISO 8601 UTC, e.g. `"2026-03-25T18:42:01+00:00"` |
| `sys_epoch` | int | System clock as Unix epoch seconds |
| `cpu_percent` | float | CPU usage % (1-second average, 1 dp) |
| `cpu_temp` | float | CPU temperature in °C (1 dp). \* |
| `memory_percent` | float | RAM usage % (1 dp) |
| `memory_total_mb` | int | Total RAM in MB |
| `memory_available_mb` | int | Available RAM in MB (includes reclaimable cache) |
| `memory_used_mb` | int | Used RAM in MB |
| `memory_free_mb` | int | Free RAM in MB |
| `swap_percent` | float | Swap usage % (1 dp) |
| `swap_total_mb` | int | Total swap in MB |
| `swap_used_mb` | int | Used swap in MB |
| `swap_free_mb` | int | Free swap in MB |
| `disk_percent` | float | Root filesystem usage % |
| `disk_total_gb` | float | Root filesystem total in GB (1 dp) |
| `disk_used_gb` | float | Root filesystem used in GB (1 dp) |
| `disk_free_gb` | float | Root filesystem free in GB (1 dp) |
| `load_1m` | float | 1-minute load average (2 dp). \* |
| `load_5m` | float | 5-minute load average (2 dp). \* |
| `load_15m` | float | 15-minute load average (2 dp). \* |
| `uptime` | string | System uptime formatted as `"Xd Yh Zm"` |
| `rtc_time` | string | RTC time from sysfs, e.g. `"18:42:01"`. \* |
| `rtc_date` | string | RTC date from sysfs, e.g. `"2026-03-25"`. \* |
| `rtc_battery` | string | DS3231 oscillator status: `"OK"` or `"Replace"`. \* |
| `rtc_epoch` | int | RTC time as Unix epoch seconds (from `/sys/class/rtc/rtc0/since_epoch`). \* |
| `rtc_iso` | string | RTC time as ISO 8601 UTC, e.g. `"2026-03-25T18:42:01+00:00"`. \* |
| `rtc_drift` | int | System epoch minus RTC epoch in seconds. Positive = RTC behind. \* |

> \* Omitted from the payload (not published as null) when the underlying source is
> unavailable (RTC not present, load averages unsupported, temperature sensor absent).
> `rtc_epoch`, `rtc_iso`, and `rtc_drift` are omitted together if either RTC epoch or
> RTC ISO is unavailable.

### CPU

| Function | Returns | Used |
|----------|---------|:----:|
| `cpu_percent(interval=1)` | Overall CPU usage % | Yes |
| `cpu_percent(percpu=True)` | Per-core usage % list | |
| `cpu_count(logical=True)` | Logical core count | |
| `cpu_count(logical=False)` | Physical core count | |
| `cpu_freq()` | Current/min/max MHz | |
| `cpu_times()` | user, system, idle, iowait, etc. (seconds) | |
| `cpu_stats()` | ctx_switches, interrupts, soft_interrupts, syscalls | |
| `getloadavg()` | 1/5/15 min load averages | Yes |

### Temperature

| Function | Returns | Used |
|----------|---------|:----:|
| `sensors_temperatures()` | Dict of temp sensors — current, high, critical (°C) | Yes |
| `sensors_temperatures()['cpu_thermal']` | RPi CPU temp specifically | |

### Memory

| Function | Returns | Used |
|----------|---------|:----:|
| `virtual_memory().percent` | RAM usage % | Yes |
| `virtual_memory().total` | Total RAM (bytes) → published as `memory_total_mb` | Yes |
| `virtual_memory().available` | Available RAM (bytes) → published as `memory_available_mb` | Yes |
| `virtual_memory().used` | Used RAM (bytes) → published as `memory_used_mb` | Yes |
| `virtual_memory().free` | Free RAM (bytes) → published as `memory_free_mb` | Yes |
| `virtual_memory().buffers` | Buffer cache (bytes, Linux) | |
| `virtual_memory().cached` | Page cache (bytes, Linux) | |
| `swap_memory().percent` | Swap usage % → published as `swap_percent` | Yes |
| `swap_memory().total` | Total swap (bytes) → published as `swap_total_mb` | Yes |
| `swap_memory().used` | Used swap (bytes) → published as `swap_used_mb` | Yes |
| `swap_memory().free` | Free swap (bytes) → published as `swap_free_mb` | Yes |
| `swap_memory().sin` | Bytes swapped in (cumulative) | |
| `swap_memory().sout` | Bytes swapped out (cumulative) | |

> All memory and swap byte values are floor-divided to integer MB before publishing.

### Disk

| Function | Returns | Used |
|----------|---------|:----:|
| `disk_usage('/').percent` | Root filesystem usage % → published as `disk_percent` | Yes |
| `disk_usage('/').total` | Root filesystem total (bytes) → published as `disk_total_gb` (float GB, 1 dp) | Yes |
| `disk_usage('/').used` | Root filesystem used (bytes) → published as `disk_used_gb` (float GB, 1 dp) | Yes |
| `disk_usage('/').free` | Root filesystem free (bytes) → published as `disk_free_gb` (float GB, 1 dp) | Yes |
| `disk_partitions()` | List of mounted partitions (device, mountpoint, fstype) | |
| `disk_io_counters()` | read_count, write_count, read_bytes, write_bytes, read_time, write_time | |
| `disk_io_counters(perdisk=True)` | Same but per-device (mmcblk0, etc.) | |

> Disk byte values are divided to float GB (rounded to 1 decimal) before publishing.

### Network

| Function | Returns | Used |
|----------|---------|:----:|
| `net_io_counters()` | bytes_sent, bytes_recv, packets_sent, packets_recv, errin, errout, dropin, dropout | |
| `net_io_counters(pernic=True)` | Same but per-interface (eth0, wlan0, etc.) | |
| `net_if_addrs()` | IP/MAC addresses per interface | |
| `net_if_stats()` | isup, duplex, speed, mtu per interface | |
| `net_connections()` | Active connections (local/remote addr, status, pid) | |

### Uptime / Boot

| Function | Returns | Used |
|----------|---------|:----:|
| `boot_time()` | Used to compute published field `uptime` (formatted string `"Xd Yh Zm"`). Raw epoch is not published. | Yes |

### Processes

| Function | Returns | Used |
|----------|---------|:----:|
| `pids()` | List of all PIDs | |
| `process_iter()` | Iterator over all processes (name, cpu%, mem%, etc.) | |
| `pid_exists(pid)` | Check if a PID is running | |
| `Process(pid).name()` | Process name | |
| `Process(pid).cpu_percent()` | Per-process CPU % | |
| `Process(pid).memory_info()` | RSS, VMS, shared, etc. | |
| `Process(pid).status()` | running, sleeping, zombie, etc. | |

### Fans (Linux)

| Function | Returns | Used |
|----------|---------|:----:|
| `sensors_fans()` | Dict of fan sensors — label, current RPM | |

### Battery

| Function | Returns | Used |
|----------|---------|:----:|
| `sensors_battery()` | percent, secsleft, power_plugged | |

---

## DS3231 RTC Module (I2C address `0x68`)

### Available Data

| Data | Access Method | Notes | Used |
|------|---------------|-------|:----:|
| RTC Time | `/sys/class/rtc/rtc0/time` | Hardware clock time | Yes |
| RTC Date | `/sys/class/rtc/rtc0/date` | Hardware clock date | Yes |
| Epoch | `/sys/class/rtc/rtc0/since_epoch` | RTC time as Unix timestamp → published as `rtc_epoch` | Yes |
| Temperature | I2C registers `0x11`-`0x12` | Built-in temp sensor, 0.25°C resolution | |
| Aging Offset | I2C register `0x10` | Crystal oscillator compensation value | |
| Oscillator Status | I2C register `0x0F` bit 7 (OSF) | Set if oscillator stopped (battery issue) | Yes |
| ISO Time | *(computed)* | RTC date + time combined as ISO 8601 UTC string → published as `rtc_iso` | Yes |
| Clock Drift | *(computed)* | System epoch minus RTC epoch (seconds); positive = RTC behind → published as `rtc_drift` | Yes |
| Battery Status | I2C register `0x0E` (control) | BBSQW / EOSC bits | |
| Alarm 1 & 2 | I2C registers `0x07`-`0x0D` | Programmable alarm times | |

> The oscillator status (OSF bit) is published as `rtc_battery` — reports `"OK"` or
> `"Replace"` based on whether the oscillator has stopped at any point.

### Python Access Examples

**RTC Time/Date** — via sysfs (no special packages needed):

```python
time = open('/sys/class/rtc/rtc0/time').read().strip()
date = open('/sys/class/rtc/rtc0/date').read().strip()
```

**Temperature** — via I2C (`smbus2` package):

```python
import smbus2
bus = smbus2.SMBus(1)
msb = bus.read_byte_data(0x68, 0x11)
lsb = bus.read_byte_data(0x68, 0x12)
temp = msb + ((lsb >> 6) * 0.25)
```

**Aging Offset** — via I2C:

```python
aging = bus.read_byte_data(0x68, 0x10)
if aging > 127:
    aging -= 256  # signed byte: positive = slower, negative = faster
```

**Oscillator Status** — via `i2cget`:

```python
import subprocess
result = subprocess.run(['i2cget', '-y', '1', '0x68', '0x0f'],
                        capture_output=True, text=True, timeout=5)
status = int(result.stdout.strip(), 16)
osf = bool(status & 0x80)  # True = oscillator stopped (battery dead/removed)
```
