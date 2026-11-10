/* Service worker running the example Django project with Pyodide.
 *
 * Every same-origin request within the worker's scope is handed over to
 * Django (see runtime.py), except for the demo's own files under _wasm/.
 *
 * This is a module service worker: Pyodide doesn't support classic workers,
 * and service workers can't use dynamic import(), so both Pyodide modules
 * are imported statically, and the runtime handed to loadPyodide.
 */

import createPyodideModule from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.asm.mjs";
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const PYODIDE_VERSION = "314.0.7";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
// Replaced at build time, so each build installs a new service worker.
const BUILD_ID = "__BUILD_ID__";

const SCOPE = new URL(globalThis.registration.scope);
const ASSETS = new URL(`_wasm/${BUILD_ID}/`, SCOPE);
const APP_DIR = "/home/pyodide/app";
const DATA_DIR = "/data";
const REDIRECT_STATUSES = [301, 302, 303, 307, 308];
const NULL_BODY_STATUSES = [101, 103, 204, 205, 304];

let runtimePromise = null;

/** Send a message to all open pages, including ones not yet controlled. */
async function broadcast(message) {
    const clients = await globalThis.clients.matchAll({
        includeUncontrolled: true,
        type: "window",
    });
    for (const client of clients) {
        client.postMessage(message);
    }
}

function status(text) {
    console.info(
        `[django-debug-toolbar demo] ${Math.round(performance.now())}ms ${text}`
    );
    broadcast({ type: "status", text });
}

async function syncfs(pyodide, populate) {
    return await new Promise((resolve, reject) => {
        pyodide.FS.syncfs(populate, (err) => (err ? reject(err) : resolve()));
    });
}

async function boot() {
    // Fetched first: when the demo is redeployed, this build's files are gone,
    // and a newer service worker needs to replace this one.
    const manifestResponse = await fetch(new URL("manifest.json", ASSETS), {
        cache: "no-cache",
    });
    if (!manifestResponse.ok) {
        await globalThis.registration.update();
        throw new Error(
            "This demo has been updated since you last opened it. Reload the page in a few seconds."
        );
    }
    const manifest = await manifestResponse.json();
    // Django, django-debug-toolbar and the example project, precompiled by
    // build.py. Downloaded while Pyodide starts.
    const archivePromise = fetch(new URL(manifest.app, ASSETS)).then((r) =>
        r.arrayBuffer()
    );

    status(`Loading Python (Pyodide ${PYODIDE_VERSION})…`);
    const pyodide = await loadPyodide({
        indexURL: PYODIDE_URL,
        createPyodideModule,
    });

    status("Loading Django and django-debug-toolbar…");
    // Packages built by Pyodide: jinja2 for the example project, and tzdata as
    // there is no system time zone database.
    await pyodide.loadPackage(["jinja2", "tzdata"]);
    pyodide.unpackArchive(await archivePromise, "zip", { extractDir: APP_DIR });

    status("Restoring the database…");
    pyodide.FS.mkdirTree(DATA_DIR);
    pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, DATA_DIR);
    await syncfs(pyodide, true);

    status("Setting up Django…");
    pyodide.runPython(`
import sys
sys.path.insert(0, "${APP_DIR}")
from example.wasm import runtime
runtime.setup()
`);
    const runtime = pyodide.pyimport("example.wasm.runtime");
    const app = { pyodide, handleRequest: runtime.handle_request };
    await persist(app);
    status("Ready.");
    return app;
}

/** Start Python and Django once, retrying on the next request if it failed. */
function getRuntime() {
    if (!runtimePromise) {
        runtimePromise = boot().catch((err) => {
            runtimePromise = null;
            console.error(err);
            broadcast({ type: "error", text: String(err.message || err) });
            throw err;
        });
    }
    return runtimePromise;
}

// Copy the in-memory filesystem to IndexedDB, coalescing concurrent calls.
let syncing = null;
let syncAgain = false;
function persist(app) {
    if (syncing) {
        syncAgain = true;
        return syncing;
    }
    syncing = (async () => {
        try {
            do {
                syncAgain = false;
                await syncfs(app.pyodide, false);
            } while (syncAgain);
        } catch (err) {
            console.error("Failed to persist the database", err);
        } finally {
            syncing = null;
        }
    })();
    return syncing;
}

/* Cookies.
 *
 * Responses created by a service worker can't set cookies with Set-Cookie,
 * and the Cookie header isn't visible on intercepted requests. Use the
 * Cookie Store API so Django and page scripts share the browser's cookies,
 * or fall back to an in-memory jar.
 */
