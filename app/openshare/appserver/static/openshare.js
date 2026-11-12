require(["jquery", "splunkjs/mvc/simplexml/ready!"], function ($) {
    "use strict";
    const root = document.getElementById("openshare");
    const appRoute = window.location.pathname.lastIndexOf("/app/");
    const webPrefix = appRoute < 0 ? "" : window.location.pathname.slice(0, appRoute);
    const endpoint = webPrefix + "/splunkd/__raw/services/openshare/manage";
    let view = "Shares";

    function node(tag, content, parent) {
        const element = document.createElement(tag);
        if (content !== undefined) element.textContent = content;
        if (parent) parent.append(element);
        return element;
    }

    function button(text, action, parent, primary = false) {
        const element = node("button", text, parent);
        element.type = "button";
        element.className = primary ? "btn btn-primary" : "btn";
        element.onclick = async () => {
            element.disabled = true;
            try { await action(); } catch (error) { notice(error.message, true); }
            finally { element.disabled = false; }
        };
        return element;
    }

    function notice(text, error = false) {
        const message = root.querySelector(".os-message");
        message.textContent = text;
        message.dataset.error = String(error);
    }

    function api(action, params = {}) {
        return new Promise((resolve, reject) => {
            $.ajax({
                url: endpoint, method: "POST", dataType: "json",
                headers: {"X-Splunk-Form-Key": (document.cookie.match(/(?:^|; )splunkweb_csrf_token_\d+=([^;]+)/) || [])[1] || ""},
                data: {request: JSON.stringify({action, ...params})},
            }).done(resolve).fail((xhr) => reject(new Error(
                xhr.responseJSON?.detail || "OpenShare request failed (" + xhr.status + ")."
            )));
        });
    }

    function table(headings, rows, parent) {
        const wrapper = node("div", undefined, parent);
        wrapper.className = "os-table-scroll";
        const grid = node("table", undefined, wrapper);
        grid.className = "os-table";
        const header = node("tr", undefined, node("thead", undefined, grid));
        headings.forEach((heading) => { node("th", heading, header).scope = "col"; });
        const body = node("tbody", undefined, grid);
        rows.forEach((row) => {
            const line = node("tr", undefined, body);
            row.forEach((value) => {
                const cell = node("td", undefined, line);
                if (value instanceof Node) cell.append(value);
                else cell.textContent = value ?? "—";
            });
        });
        return grid;
    }

    function input(label, type, parent, value = "") {
        const wrapper = node("label", label, parent);
        const field = node("input", undefined, wrapper);
        field.setAttribute("aria-label", label);
        field.type = type;
        field.value = value;
        return field;
    }

    function select(label, options, parent) {
        const field = node("select", undefined, node("label", label, parent));
        field.setAttribute("aria-label", label);
        options.forEach(([key, title]) => {
            node("option", title, field).value = key;
        });
        return field;
    }

    const date = (seconds) => seconds ? new Date(seconds * 1000).toLocaleString() : "—";

    function intro(parent, title, description) {
        const heading = node("header", undefined, parent);
        heading.className = "os-heading";
        const text = node("div", undefined, heading);
        node("h2", title, text);
        node("p", description, text);
        return heading;
    }

    function status(label, tone) {
        const element = node("span", label);
        element.className = "os-status";
        element.dataset.tone = tone;
        return element;
    }

    function empty(parent, title, detail) {
        const panel = node("div", undefined, parent);
        panel.className = "os-empty";
        node("h3", title, panel);
        node("p", detail, panel);
    }

    async function create(parent) {
        parent.replaceChildren();
        intro(parent, "Create share", "Select a source and preview the exact columns and rows you’ll publish.");
        const sources = await api("sources");
        const form = node("div", undefined, parent);
        form.className = "os-fields";
        const type = select("Source type", [["index", "Index"], ["report", "Saved report"]], form);
        const sourcesBox = node("div", undefined, form);
        let source;
        function sourceOptions() {
            sourcesBox.replaceChildren();
            const options = type.value === "index"
                ? sources.indexes.map((name) => [name, name])
                : sources.reports.map((report, i) => [i, report.name + " (" + report.app + " / " + report.owner + ")"]);
            source = select("Source", [["", "Choose a source"], ...options], sourcesBox);
        }
        type.onchange = sourceOptions;
        sourceOptions();
        const name = input("Share name", "text", form);
        const fields = input("Fields (comma-separated)", "text", form);
        fields.placeholder = "service, error_count";
        const window = select("Search window", [["1h", "Last hour"], ["24h", "Last 24 hours"], ["7d", "Last 7 days"]], form);
        window.value = "24h";
        const actions = node("div", undefined, parent);
        actions.className = "os-actions";
        const preview = node("section", undefined, parent);
        preview.className = "os-preview";
        let revision = 0;
        form.addEventListener("input", () => {
            revision += 1;
            preview.replaceChildren();
        });
        button("Preview snapshot", async () => {
            if (!source.value) throw new Error("Choose a source.");
            const report = type.value === "report" ? sources.reports[Number(source.value)] : null;
            const requestedRevision = revision;
            notice("Preparing a snapshot…");
            preview.replaceChildren();
            const draft = await api("stage", {
                sourceType: type.value, source: report ? report.name : source.value,
                reportOwner: report?.owner, app: report?.app, name: name.value.trim(),
                fields: fields.value.split(",").map((field) => field.trim()).filter(Boolean),
                window: window.value,
            });
            notice("");
            if (requestedRevision === revision) review(preview, draft);
        }, actions, true);
        button("Cancel", render, actions);
    }

    function review(panel, draft, replacement = false) {
        node("h3", "Review snapshot", panel);
        node("p", draft.name + " · " + draft.rows + " rows · " + draft.fields.length + " columns · Showing up to 10 rows", panel);
        table(draft.fields, draft.sample.map((row) => draft.fields.map((field) => row[field])), panel);
        button(replacement ? "Publish replacement" : "Publish snapshot", async () => {
            await api("publish", {snapshot: draft.id});
            await render(replacement ? null : draft.id);
            notice(replacement ? "Snapshot refreshed." : "Snapshot published.");
        }, panel, true);
    }

    function networkGuide(parent, endpointUrl, share = null, dismiss = null) {
        const url = new URL(endpointUrl);
        const base = url.pathname.replace(/\/$/, "");
        const sharePath = base + "/shares/" + (share ? encodeURIComponent(share.id) : "{share}");
        const schemaPath = sharePath + "/schemas/" + (share ? "data" : "{schema}");
        const tablePath = schemaPath + "/tables/" + (share ? "snapshot" : "{table}");
        const routes = [
            ["GET", base + "/shares"],
            ["GET", sharePath],
            ["GET", sharePath + "/schemas"],
            ["GET", sharePath + "/all-tables"],
            ["GET", schemaPath + "/tables"],
            ["GET, HEAD", tablePath],
            ["GET", tablePath + "/metadata"],
            ["GET", tablePath + "/version"],
            ["POST", tablePath + "/query"],
            ["GET, HEAD", base + "/files/{snapshot}/{grant}/{expiry}/{signature}"],
        ];
        const destination = url.hostname + " on TCP " + (url.port || "443");
        const probe = "curl -i '" + url.origin + base + "/shares'";
        const guide = node("section", undefined, parent);
        guide.className = "os-network-guide";
        const heading = intro(guide, "Firewall and load balancer guide", share
            ? "Network handoff for " + share.name
            : "Network handoff for the shared OpenShare listener.");
        const actions = node("div", undefined, heading);
        actions.className = "os-actions";
        const steps = [
            ["Firewall", "Allow outbound HTTPS from the agreed recipient source IPs or CIDRs to " + destination + "."],
            ["Load balancer", "Route the methods and paths below to the OpenShare recipient listener. Preserve the Authorization header and byte-range requests. Keep all other routes private, including Splunk Web, the Splunk management API, and publishing routes."],
            ["DNS and TLS", "Resolve " + url.hostname + " to the recipient-facing load balancer or gateway. The client must trust the certificate issuer and the certificate must cover this hostname."],
            ["Connectivity check", "Run from the recipient network. HTTP 401 is expected without a token and confirms the route is reachable. Use an authorized profile separately to verify file delivery."],
        ];
        const handoff = [
            "OpenShare firewall and load balancer handoff" + (share ? " for " + share.name : ""),
            "Recipient endpoint: " + endpointUrl,
            ...steps.slice(0, 3).map(([label, text]) => label + ": " + text),
            "Allowed HTTP methods and paths:",
            ...routes.map(([method, path]) => method + " " + path),
            "Connectivity check: " + steps[3][1],
            probe,
        ].join("\n");
        button("Copy network guide", async () => {
            await navigator.clipboard.writeText(handoff);
            notice("Network guide copied.");
        }, actions, true);
        if (dismiss) button("Done", dismiss, actions);
        const summary = node("dl", undefined, guide);
        node("dt", "Recipient endpoint", summary);
        node("dd", endpointUrl, summary);
        steps.slice(0, 3).forEach(([label, text]) => {
            node("dt", label, summary);
            node("dd", text, summary);
        });
        const details = node("details", undefined, guide);
        node("summary", "Allowed methods and paths", details);
        table(["Method", "Path"], routes, details);
        node("h3", steps[3][0], guide);
        node("p", steps[3][1], guide);
        node("pre", probe, guide);
        return guide;
    }

    function saveProfile(profile) {
        const url = URL.createObjectURL(new Blob([JSON.stringify(profile, null, 2)], {type: "application/json"}));
        const link = document.createElement("a");
        link.href = url;
        link.download = "openshare.share";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function issue(parent, share) {
        const panel = node("dialog", undefined, parent);
        panel.className = "os-issue";
        node("h3", "Generate profile for " + share.name, panel).id = "os-profile-title";
        panel.setAttribute("aria-labelledby", "os-profile-title");
        node("p", "Anyone holding the profile can read this share until its token expires or is revoked.", panel);
        const error = node("p", "", panel);
        error.setAttribute("role", "alert");
        error.className = "os-inline-error";
        const label = input("Recipient label", "text", panel);
        const days = input("Expires in days (1–30)", "number", panel, 7);
        days.min = 1;
        days.max = 30;
        const actions = node("div", undefined, panel);
        actions.className = "os-actions";
        button("Generate and download", async () => {
            error.textContent = "";
            try {
                saveProfile(await api("issue", {snapshot: share.id, label: label.value, days: days.value}));
            } catch (failure) {
                error.textContent = failure.message;
                return;
            }
            panel.close();
            await render();
            notice("Profile downloaded. Store it as a credential.");
        }, actions, true);
        button("Cancel", () => panel.close(), actions);
        panel.addEventListener("close", () => panel.remove(), {once: true});
        panel.showModal();
        label.focus();
    }

    async function render(guideShareId = null) {
        const model = await api("list");
        root.replaceChildren();
        const nav = node("nav", undefined, root);
        nav.className = "os-nav";
        nav.setAttribute("aria-label", "OpenShare");
        const tabs = ["Shares", "Activity", "Access Tokens", "Network Access"];
        if (model.admin) tabs.push("Logging");
        tabs.forEach((tab) => {
            const item = button(tab, async () => { view = tab; await render(); }, nav);
            if (tab === view) item.setAttribute("aria-current", "page");
        });
        const message = node("p", "", root);
        message.className = "os-message";
        message.setAttribute("role", "status");
        const panel = node("section", undefined, root);
        panel.className = "os-panel";

        if (view === "Shares") {
            const heading = intro(panel, "Published shares", "Publish snapshots from Splunk and manage recipient access.");
            button("Create share", () => create(panel), heading, true);
            if (!model.shares.length) {
                empty(panel, "No published shares", "Create a share from an index or saved report to get started.");
                return;
            }
            const guideArea = node("div", undefined, panel);
            function showGuide(share) {
                guideArea.replaceChildren();
                const guide = networkGuide(guideArea, model.endpoint, share, () => guideArea.replaceChildren());
                guide.querySelector("h2").tabIndex = -1;
                guide.querySelector("h2").focus();
            }
            table(["Share", "Source", "Rows", "Fields", "Snapshot", "Actions"], model.shares.map((share) => {
                const actions = node("div");
                actions.className = "os-actions";
                button("Generate profile", () => issue(panel, share), actions);
                if (share.can_refresh) button("Refresh", async () => {
                    const draft = await api("stage_refresh", {snapshot: share.id});
                    panel.querySelector(".os-refresh")?.remove();
                    const preview = node("section", undefined, panel);
                    preview.className = "os-refresh";
                    review(preview, draft, true);
                }, actions);
                button("Disable", async () => {
                    if (!confirm("Disable this share and revoke its grants? Existing file links can work for up to five minutes.")) return;
                    await api("disable", {snapshot: share.id});
                    await render();
                }, actions);
                const title = node("div");
                node("strong", share.name, title);
                button("Network guide", () => showGuide(share), title).className = "os-text-button";
                return [title, share.source, share.rows.toLocaleString(), JSON.parse(share.fields).join(", "), date(share.created), actions];
            }), panel);
            const published = model.shares.find((share) => share.id === guideShareId);
            if (published) showGuide(published);
        } else if (view === "Access Tokens") {
            intro(panel, "Access tokens", "Review expiring profiles and rotate or revoke access.");
            if (!model.grants.length) {
                empty(panel, "No recipient profiles", "Generate a profile from a published share.");
                return;
            }
            table(["Recipient", "Share", "Status", "Expires", "Last snapshot request", "Actions"], model.grants.map((grant) => {
                const actions = node("div");
                actions.className = "os-actions";
                const state = grant.revoked ? "Revoked" : grant.expires * 1000 <= Date.now() ? "Expired" : "Active";
                if (state === "Active") {
                    button("Rotate", async () => {
                        if (!confirm("Replace this profile? The current token will stop working immediately.")) return;
                        saveProfile(await api("rotate", {snapshot: grant.snapshot, grant: grant.id}));
                        await render();
                    }, actions);
                    button("Revoke", async () => {
                        if (!confirm("Revoke access? Previously issued file links can work for up to five minutes.")) return;
                        await api("revoke", {snapshot: grant.snapshot, grant: grant.id});
                        await render();
                    }, actions);
                }
                return [grant.label, grant.name, status(state, state.toLowerCase()), date(grant.expires), date(grant.last_used), actions];
            }), panel);
        } else if (view === "Activity") {
            const heading = intro(panel, "Activity", "Review the latest 100 publishing, access, and configuration events.");
            if (!model.settings.access_audit) heading.append(status("Recipient auditing off", "expired"));
            const names = new Map(model.shares.map((share) => [share.id, share.name]));
            const kinds = [...new Set(model.activity.map((event) => event.event))].sort();
            const filters = node("div", undefined, panel);
            filters.className = "os-filters";
            const eventType = select("Event type", [["", "All events"], ...kinds.map((kind) => [kind, kind.replaceAll("_", " ")])], filters);
            const shareFilter = select("Share", [["", "All shares"], ...names], filters);
            const results = node("div", undefined, panel);
            function showEvents() {
                results.replaceChildren();
                const events = model.activity.filter((event) =>
                    (!eventType.value || event.event === eventType.value) &&
                    (!shareFilter.value || event.snapshot === shareFilter.value));
                if (!events.length) {
                    empty(results, "No matching events", "Change the filters or publish a snapshot to generate activity.");
                    return;
                }
                table(["Time", "Event", "Publisher", "Share", "Grant"], events.map((event) => [
                    date(event.ts), event.event.replaceAll("_", " "), event.actor || "—",
                    names.get(event.snapshot) || event.snapshot || "—", event.grant_id || "—"
                ]), results);
            }
            eventType.onchange = showEvents;
            shareFilter.onchange = showEvents;
            showEvents();
        } else if (view === "Network Access") {
            networkGuide(panel, model.endpoint);
        } else {
            intro(panel, "Logging", "Control recipient access auditing and temporary diagnostics.");
            const auditRow = node("div", undefined, panel);
            auditRow.className = "os-setting";
            const audit = input("Record recipient access audit", "checkbox", auditRow);
            audit.checked = Boolean(model.settings.access_audit);
            node("p", "Records snapshot requests, file transfers, and denied requests. Share and credential changes are always recorded.", auditRow);
            const diagnosticRow = node("div", undefined, panel);
            diagnosticRow.className = "os-setting";
            const verbose = input("Verbose diagnostics for 30 minutes", "checkbox", diagnosticRow);
            verbose.checked = model.settings.debug_until * 1000 > Date.now();
            node("p", verbose.checked ? "Active until " + date(model.settings.debug_until) : "Includes request timings and status codes in the sharing service log.", diagnosticRow);
            button("Save logging settings", async () => {
                await api("logging", {access_audit: audit.checked, verbose: verbose.checked});
                await render();
                notice("Logging settings saved.");
            }, panel, true);
        }
    }

    render().catch((error) => { root.textContent = error.message; });
});
