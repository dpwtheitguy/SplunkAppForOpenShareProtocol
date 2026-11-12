"""Private publisher controls exposed through Splunk Web."""

import configparser
import hashlib
import json
import logging
import re
import secrets
import ssl
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import splunk.rest
from splunk.persistconn.application import PersistentServerConnectionApplication

logger = logging.getLogger("splunk.openshare")


class UserError(Exception):
    pass


def local(path, session, form=None):
    path, _, query = path.partition("?")
    arguments = dict(urllib.parse.parse_qsl(query))
    arguments["output_mode"] = "json"
    response, body = splunk.rest.simpleRequest(
        path,
        sessionKey=session,
        method="POST" if form is not None else "GET",
        postargs=form,
        getargs=arguments,
        raiseAllErrors=True,
    )
    return json.loads(body)


def segment(value):
    return urllib.parse.quote(str(value), safe="")


def list_sources(session):
    indexes = local("/services/data/indexes", session).get("entry", [])
    reports = local("/servicesNS/-/-/saved/searches?count=0", session).get("entry", [])
    return {
        "indexes": [e["name"] for e in indexes if not e["name"].startswith("_")],
        "reports": [
            {"name": e["name"], "owner": e["acl"]["owner"], "app": e["acl"]["app"]}
            for e in reports
            if not e["content"].get("disabled")
        ],
    }


def search_rows(data, session, fields):
    source = data["source"]
    window = data.get("window", "24h")
    if window not in {"1h", "24h", "7d"}:
        raise UserError("Choose a supported time window")
    params = {
        "earliest_time": "-" + window,
        "latest_time": "now",
        "max_time": "120",
        "max_count": "50001",
        "exec_mode": "blocking",
    }
    if data["sourceType"] == "index":
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", source):
            raise UserError("Invalid index name")
        params["search"] = "search index=" + source + " | fields " + " ".join(fields)
        job = local("/services/search/jobs", session, params)
    elif data["sourceType"] == "report":
        namespace = "/servicesNS/{}/{}".format(segment(data["actor"]), segment(data["app"]))
        report = local(namespace + "/saved/searches/" + segment(source), session)["entry"][0]
        if report["acl"]["owner"] != data["reportOwner"]:
            raise UserError("The report owner changed. Select the report again.")
        spl = report["content"]["search"].strip()
        if re.search(r"\$[^$\s]+\$", spl):
            raise UserError("Reports that need runtime inputs are unsupported.")
        params["search"] = spl if re.match(r"^(\||search\s)", spl, re.I) else "search " + spl
        job = local(namespace + "/search/jobs", session, params)
    else:
        raise UserError("Choose an index or saved report")
    job_id = segment(job["sid"])
    path = "/services/search/jobs/" + job_id
    deadline = time.monotonic() + 120
    while True:
        status = local(path, session)["entry"][0]["content"]
        state = status.get("dispatchState")
        if state == "DONE":
            break
        if (
            state in {"FAILED", "INTERNAL_CANCEL", "USER_CANCEL", "BAD_INPUT_CANCEL", "QUIT"}
            or time.monotonic() >= deadline
        ):
            raise UserError("Search did not finish. Review the search job and try again.")
        time.sleep(0.25)
    if status.get("isFailed") in (True, "1", "true") or status.get("isFinalized") in (
        True,
        "1",
        "true",
    ):
        raise UserError("Search returned incomplete results.")
    if int(status.get("resultCount", 0)) > 50000:
        raise UserError("Search exceeded 50,000 rows")
    results = local(path + "/results?count=50001", session).get("results", [])
    if len(results) > 50000 or len(results) != int(status.get("resultCount", 0)):
        raise UserError("Search results exceeded the limit or were incomplete")
    for row in results:
        for field in fields:
            if field in row and not isinstance(row[field], (str, type(None))):
                raise UserError("Select scalar fields. Multivalue fields are unsupported.")
    return [{field: row.get(field) for field in fields} for row in results]


