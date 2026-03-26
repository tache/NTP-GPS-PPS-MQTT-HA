# Security Policy

## Reporting a Vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Use GitHub's **[private vulnerability reporting](../../security/advisories/new)** to report
issues confidentially. This allows the vulnerability to be assessed and patched before
any public disclosure.

Include as much detail as possible: affected script(s), steps to reproduce, and potential impact.

## Scope

This project consists of Python scripts that run on a Raspberry Pi and publish
sensor data to a local MQTT broker. The relevant attack surfaces are:

- MQTT credentials and TLS configuration (`*_monitor.conf`)
- GPSD socket input parsing (`gpsd_monitor.py`)
- subprocess calls to `ntpq` and `i2cget` (`ntpd_monitor.py`, `system_monitor.py`)

Credential files (`*_monitor.conf`) must be `chmod 600` and owned by the service user.
See the `.conf.example` files for the recommended configuration.
