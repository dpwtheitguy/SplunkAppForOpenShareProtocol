# Splunkbase submission

Submit OpenShare as a community app for standalone Splunk Enterprise. The tested releases are Enterprise 9.4.16 and 10.6.1 on Linux. The app requires a separately deployed, customer-managed companion service. The app sends the selected search-result rows and grant changes to that service over the configured private HTTPS endpoint. Recipients use the companion's public HTTPS gateway to read the published snapshot.

- Upload [openshare-0.3.2.spl](../../packages/openshare-0.3.2.spl) and retain its [SHA-256 checksum](../../packages/openshare-0.3.2.spl.sha256).
- Use the [36 × 36 app icon](../../app/openshare/appserver/static/appIcon.png) and [623 × 350 screenshot](listing-screenshot.png).
- Use the [installation guide](../../README.md#install-on-splunk-enterprise) and [GitHub Issues](https://github.com/dpwtheitguy/SplunkAppForOpenShareProtocol/issues) for documentation and issue reporting.
- Select **Apache License Version 2.0** and public download access. Confirm the app ID, support, and listing metadata in the portal. Splunkbase performs its own upload checks and first-release manual review.

The package ID, manifest name, and archive root are all `openshare`. The package explicitly sets `[package] check_for_updates = 1`. Version 0.3.2 includes the Apache 2.0 license and attribution and replaces 0.3.1 for submission. Run `./scripts/check-package.sh` to check the artifact locally. [Splunkbase file standards](https://dev.splunk.com/enterprise/docs/releaseapps/splunkbase/approvalcriteria/)

Local AppInspect precert includes a private-app advisory that recommends disabling update checks for private apps. Keep update checks enabled in the public submission archive. The separate `packaging_standards` scan completed with zero warnings and zero failures.
