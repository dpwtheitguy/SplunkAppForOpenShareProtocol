OpenShare for Splunk Enterprise
App ID openshare

OpenShare publishes read-only OpenSharing snapshots of selected Splunk indexes
and saved reports. This package has been tested on standalone Splunk Enterprise
9.4.16 and 10.6.1 on Linux using bundled Python 3.9 and 3.13. The app needs no
third-party Python packages. Deploy the separate companion service to
materialize and serve snapshots. Splunk Cloud Platform has not been validated.

Install the .spl in Splunk Web under Apps > Manage Apps > Install app from file.
Configure $SPLUNK_HOME/etc/apps/openshare/local/openshare.conf using the
specification under README/. Provision the shared integration key in a protected
file readable by the Splunk service account. Configure the private companion URL
and CA before opening the app. The app sends selected result rows and grant
changes to the configured companion.

Grant openshare_publish to a Splunk search role and grant access to the intended
indexes or saved reports. In OpenShare, create a share, choose fields, preview
the snapshot, publish, and generate an expiring recipient profile. Copy the
network guide for firewall and load balancer configuration. Recipients read
using a standard OpenSharing client and their downloaded profile. The
companion can export OCSF 1.7.0 API Activity audit events as JSON lines.

If the app cannot load, check the companion URL, certificate trust, integration
key permissions, and service availability. If a recipient receives HTTP 401,
check that the share is enabled and the token is current.

Setup, deployment, and support:
https://github.com/dpwtheitguy/SplunkAppForOpenShareProtocol
https://github.com/dpwtheitguy/SplunkAppForOpenShareProtocol/issues