const memoryJar = new Map();

async function getCookieHeader() {
    if (globalThis.cookieStore) {
        const cookies = await globalThis.cookieStore.getAll();
        return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    }
    return [...memoryJar].map(([name, value]) => `${name}=${value}`).join("; ");
}

async function setCookie(header) {
    const [nameValue, ...attributes] = header.split(";");
    const separator = nameValue.indexOf("=");
    const name = nameValue.slice(0, separator).trim();
    const value = nameValue.slice(separator + 1).trim();
    const cookie = { name, value, path: "/" };
    let expired = false;
    for (const attribute of attributes) {
        const [key, ...rest] = attribute.split("=");
        const attrValue = rest.join("=").trim();
        switch (key.trim().toLowerCase()) {
            case "path":
                cookie.path = attrValue;
                break;
            case "max-age":
                cookie.expires = Date.now() + Number(attrValue) * 1000;
                expired = Number(attrValue) <= 0;
                break;
            case "expires":
                cookie.expires ??= Date.parse(attrValue);
                expired ||= Date.parse(attrValue) <= Date.now();
                break;
            case "samesite":
                cookie.sameSite = attrValue.toLowerCase();
                break;
        }
    }
    if (globalThis.cookieStore) {
        if (expired) {
            await globalThis.cookieStore.delete({ name, path: cookie.path });
        } else {
            await globalThis.cookieStore.set(cookie);
        }
    } else if (expired) {
        memoryJar.delete(name);
    } else {
        memoryJar.set(name, value);
    }
}

function escapeHTML(text) {
    return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

async function handleRequest(event) {
    const request = event.request;
    let app;
    try {
        app = await getRuntime();
    } catch (err) {
        return new Response(
            `<h1>Could not start Django</h1><pre>${escapeHTML(String(err.message || err))}</pre>`,
            {
                status: 500,
                headers: { "Content-Type": "text/html; charset=utf-8" },
            }
        );
    }

    const headers = Object.fromEntries(request.headers);
    // Headers the browser adds after the service worker, which Django needs.
    if (request.referrer && request.referrer !== "about:client") {
        headers.referer = request.referrer;
    }
    if (!["GET", "HEAD"].includes(request.method)) {
        headers.origin = SCOPE.origin;
    }
    const cookie = await getCookieHeader();
    if (cookie) {
        headers.cookie = cookie;
    }
    const body = ["GET", "HEAD"].includes(request.method)
        ? undefined
        : new Uint8Array(await request.arrayBuffer());

    let result;
    try {
        const pyResult = app.handleRequest(
            request.method,
            request.url,
            SCOPE.pathname,
            headers,
            body
        );
        result = pyResult.toJs({ dict_converter: Object.fromEntries });
        pyResult.destroy();
    } catch (err) {
        console.error(err);
        return new Response(
            `<pre>${escapeHTML(String(err.message || err))}</pre>`,
            {
                status: 500,
                headers: { "Content-Type": "text/html; charset=utf-8" },
            }
        );
    }
    event.waitUntil(persist(app));

    const responseHeaders = new Headers();
    for (const [name, value] of result.headers) {
        if (name.toLowerCase() === "set-cookie") {
            await setCookie(value);
        } else {
            responseHeaders.append(name, value);
        }
    }

    if (REDIRECT_STATUSES.includes(result.status)) {
        const location = new URL(responseHeaders.get("Location"), request.url);
        return Response.redirect(location.href, result.status);
    }
    const hasBody =
        request.method !== "HEAD" &&
        !NULL_BODY_STATUSES.includes(result.status);
    return new Response(hasBody ? result.body : null, {
        status: result.status,
        headers: responseHeaders,
    });
}

globalThis.addEventListener("install", (event) => {
    globalThis.skipWaiting();
    event.waitUntil(getRuntime());
});

globalThis.addEventListener("activate", (event) => {
    event.waitUntil(globalThis.clients.claim());
});

globalThis.addEventListener("message", (event) => {
    // Sent by the loading page when it isn't controlled yet (e.g. hard reload).
    if (event.data === "claim") {
        event.waitUntil(
            getRuntime()
                .then(() => globalThis.clients.claim())
                .then(() => broadcast({ type: "ready" }))
        );
    }
});

globalThis.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    if (!url.href.startsWith(SCOPE.href)) {
        return;
    }
    const path = url.href.slice(SCOPE.href.length);
    if (path.startsWith("_wasm/") || path === "sw.js") {
        return;
    }
    event.respondWith(handleRequest(event));
});
