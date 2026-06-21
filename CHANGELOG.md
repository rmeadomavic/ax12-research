# Changelog

All notable changes to **RadioMaster AX12** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository baseline scaffolding (SECURITY.md, ISSUE_TEMPLATE forms, dependabot config, pre-commit hooks).

### Changed
- Reframed all GPS/GNSS references to match the verified hardware reality: the MT6631 GNSS stack runs but no antenna is populated, so the device acquires zero satellites. `gps_tool.py` reads Android network/fused location only. Updated README, DEVELOPER_QUICKSTART, and TEST_VERIFICATION_SHEET accordingly.

### Removed
- `docs/REDDIT_GPS_POST.md` — the "hidden working GPS receiver" draft was based on a misread (WiFi/network position + sats-in-view mistaken for a satellite fix). Removed pending a real solution (external antenna / GPS RX hardware mod).

### Fixed
- Corrected the false "GPS receiver confirmed/working" claim in README and the GPS test in TEST_VERIFICATION_SHEET; they now agree with `docs/hardware/hardware-map.md` (no antenna populated, unusable without a hardware mod).

### Security
- Enabled GitHub Dependabot vulnerability alerts and automated security update PRs.
- Enabled GitHub secret scanning + push protection.

[Unreleased]: https://github.com/rmeadomavic/ax12-research-repo/commits/main
