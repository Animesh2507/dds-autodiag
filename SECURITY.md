# Security policy

## Reporting a vulnerability

Please report security issues **privately** via GitHub: **Security → Report a vulnerability** on this repository
(<https://github.com/Animesh2507/dds-autodiag/security/advisories/new>). Don't open a public issue.

Include what you found, how to reproduce it, and the affected version (`dds-autodiag --version`). You'll get a reply
within a week; fixes are released as soon as possible and credited if you wish.

## Supported versions

Until 1.0, only the latest release receives security fixes.

## Scope

DDS AutoDiag runs local commands and can hold AI provider keys, so these are especially relevant:

- bypassing the Host-header, Origin or token checks of the dashboard and API;
- reading stored API keys or making them reach the browser or logs;
- making AutoDiag run commands other than its read-only probes, or change the ROS / DDS configuration;
- sending snapshot data, hostnames or IPs to cloud AI providers.

The design is described in the [security model](docs/concepts/security.md).