def backend(data):
    config = configparser.ConfigParser(interpolation=None)
    config_path = Path(__file__).resolve().parent.parent / "local/openshare.conf"
    try:
        config.read(config_path, encoding="utf-8")
        settings = config["companion"]
        url = settings["url"].strip().rstrip("/")
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme == "http" and not settings.getboolean("allow_http", fallback=False))
        ):
            raise ValueError("Invalid companion URL")
        integration_key = Path(settings["key_file"].strip()).read_text(encoding="utf-8").strip()
        if len(integration_key) < 32:
            raise ValueError("Integration key is too short")
        cafile = settings.get("ca_file", "").strip() or None
        tls = ssl.create_default_context(cafile=cafile) if parsed.scheme == "https" else None
    except (OSError, ValueError, KeyError, configparser.Error):
        raise UserError(
            "Configure the companion URL and integration key file in local/openshare.conf. See the installation guide."
        ) from None
    request = urllib.request.Request(  # noqa: S310 - scheme is validated above.
        url + "/private/manage",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-OpenShare-Key": integration_key},
    )
    handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
    if tls:
        handlers.append(urllib.request.HTTPSHandler(context=tls))
    with urllib.request.build_opener(*handlers).open(request, timeout=130) as response:
        return json.load(response)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        return None


class OpenShareHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line, command_arguments):
        super().__init__()

    def handle(self, request):
        try:
            incoming = json.loads(request)
            session = incoming["session"]["authtoken"]
            context = local("/services/authentication/current-context", session)["entry"][0][
                "content"
            ]
            actor = context["username"]
            admin = "admin" in context.get("roles", [])
            if not admin and "openshare_publish" not in context.get("capabilities", []):
                return self.reply(403, {"detail": "OpenShare publisher access is required"})
            payload = incoming.get("payload") or ""
            if payload.startswith("{"):
                data = json.loads(payload)
            else:
                form = dict(incoming.get("form") or [])
                form.update(dict(urllib.parse.parse_qsl(payload)))
                data = json.loads(form["request"])
            data.update(actor=actor, admin=admin)
            action = data["action"]
            if action == "sources":
                return self.reply(200, list_sources(session))
            if action in ("stage", "stage_refresh"):
                if action == "stage_refresh":
                    target = data["snapshot"]
                    source = backend(
                        {
                            "action": "refresh_source",
                            "actor": actor,
                            "admin": admin,
                            "snapshot": target,
                        }
                    )
                    data = {
                        **source,
                        "action": "stage",
                        "actor": actor,
                        "admin": admin,
                        "replacement_for": target,
                    }
                else:
                    data.pop("replacement_for", None)
                    data.pop("base_version", None)
                fields = data["fields"]
                if (
                    not fields
                    or len(fields) > 100
                    or len(fields) != len(set(fields))
                    or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", field) for field in fields)
                ):
                    raise UserError("Enter up to 100 distinct scalar field names")
                if not data.get("name", "").strip() or len(data["name"]) > 100:
                    raise UserError("Enter a share name of up to 100 characters")
                data["rows"] = search_rows(data, session, fields)
            if action in ("issue", "rotate"):
                token = secrets.token_urlsafe(32)
                data["verifier"] = hashlib.sha256(token.encode()).hexdigest()
                profile = backend(data)
                profile["bearerToken"] = token
                return self.reply(200, profile)
            result = backend(data)
            if action == "list":
                result["admin"] = admin
            return self.reply(200, result)
        except UserError as error:
            return self.reply(400, {"detail": str(error)})
        except splunk.AuthorizationFailed:
            return self.reply(
                403, {"detail": "Your Splunk role cannot access this source or run its search."}
            )
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error).get("detail", "Request failed")
            except ValueError:
                detail = "Request failed"
            return self.reply(error.code, {"detail": detail})
        except Exception as error:
            frames = traceback.extract_tb(error.__traceback__)
            logger.warning(
                "OpenShare request failed error_type=%s frames=%s",
                type(error).__name__,
                " ".join(f"{frame.name}:{frame.lineno}" for frame in frames),
            )
            return self.reply(
                500,
                {
                    "detail": "OpenShare could not complete the request. Review the private service and Splunk logs."
                },
            )

    @staticmethod
    def reply(status, result):
        return {
            "status": status,
            "payload": json.dumps(result),
            "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        }
