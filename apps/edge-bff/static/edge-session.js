/* generated from apps/edge-bff/shared/edge-session.ts sha256=869192580ed828e9839006d1eb6c06b5f9212463ef147b17800df0eea0c8db5f by shared/build-shell.mjs; do not edit */
var EdgeSession = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // shared/edge-session.ts
  var edge_session_exports = {};
  __export(edge_session_exports, {
    CATALOG_URL: () => CATALOG_URL,
    ENTITLEMENTS_HEADER: () => ENTITLEMENTS_HEADER,
    GUEST_IDENTITY: () => GUEST_IDENTITY,
    GUEST_URL: () => GUEST_URL,
    LAST_LOGIN_KEY: () => LAST_LOGIN_KEY,
    PREFERENCES_URL: () => PREFERENCES_URL,
    SESSION_URL: () => SESSION_URL,
    SIGNED_OUT: () => SIGNED_OUT,
    STORAGE: () => STORAGE,
    SYNC_KEYS: () => SYNC_KEYS,
    SessionError: () => SessionError,
    accessText: () => accessText,
    checkUser: () => checkUser,
    classify: () => classify,
    clearUserState: () => clearUserState,
    edge: () => edge,
    errorOf: () => errorOf,
    identityOf: () => identityOf,
    isAccessRefusal: () => isAccessRefusal,
    isLastLogin: () => isLastLogin,
    keepsSession: () => keepsSession,
    lastLogin: () => lastLogin,
    loginKey: () => loginKey,
    migrateIdentity: () => migrateIdentity,
    noteIdentity: () => noteIdentity,
    noteLogin: () => noteLogin,
    onCleared: () => onCleared,
    onReset: () => onReset,
    onSignedOut: () => onSignedOut,
    onVersion: () => onVersion,
    preferences: () => preferences,
    prefs: () => prefs,
    readError: () => readError,
    reloadPage: () => reloadPage,
    retryAfter: () => retryAfter,
    sessionClient: () => sessionClient,
    setRole: () => setRole,
    stampOwner: () => stampOwner,
    stampedCopy: () => stampedCopy
  });
  var STORAGE = Object.freeze([
    // the shell (static/index.html, static/edge-client.js)
    { key: "edge-auth-monitor-theme", match: "exact", area: "local", kind: "browser", where: "shell, all pages", what: "light or dark theme" },
    { key: "edge-monitor-collapsed", match: "exact", area: "local", kind: "browser", where: "shell", what: "Monitor sidebar folded" },
    { key: "edge-monitor-width", match: "exact", area: "local", kind: "browser", where: "shell", what: "Monitor sidebar width" },
    { key: "edge-details-width", match: "exact", area: "local", kind: "browser", where: "shell", what: "details panel width" },
    { key: "edge-details-open", match: "exact", area: "session", kind: "browser", where: "shell", what: "details panel open" },
    { key: "edge-pins-height", match: "exact", area: "local", kind: "browser", where: "shell", what: "pinned answers panel height" },
    { key: "edge-pins-open", match: "exact", area: "local", kind: "browser", where: "shell", what: "pinned answers panel open" },
    { key: "edge-flow-open", match: "exact", area: "local", kind: "browser", where: "shell", what: "flow panel open" },
    { key: "edge-sources-open:", match: "prefix", area: "local", kind: "browser", where: "shell", what: "a Sources part opened (by its title)" },
    { key: "edge-last-login", match: "exact", area: "local", kind: "browser", where: "shared/edge-session.ts", what: "the identity signed in last (owner:<owner key>, else the login), to see a change of user; removed on sign-out" },
    { key: "edge-side-attach:", match: "prefix", area: "session", kind: "user", cache: true, where: "shell", what: "a passage quoted into a side chat (by conversation id)" },
    { key: "edge-model-choice", match: "exact", area: "local", kind: "user", sync: true, cap: "monitor.view", where: "shell", what: "the chosen AI model and level" },
    { key: "edge-research-context", match: "exact", area: "session", kind: "user", cache: true, where: "shell (legacy)", what: "an older research context; removed on load" },
    { key: "edge-research-context", match: "exact", area: "local", kind: "user", cache: true, where: "shell (legacy)", what: "an older research context; removed on load" },
    { key: "edge-auth-monitor-conversations", match: "exact", area: "local", kind: "user", cache: true, where: "shell (legacy)", what: "an older conversation list; removed on load" },
    { key: "edge-auth-monitor-conversations", match: "exact", area: "session", kind: "user", cache: true, where: "shell (legacy)", what: "an older conversation list; removed on load" },
    { key: "edge-session", match: "exact", area: "local", kind: "user", cache: true, where: "shell (legacy)", what: "an older session copy; removed on load" },
    { key: "edge-session", match: "exact", area: "session", kind: "user", cache: true, where: "shell (legacy)", what: "an older session copy; removed on load" },
    { key: "edge-active-run", match: "exact", area: "local", kind: "user", cache: true, where: "shell (legacy)", what: "an older running question; removed on load" },
    { key: "edge-active-run", match: "exact", area: "session", kind: "user", cache: true, where: "shell (legacy)", what: "an older running question; removed on load" },
    // the Terminal (terminal/src): a chart's content and the account's saved things are the user's; panel sizes are the browser's
    { key: "ml.symbol", match: "exact", area: "local", kind: "user", sync: true, where: "Terminal, Backtest, Screener, Radar, Overview, Watchlist, Sector Analysis", what: "the ticker the Terminal opens on" },
    { key: "ml.tf", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "timeframe" },
    { key: "ml.tfs", match: "exact", area: "local", kind: "browser", where: "Terminal", what: "timeframes the data offered" },
    { key: "ml.fi.metric", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "bond yield or price" },
    { key: "ml.chart.style", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "candle or line" },
    { key: "ml.chart.mode", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "price or return" },
    { key: "ml.session.lines", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "lines at the start of each trading day on intraday charts" },
    { key: "ml.vol.on", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "volume shown" },
    { key: "ml.vol.removed", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "volume removed" },
    { key: "ml.ind.v1", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "the indicators on the chart" },
    { key: "ml.ind.filters", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "indicator filters" },
    { key: "ml.ind.favs", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal", what: "favourite indicators" },
    { key: "ml.ind.box", match: "exact", area: "local", kind: "browser", where: "Terminal", what: "Indicators window size" },
    { key: "ml.ind.navw", match: "exact", area: "local", kind: "browser", where: "Terminal", what: "Indicators window group list width" },
    { key: "ml.legend.hidden", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "indicator names hidden" },
    { key: "ml.events.v1", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "event markers chosen" },
    { key: "ml.flow.filters", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "Flow Timeline filters" },
    { key: "ml.flow.cum", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal (layout)", what: "Flow Timeline cumulative line" },
    { key: "ml.flow.collapsed", match: "exact", area: "local", kind: "user", cache: true, where: "Terminal (layout)", what: "Flow Timeline folded" },
    { key: "ml.flow.h", match: "exact", area: "local", kind: "user", cache: true, where: "Terminal (layout)", what: "Flow Timeline height" },
    { key: "ml.flow.ratio", match: "exact", area: "local", kind: "user", cache: true, where: "Terminal (layout)", what: "Flow Timeline height share" },
    { key: "ml.layout.", match: "prefix", area: "local", kind: "user", cache: true, where: "Terminal", what: "the open saved layout, its autosave and base" },
    { key: "ml.drawings.", match: "prefix", area: "local", kind: "user", cache: true, where: "Terminal", what: "drawings kept while the account cannot be reached (stamped with the login, M468)" },
    { key: "ml.assets.v1", match: "exact", area: "local", kind: "user", sync: true, cap: "terminal.view", where: "Terminal", what: "series added to the chart" },
    { key: "ml.assets.defaults", match: "exact", area: "local", kind: "browser", where: "Terminal", what: "default look of an added series" },
    { key: "ml.assets.flow.", match: "prefix", area: "local", kind: "user", cache: true, where: "Terminal", what: "an added series pane folded or its height, by its ticker (the account's series, re-check R1-20)" },
    { key: "ml.draw.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "drawing tool choices (cursor, line, shape, measure, magnet)" },
    { key: "ml.stats.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "left panel width, fold, sections and order" },
    { key: "ml.broker.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "right panel width, fold, sections and order" },
    { key: "ml.acc.top", match: "exact", area: "local", kind: "browser", where: "Terminal", what: "top brokers shown" },
    { key: "ml.fd.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "Foreign x Domestic top count and readout" },
    { key: "ml.win.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "floating window places and which are open" },
    { key: "ml.winst.", match: "prefix", area: "local", kind: "browser", where: "Terminal", what: "floating broker window sort and view" },
    { key: "terminal-files", match: "exact", area: "idb", kind: "user", cache: true, where: "Terminal, Backtest, Screener", what: "downloaded data files and the Screener's last result" },
    // the Backtest (backtest/src)
    { key: "ml.my", match: "exact", area: "local", kind: "user", sync: true, cap: "backtest.view", where: "Backtest", what: "my conditions" },
    { key: "ml.bw", match: "exact", area: "local", kind: "browser", where: "Backtest", what: "panel width" },
    { key: "ml.panel", match: "exact", area: "local", kind: "browser", where: "Backtest", what: "panel shown" },
    // the Screener (screener/src)
    { key: "scr.last", match: "exact", area: "local", kind: "user", sync: true, cap: "screener.view", where: "Screener", what: "the last screen definition" },
    { key: "scr.boot", match: "exact", area: "local", kind: "user", cache: true, where: "Screener", what: "the cached first paint pointer (with its login)" },
    { key: "scr.extraCols", match: "exact", area: "local", kind: "user", sync: true, cap: "screener.view", where: "Screener", what: "extra columns chosen" },
    { key: "scr.panel", match: "exact", area: "local", kind: "browser", where: "Screener", what: "panel layout" },
    { key: "scr.panes", match: "exact", area: "local", kind: "browser", where: "Screener", what: "pane sizes" },
    { key: "scr.popsize", match: "exact", area: "local", kind: "browser", where: "Screener", what: "pop-up sizes" },
    { key: "scr.colorder", match: "exact", area: "local", kind: "browser", where: "Screener", what: "column order" },
    // the Watchlist (watchlist/src)
    { key: "edge.watchlist.view", match: "exact", area: "local", kind: "user", sync: true, cap: "watchlist.view", where: "Watchlist", what: "the open list id and Table or Cards" },
    { key: "edge.watchlist.logos", match: "exact", area: "local", kind: "user", cache: true, where: "Watchlist", what: "issuer logo list (12 hours; a reference file the plan reads, so it leaves with the account: re-check R1-17)" }
  ]);
  function classify(key, area = "local") {
    let best = null;
    for (const e of STORAGE) {
      if (e.area !== area) continue;
      if (e.match === "exact" ? key === e.key : key.startsWith(e.key)) {
        if (e.match === "exact") return e;
        if (!best || e.key.length > best.key.length) best = e;
      }
    }
    return best;
  }
  var OURS = /^(?:ml\.|scr\.|edge[.:-])/;
  var isUserKey = (key, area) => {
    const e = classify(key, area);
    return e ? e.kind === "user" : OURS.test(key);
  };
  var LAST_LOGIN_KEY = "edge-last-login";
  var CHANNEL = "edge-session";
  var PAGE_LONG = typeof AbortController === "function" ? { signal: new AbortController().signal } : void 0;
  var norm = (login) => String(login || "").trim().toLowerCase();
  function areaOf(area) {
    try {
      return area === "local" ? globalThis.localStorage ?? null : globalThis.sessionStorage ?? null;
    } catch {
      return null;
    }
  }
  function keysOf(s) {
    const out = [];
    try {
      for (let i = 0; i < s.length; i++) {
        const k = s.key(i);
        if (k !== null) out.push(k);
      }
    } catch {
    }
    return out;
  }
  function lastLogin() {
    try {
      return areaOf("local")?.getItem(LAST_LOGIN_KEY) || "";
    } catch {
      return "";
    }
  }
  var PAGE_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
  function post(message) {
    try {
      if (typeof BroadcastChannel !== "undefined") {
        const c = new BroadcastChannel(CHANNEL);
        c.postMessage({ ...message, from: PAGE_ID });
        c.close();
      }
    } catch {
    }
  }
  function stampOwner(value) {
    if (!value || value[0] !== "{") return null;
    try {
      const v = JSON.parse(value);
      return v && typeof v === "object" && typeof v.owner === "string" && v.owner ? v.owner : null;
    } catch {
      return null;
    }
  }
  var stampedCopy = (value) => stampOwner(value) !== null;
  function clearArea(area, signOut, keepStampsOf) {
    const s = areaOf(area);
    if (!s) return;
    for (const k of keysOf(s)) {
      if (k === LAST_LOGIN_KEY ? signOut : isUserKey(k, area)) {
        try {
          if (!signOut && keepStampsOf && stampOwner(s.getItem(k)) === keepStampsOf) continue;
          s.removeItem(k);
        } catch {
        }
      }
    }
  }
  var memoryClears = /* @__PURE__ */ new Set();
  function clearUserState(opts = {}) {
    memoryClears.forEach((fn) => {
      try {
        fn();
      } catch {
      }
    });
    clearArea("local", !!opts.signOut, opts.keepStampsOf);
    clearArea("session", !!opts.signOut, opts.keepStampsOf);
    post({ type: "cleared", signOut: !!opts.signOut });
    const idb = (() => {
      try {
        return globalThis.indexedDB;
      } catch {
        return void 0;
      }
    })();
    const names = STORAGE.filter((e) => e.area === "idb" && e.kind === "user").map((e) => e.key);
    if (!idb) return Promise.resolve();
    return Promise.all(names.map((n) => new Promise((done) => {
      try {
        const r = idb.deleteDatabase(n);
        r.onsuccess = r.onerror = () => done();
        r.onblocked = () => done();
      } catch {
        done();
      }
    }))).then(() => void 0);
  }
  var identityOf = (login, ownerKey) => ownerKey ? `owner:${norm(ownerKey)}` : norm(login);
  function hasUserState() {
    for (const area of ["local", "session"]) {
      const s = areaOf(area);
      if (!s) continue;
      if (keysOf(s).some((k) => k !== LAST_LOGIN_KEY && isUserKey(k, area))) return true;
    }
    return false;
  }
  function hasStampsOf(owner) {
    const s = areaOf("local");
    if (!s || !owner) return false;
    return keysOf(s).some((k) => {
      if (!k.startsWith("ml.drawings.")) return false;
      try {
        const v = JSON.parse(s.getItem(k) || "null");
        return !!v && typeof v === "object" && !Array.isArray(v) && v.owner === owner;
      } catch {
        return false;
      }
    });
  }
  function migrateIdentity(from, to) {
    const s = areaOf("local");
    if (!s || !from || !to || from === to) return;
    for (const k of keysOf(s)) {
      if (!k.startsWith("ml.drawings.")) continue;
      try {
        const v = JSON.parse(s.getItem(k) || "null");
        if (v && typeof v === "object" && !Array.isArray(v) && v.owner === from) s.setItem(k, JSON.stringify({ ...v, owner: to }));
      } catch {
      }
    }
  }
  var bareForm = (id) => !!id && !id.startsWith("owner:") && id !== GUEST_IDENTITY;
  function migrateBare(to) {
    const s = areaOf("local");
    if (!s || bareForm(to)) return;
    for (const k of keysOf(s)) {
      if (!k.startsWith("ml.drawings.")) continue;
      try {
        const v = JSON.parse(s.getItem(k) || "null");
        if (v && typeof v === "object" && !Array.isArray(v) && typeof v.owner === "string" && bareForm(v.owner)) s.setItem(k, JSON.stringify({ ...v, owner: to }));
      } catch {
      }
    }
  }
  var seedKeeps = (was, now, seed) => seed === true && was !== now && (!was || bareForm(was));
  function noteIdentity(login, ownerKey, opts = {}) {
    const now = identityOf(login, ownerKey);
    if (!now) return { changed: false, same: false };
    const was = lastLogin();
    const seed = seedKeeps(was, now, opts.seed);
    const ownStamps = !was && hasStampsOf(norm(login));
    const upgraded = !seed && !!ownerKey && (was === norm(login) || ownStamps);
    if (seed) migrateBare(now);
    else if (upgraded) migrateIdentity(norm(login), now);
    const unknown = !was && !ownStamps && !seed && hasUserState();
    const changed = !!was && was !== now && !upgraded && !seed || unknown;
    if (changed) clearUserState(was === GUEST_IDENTITY ? { keepStampsOf: now } : {});
    try {
      areaOf("local")?.setItem(LAST_LOGIN_KEY, now);
    } catch {
    }
    return { changed, same: !!was && (was === now || upgraded || seed) || !was && (ownStamps || seed) };
  }
  var noteLogin = (login, ownerKey) => noteIdentity(login, ownerKey).changed;
  function checkUser(login, ownerKey, opts = {}) {
    const now = identityOf(login, ownerKey), was = lastLogin();
    if (!now || !was || was === now) return false;
    if (ownerKey && was === norm(login)) {
      migrateIdentity(was, now);
      return false;
    }
    if (seedKeeps(was, now, opts.seed)) {
      migrateBare(now);
      return false;
    }
    clearUserState(was === GUEST_IDENTITY ? { keepStampsOf: now } : {});
    return true;
  }
  var isLastLogin = (login) => !!norm(login) && lastLogin() === norm(login);
  var loginKey = norm;
  function retryAfter(h, now = Date.now()) {
    if (!h) return null;
    const s = Number(h);
    if (Number.isFinite(s) && s >= 0) return Math.ceil(s);
    const t = Date.parse(h);
    return Number.isFinite(t) ? Math.max(0, Math.ceil((t - now) / 1e3)) : null;
  }
  var KIND = {
    UNAUTHENTICATED: "signin",
    CSRF_INVALID: "csrf",
    CAPABILITY_REQUIRED: "upgrade",
    PLAN_EXPIRED: "upgrade",
    MFA_REQUIRED: "mfa",
    LIMIT_REACHED: "limit",
    SIGN_IN_RATE_LIMIT: "wait",
    ORIGIN_REJECTED: "origin",
    NOT_FOUND: "not_found"
  };
  function readError(status, body, retryAfterHeader) {
    const err = body && typeof body.error === "object" && body.error ? body.error : null;
    let code = "", message = "", legacy = false;
    if (err) {
      code = String(err.code || "");
      message = typeof err.message === "string" ? err.message : "";
    } else if (body && typeof body.error === "string") code = body.error;
    else if (body && "detail" in body && (status === 401 || status === 403)) {
      legacy = true;
      const detail = typeof body.detail === "string" ? body.detail : "";
      code = status === 401 ? "UNAUTHENTICATED" : /csrf/i.test(detail) ? "CSRF_INVALID" : "FORBIDDEN";
      message = detail;
    }
    if (!code) code = status === 401 ? "UNAUTHENTICATED" : `HTTP_${status}`;
    const details = err && err.details && typeof err.details === "object" ? err.details : {};
    const fromDetails = typeof details.retry_after_s === "number" ? Math.ceil(details.retry_after_s) : null;
    const kind = status === 401 ? "signin" : status === 403 && code === "CSRF_INVALID" ? "csrf" : KIND[code] && KIND[code] !== "signin" && KIND[code] !== "csrf" ? KIND[code] : "other";
    return {
      status,
      code,
      message,
      details,
      ...err && typeof err.field === "string" ? { field: err.field } : {},
      retryAfter: retryAfter(retryAfterHeader) ?? fromDetails,
      legacy,
      kind
    };
  }
  async function errorOf(res) {
    let body = null;
    try {
      body = await res.json();
    } catch {
    }
    return readError(res.status, body, res.headers?.get?.("Retry-After"));
  }
  var keepsSession = (e) => e.kind !== "signin";
  var isAccessRefusal = (e) => e.kind === "upgrade" || e.kind === "mfa" || e.kind === "limit" || e.kind === "wait";
  var secs = (n) => n == null ? "a minute" : n === 1 ? "1 second" : `${n} seconds`;
  function accessText(e) {
    const name = typeof e.details.display_name === "string" && e.details.display_name ? e.details.display_name : "";
    if (e.details.visitor === true && (e.kind === "upgrade" || e.kind === "limit"))
      return e.message || (e.kind === "upgrade" ? `${name || "This"} needs an EDGE account. Sign in to use it.` : `You have reached the limit for visitors without an account. Try again in ${secs(e.retryAfter)}, or sign in to EDGE.`);
    switch (e.kind) {
      case "signin":
        return e.message && !e.legacy ? e.message : "Your EDGE sign-in has ended. Sign in to EDGE again, then open this page again.";
      case "csrf":
        return "This page's sign-in check failed. Reload the page and try again.";
      case "upgrade":
        return e.message || (e.code === "PLAN_EXPIRED" ? "Your EDGE plan has ended. Renew it to use this again; you are still signed in." : `${name || "This feature"} is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.`);
      case "mfa":
        return e.message || "This needs your sign-in code. Enter the code from your authenticator app in EDGE, then try again.";
      case "limit":
        return e.message || `You have reached your plan's limit. Try again in ${secs(e.retryAfter)}, or upgrade the plan.`;
      case "wait":
        return e.message || `Too many sign-in attempts. Wait ${secs(e.retryAfter)}, then try again.`;
      default:
        return null;
    }
  }
  var SESSION_URL = "/api/v1/auth/session";
  var ENTITLEMENTS_HEADER = "X-Edge-Entitlements";
  var GUEST_URL = "/api/v1/auth/guest";
  var GUEST_IDENTITY = "guest:";
  var CATALOG_URL = "/api/v1/catalog/";
  var isItemKey = (key) => key.includes(":");
  var SessionError = class extends Error {
    constructor(error, message) {
      super(message);
      this.error = error;
    }
  };
  var clients = /* @__PURE__ */ new Set();
  var resets = /* @__PURE__ */ new Set();
  var fireResets = () => resets.forEach((fn) => {
    try {
      fn();
    } catch {
    }
  });
  function onReset(fn) {
    resets.add(fn);
    return () => {
      resets.delete(fn);
    };
  }
  var clearedHooks = /* @__PURE__ */ new Set();
  function onCleared(fn) {
    clearedHooks.add(fn);
    return () => {
      clearedHooks.delete(fn);
    };
  }
  var versionHooks = /* @__PURE__ */ new Set();
  var fireVersion = (v) => versionHooks.forEach((fn) => {
    try {
      fn(v);
    } catch {
    }
  });
  function onVersion(fn) {
    versionHooks.add(fn);
    return () => {
      versionHooks.delete(fn);
    };
  }
  var signedOutHooks = /* @__PURE__ */ new Set();
  var fireSignedOut = () => signedOutHooks.forEach((fn) => {
    try {
      fn();
    } catch {
    }
  });
  function onSignedOut(fn) {
    signedOutHooks.add(fn);
    return () => {
      signedOutHooks.delete(fn);
    };
  }
  var SIGNED_OUT = "signed-out";
  function saySignedOut() {
    post({ type: SIGNED_OUT });
    try {
      if (typeof window !== "undefined" && window.parent && window.parent !== window) window.parent.postMessage({ type: "edge-session", event: SIGNED_OUT }, location.origin);
    } catch {
    }
  }
  var role = "app";
  var parentListening = false;
  function setRole(r) {
    role = r;
    listen();
    if (r === "shell" && !parentListening && typeof addEventListener === "function") {
      parentListening = true;
      addEventListener("message", ((e) => {
        try {
          if (e.origin !== location.origin || e.data?.type !== "edge-session" || e.data?.event !== SIGNED_OUT) return;
        } catch {
          return;
        }
        fireSignedOut();
      }), PAGE_LONG);
    }
  }
  function reloadPage() {
    try {
      if (role === "app" && typeof location !== "undefined" && typeof location.reload === "function") location.reload();
    } catch {
    }
  }
  var entitlements = null;
  var listening = false;
  function listen() {
    if (listening) return;
    listening = true;
    try {
      if (typeof BroadcastChannel === "undefined") return;
      const c = new BroadcastChannel(CHANNEL);
      c.onmessage = (ev) => {
        if (ev?.data?.from === PAGE_ID) return;
        const t = ev?.data?.type;
        if (t === "entitlements" || t === "cleared") clients.forEach((fn) => fn());
        if (t === "entitlements") fireVersion(typeof ev?.data?.version === "string" ? ev.data.version : null);
        if (t === SIGNED_OUT) fireSignedOut();
        if (t === "cleared") {
          clearArea("session", !!ev?.data?.signOut);
          clearedHooks.forEach((fn) => {
            try {
              fn();
            } catch {
            }
          });
          if (role === "app") {
            fireResets();
            reloadPage();
          }
        }
      };
      c.unref?.();
    } catch {
    }
  }
  function noteVersion(res) {
    let v = null;
    try {
      v = res.headers?.get?.(ENTITLEMENTS_HEADER) ?? null;
    } catch {
      v = null;
    }
    if (!v || v === entitlements) return;
    const first = entitlements === null;
    entitlements = v;
    if (!first) {
      clients.forEach((fn) => fn());
      post({ type: "entitlements", version: v });
      fireVersion(v);
    }
  }
  var WRITE = /* @__PURE__ */ new Set(["POST", "PUT", "PATCH", "DELETE"]);
  function sessionClient(fetchImpl) {
    const f = fetchImpl ?? ((...a) => fetch(...a));
    let p = null, now = null;
    let identity = "";
    const catalogs = /* @__PURE__ */ new Map();
    let catalogGen = 0;
    const dropCatalogs = () => {
      catalogs.clear();
      catalogGen++;
    };
    const catalogStamp = () => `${entitlements ?? ""}
${identity}`;
    const invalidate = () => {
      p = null;
      now = null;
      dropCatalogs();
    };
    clients.add(invalidate);
    listen();
    resets.add(dropCatalogs);
    memoryClears.add(dropCatalogs);
    let guests = false;
    async function guestRead() {
      let res;
      try {
        res = await f(GUEST_URL, { credentials: "same-origin" });
      } catch {
        return null;
      }
      const d = await res.json().catch(() => null);
      if (!res.ok || d?.visitor !== true) return null;
      noteVersion(res);
      return { login: "", ownerKey: null, csrf: "", access: d?.access ?? null, raw: d, guest: true };
    }
    const session = () => p || (p = (async () => {
      let res;
      try {
        res = await f(SESSION_URL, { credentials: "same-origin" });
      } catch {
        throw new SessionError(null, "EDGE could not be reached. Check the connection and try again.");
      }
      if (!res.ok) {
        const e = await errorOf(res);
        const visitor = res.status === 401 && guests ? await guestRead() : null;
        if (visitor) {
          if (identity && identity !== GUEST_IDENTITY) {
            fireResets();
            reloadPage();
          }
          const was = lastLogin();
          if (was && was !== GUEST_IDENTITY) void clearUserState({ keepStampsOf: was });
          try {
            areaOf("local")?.setItem(LAST_LOGIN_KEY, GUEST_IDENTITY);
          } catch {
          }
          if (!identity) identity = GUEST_IDENTITY;
          now = visitor;
          return visitor;
        }
        if (res.status === 401) saySignedOut();
        throw new SessionError(e, accessText(e) || `EDGE answered ${res.status}.`);
      }
      noteVersion(res);
      const d = await res.json().catch(() => ({}));
      const owner = d?.owner_key ?? d?.access?.owner_key;
      const s = {
        login: String(d?.login || ""),
        ownerKey: typeof owner === "string" && owner ? owner : null,
        csrf: String(d?.csrf_token || ""),
        access: d?.access ?? null,
        raw: d
      };
      const id = identityOf(s.login, s.ownerKey);
      if (identity && id !== identity && s.ownerKey && identity === norm(s.login)) {
        migrateIdentity(identity, id);
        identity = id;
      }
      if (identity === GUEST_IDENTITY) {
        fireResets();
        reloadPage();
        const e = readError(401, { error: { code: "USER_CHANGED", message: "You signed in to EDGE. Reload the page to continue with your account." } });
        throw new SessionError(e, e.message);
      }
      if (identity && id !== identity) {
        fireResets();
        void clearUserState();
        reloadPage();
        const e = readError(401, { error: { code: "USER_CHANGED", message: "Another EDGE account signed in on this browser. Reload the page to continue as that account." } });
        throw new SessionError(e, e.message);
      }
      checkUser(s.login, s.ownerKey, { seed: d?.access?.seed === true });
      if (!identity) identity = id;
      now = s;
      return s;
    })().catch((e) => {
      p = null;
      throw e;
    }));
    const changed = (message = "Another EDGE account signed in on this browser. Reload the page to continue as that account.") => new Response(JSON.stringify({ error: { code: "USER_CHANGED", message, details: {} } }), { status: 401, headers: { "Content-Type": "application/json" } });
    async function send(url, init = {}, retried = false, expected = identity) {
      const method = String(init.method || "GET").toUpperCase();
      const write = WRITE.has(method);
      const headers = { ...init.headers || {} };
      if (write) {
        if (retried && !expected) return changed();
        try {
          headers["X-CSRF-Token"] = (await session()).csrf;
        } catch (e) {
          if (e instanceof SessionError && e.error?.code === "USER_CHANGED") return changed(e.message);
          throw e;
        }
        if (!retried && !expected) expected = identity;
        if (expected && identity !== expected) return changed();
      }
      const res = await f(url, { credentials: "same-origin", ...init, method, headers });
      noteVersion(res);
      if (res.status === 401) {
        invalidate();
        saySignedOut();
      }
      if (res.status === 403 && write && !retried) {
        const e = await errorOf(res.clone());
        if (e.kind === "csrf") {
          invalidate();
          return send(url, init, true, expected);
        }
      }
      return res;
    }
    function access() {
      const a = now?.access;
      if (!a || typeof a !== "object" || Array.isArray(a)) return null;
      return {
        ...a,
        capabilities: Array.isArray(a.capabilities) ? a.capabilities.filter((c) => typeof c === "string") : [],
        limits: a.limits && typeof a.limits === "object" && !Array.isArray(a.limits) ? a.limits : {}
      };
    }
    function can(key) {
      const caps = access()?.capabilities ?? [];
      if (caps.includes("*")) return true;
      return !!key && !isItemKey(key) && caps.includes(key);
    }
    function limit(key) {
      const v = access()?.limits?.[key];
      if (typeof v === "number" && Number.isFinite(v)) return v;
      if (Array.isArray(v)) return v.filter((x) => typeof x === "string");
      return void 0;
    }
    function catalog(kind) {
      return identity ? catalogOf(kind) : session().then(() => catalogOf(kind));
    }
    function catalogOf(kind) {
      const hit = catalogs.get(kind);
      if (hit && hit.stamp === catalogStamp()) return hit.answer;
      const gen = catalogGen;
      const entry = { stamp: catalogStamp(), answer: null };
      entry.answer = (async () => {
        let res;
        try {
          res = await send(CATALOG_URL + encodeURIComponent(kind));
        } catch {
          throw new SessionError(null, "EDGE could not be reached. Check the connection and try again.");
        }
        if (!res.ok) {
          const e = await errorOf(res);
          throw new SessionError(e, accessText(e) || e.message || `EDGE answered ${res.status}.`);
        }
        const d = await res.json().catch(() => null);
        const entries = Array.isArray(d?.entries) ? d.entries.filter((x) => x && typeof x.id === "string").map((x) => Object.freeze({ id: x.id, stage: typeof x.stage === "string" ? x.stage : "lab" })) : [];
        if (gen === catalogGen && catalogs.get(kind) === entry) entry.stamp = catalogStamp();
        return Object.freeze({ kind: typeof d?.kind === "string" ? d.kind : kind, entries: Object.freeze(entries) });
      })();
      entry.answer.catch(() => {
        if (catalogs.get(kind) === entry) catalogs.delete(kind);
      });
      catalogs.set(kind, entry);
      return entry.answer;
    }
    return {
      session,
      send,
      invalidate,
      access,
      can,
      limit,
      catalog,
      get current() {
        return now;
      },
      /** track guest: this page may run as a visitor without an account (the Terminal); call before the first read */
      allowGuest() {
        guests = true;
      },
      /** track guest: the session read is a visitor's (the guest plan's access), not an account's */
      get guest() {
        return !!now?.guest;
      },
      /** the identity this page opened with ('' before its first session read): owner:<owner key>, else the login */
      get identity() {
        return identity;
      },
      /** the shell only, on its own sign-out or sign-in: the next session read is a new identity, not a change of user */
      forget() {
        invalidate();
        identity = "";
      }
    };
  }
  var edge = sessionClient();
  var SYNC_KEYS = Object.freeze(STORAGE.filter((e) => e.sync && e.match === "exact" && e.area === "local").map((e) => e.key));
  var PREFERENCES_URL = "/api/v1/preferences";
  var DEFAULT_VALUE_BYTES = 65536;
  var asText = (v) => v == null ? null : typeof v === "string" ? v : JSON.stringify(v);
  var jsonBytes = (v) => {
    try {
      return new TextEncoder().encode(JSON.stringify(v)).length;
    } catch {
      return v.length * 3;
    }
  };
  function preferences(client, opts = {}) {
    const delay = opts.delayMs ?? 1e3;
    const state = /* @__PURE__ */ new Map();
    const timers = /* @__PURE__ */ new Map();
    const refused = /* @__PURE__ */ new Set();
    let on = false, listening2 = false, valueBytes = DEFAULT_VALUE_BYTES;
    const local = () => areaOf("local");
    const onStorage = (e) => {
      if (!on || !e.key || e.newValue === null || !SYNC_KEYS.includes(e.key)) return;
      try {
        if (e.storageArea && e.storageArea !== local()) return;
      } catch {
      }
      note(e.key);
    };
    const keep = (key, value) => {
      try {
        if (value === null) local()?.removeItem(key);
        else if (local()?.getItem(key) !== value) local()?.setItem(key, value);
      } catch {
      }
    };
    async function put(key, again = true) {
      timers.delete(key);
      if (!on || refused.has(key)) return;
      let value = null;
      try {
        value = local()?.getItem(key) ?? null;
      } catch {
        value = null;
      }
      const was = state.get(key);
      if (value === null || value === (was?.value ?? null)) return;
      if (jsonBytes(value) > valueBytes) {
        refused.add(key);
        return;
      }
      if (!on) return;
      let res;
      try {
        res = await client.send(`${PREFERENCES_URL}/${encodeURIComponent(key)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value, version: was?.version ?? null })
        });
      } catch {
        return;
      }
      let body = null;
      try {
        body = await res.json();
      } catch {
        body = null;
      }
      if (!on) return;
      if (res.status === 200 || res.status === 201) {
        state.set(key, { value, version: typeof body?.version === "number" ? body.version : null });
        return;
      }
      const error = body?.error;
      if (res.status === 409 && error?.code === "PREFERENCE_CONFLICT") {
        const current = error.details?.current;
        if (current && typeof current.version === "number") {
          const server = asText(current.value);
          state.set(key, { value: server, version: current.version });
          keep(key, server);
        } else if (again) {
          state.delete(key);
          await put(key, false);
        }
        return;
      }
      if (res.status === 422 && error?.code === "PREFERENCE_LIMIT") refused.add(key);
      else if (res.status === 403 && isAccessRefusal(readError(res.status, body))) refused.add(key);
    }
    function note(key) {
      if (!on || !SYNC_KEYS.includes(key) || refused.has(key)) return;
      const t = timers.get(key);
      if (t) clearTimeout(t);
      timers.set(key, setTimeout(() => {
        void put(key);
      }, delay));
    }
    async function load(o = {}) {
      let res;
      try {
        res = await client.send(PREFERENCES_URL);
      } catch {
        return false;
      }
      if (!res.ok) {
        try {
          await res.text();
        } catch {
        }
        return false;
      }
      let body = null;
      try {
        body = await res.json();
      } catch {
        return false;
      }
      const items = body?.preferences;
      if (!items || typeof items !== "object" || Array.isArray(items)) return false;
      if (typeof body.limits?.value_bytes === "number") valueBytes = body.limits.value_bytes;
      state.clear();
      refused.clear();
      on = true;
      for (const [key, item] of Object.entries(items)) {
        if (!SYNC_KEYS.includes(key) || !item || typeof item.version !== "number") continue;
        const value = asText(item.value);
        state.set(key, { value, version: item.version });
        keep(key, value);
      }
      if (o.uploadLocal) for (const key of SYNC_KEYS) {
        let v = null;
        try {
          v = local()?.getItem(key) ?? null;
        } catch {
          v = null;
        }
        if (v !== null && !state.has(key)) await put(key);
      }
      if (!listening2 && typeof addEventListener === "function") {
        listening2 = true;
        addEventListener("storage", onStorage, PAGE_LONG);
      }
      return true;
    }
    function stop() {
      on = false;
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
      state.clear();
    }
    async function flush() {
      const keys = [...timers.keys()];
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
      await Promise.all(keys.map((k) => put(k)));
    }
    return { load, note, stop, flush, get active() {
      return on;
    }, state, refused };
  }
  var prefs = preferences(edge);
  return __toCommonJS(edge_session_exports);
})();
