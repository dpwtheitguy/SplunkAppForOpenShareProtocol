[companion]
url = <HTTPS URL>
* Base URL of the private companion gateway, reachable from the Splunk server.
* The app appends /private/manage to this URL.

key_file = <absolute path>
* Provision this file with the shared integration key used by the companion.
* The Splunk operating-system user must have read access.

ca_file = <absolute path>
* Optional PEM bundle for the private gateway's certificate issuer.
* Defaults to the system CA store.

allow_http = <boolean>
* Allow a plain HTTP connection only in an isolated test deployment.
* Defaults to false.
