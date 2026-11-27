/* EDGE Design System — number formats and hand-made SVG charts, as EDGE's pages write them.
   Plain browser script: sets window.EdgeDS. In a Vite/TypeScript page, copy the functions you need into the page's
   model.ts (EDGE's pages keep their own copies; this file is the reference, not a shared runtime dependency).
   Sources: apps/edge-bff/overview/src/model.ts (sign, num, pct, rp, amount, cls, colorOf),
   overview/src/app.ts (spark 64×26, lineChart, ticks 1/2/2.5/5/10), watchlist/src/model.ts (fluid spark),
   apps/edge-bff/shared/focus-modality.ts and company-name.ts (trackFocusModality, companyName; 2026-11-27). */
(function (G) {
  'use strict';
  /* ---------------- numbers (decision 7: en-US digits, U+2212 minus, Rp with T/B/M) ---------------- */
  var MINUS = '−';
  function sign(v) { return v > 0 ? '+' : v < 0 ? MINUS : ''; }
  function num(v, d) { if (v == null) return '—'; d = d == null ? 2 : d; return (v < 0 ? MINUS : '') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function pct(v, d) { return v == null ? '—' : sign(v) + Math.abs(v).toFixed(d == null ? 2 : d) + '%'; }
  function price(v) { return v == null ? '—' : Math.round(v).toLocaleString('en-US'); }
  /* the unit is chosen after rounding: the largest of T, B, M whose rounded value is at least 1 */
  function scaled(a, decimals) {
    var U = [['T', 1e12], ['B', 1e9], ['M', 1e6]];
    for (var i = 0; i < U.length; i++) { var x = a / U[i][1], d = decimals(U[i][0], x), r = Number(x.toFixed(d)); if (r >= 1) return r.toFixed(d) + U[i][0]; }
    return null;
  }
  /** "Rp 8.15T", "Rp 116.6B", "−Rp 4.2M"; signed=true writes "+" too */
  function rp(v, signed) {
    if (v == null) return '—';
    var a = Math.abs(v), s = signed ? sign(v) : v < 0 ? MINUS : '';
    return s + 'Rp ' + (scaled(a, function (u) { return u === 'T' ? 2 : 1; }) || Math.round(a).toLocaleString('en-US'));
  }
  /** short amount inside a tile or bar row: "+1.23T", "−523B"; under Rp 1 million "0" */
  function amount(v) {
    if (v == null) return '—';
    var a = Math.abs(v); if (a < 1e6) return '0';
    return sign(v) + scaled(a, function (u, x) { return u === 'T' ? (x >= 9.995 ? 1 : 2) : 0; });
  }
  function cls(v) { return v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : ''; }
  /** "Mon 17 Nov" from an ISO date (the data-date pills and tooltips) */
  function dateLabel(iso, withYear) {
    var d = new Date(iso + 'T00:00:00Z');
    return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: withYear ? 'numeric' : undefined, timeZone: 'UTC' }).replace(',', '');
  }

  /* ---------------- colour scale of a % change (treemap, heatmap cells): seven steps ---------------- */
  /** [background, text] for a % change; signed=true: anything above/below 0 is at least the light green/red step */
  function changeColor(c, signed) {
    if (c >= 3) return ['var(--green-600)', '#fff'];
    if (c >= 1.5) return ['var(--green-500)', '#fff'];
    if (c >= 0.5 || (signed && c > 0)) return ['var(--green-300)', 'var(--gray-900)'];
    if (c > -0.5 && !(signed && c < 0)) return ['var(--gray-200)', 'var(--gray-900)'];
    if (c > -1.5) return ['var(--red-300)', 'var(--gray-900)'];
    if (c > -3) return ['var(--red-500)', '#fff'];
    return ['var(--red-600)', '#fff'];
  }

  /* ---------------- SVG charts ---------------- */
  /** KPI sparkline 64×26 (Overview): up colour when last >= first, else down; or a fixed colour */
  function spark(vals, opt) {
    opt = opt || {}; var w = opt.w || 64, h = opt.h || 26, v = vals.filter(function (x) { return x != null; });
    if (v.length < 2) return '';
    var lo = Math.min.apply(null, v), hi = Math.max.apply(null, v), sp = hi - lo || 1;
    var pts = vals.map(function (x, i) { return x == null ? null : (i / (vals.length - 1) * w).toFixed(1) + ',' + (h - 2 - (x - lo) / sp * (h - 4)).toFixed(1); }).filter(Boolean).join(' ');
    var col = opt.color || (v[v.length - 1] >= v[0] ? 'var(--up)' : 'var(--down)');
    return '<svg class="sp" width="' + w + '" height="' + h + '" aria-hidden="true"><polyline points="' + pts + '" fill="none" stroke="' + col + '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }
  /** fluid trend line (Watchlist card 100%×40): stretches to the box width, stroke stays 1.6px */
  function trend(vals, h) {
    h = h || 40; var W = 300, v = vals.filter(function (x) { return x != null; });
    if (v.length < 2) return '<div class="nospark"></div>';
    var lo = Math.min.apply(null, v), hi = Math.max.apply(null, v), sp = hi - lo || 1;
    var d = vals.map(function (x, i) { return (i ? 'L' : 'M') + (i / (vals.length - 1) * W).toFixed(1) + ' ' + (h - 2 - (x - lo) / sp * (h - 4)).toFixed(1); }).join('');
    var col = v[v.length - 1] >= v[0] ? 'var(--up)' : 'var(--down)';
    return '<svg width="100%" viewBox="0 0 ' + W + ' ' + h + '" preserveAspectRatio="none" style="height:' + h + 'px" aria-hidden="true"><path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>';
  }
  /** "nice" ticks: steps of 1, 2, 2.5, 5 × 10^n, about n of them */
  function ticks(lo, hi, n) {
    var span = hi - lo || 1, raw = span / (n || 4), p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    var step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p, out = [];
    for (var t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) out.push(+t.toFixed(10));
    return out;
  }
  /** multi-line chart (Overview line engine): series [{name, color, values, w?, dash?}], x labels [iso dates];
      returns SVG; grid var(--chart-grid), zero line var(--chart-base), labels .ax, y labels formatted by fy */
  function lines(series, dates, opt) {
    opt = opt || {}; var W = opt.w || 520, H = opt.h || 200, L = opt.left || 40, R = W - 4, T = 6, B = H - 18;
    var fy = opt.fy || function (v) { return pct(v, 0); }, all = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (v != null) all.push(v); }); });
    var lo = Math.min.apply(null, all.concat(opt.zero ? [0] : [])), hi = Math.max.apply(null, all.concat(opt.zero ? [0] : []));
    var pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
    var n = dates.length, x = function (i) { return L + i / (n - 1) * (R - L); }, y = function (v) { return T + (hi - v) / (hi - lo) * (B - T); };
    var g = ticks(lo, hi, 4).map(function (t) { return '<line x1="' + L + '" x2="' + R + '" y1="' + y(t).toFixed(1) + '" y2="' + y(t).toFixed(1) + '" stroke="' + (t === 0 ? 'var(--chart-base)' : 'var(--chart-grid)') + '"/><text class="ax" x="' + (L - 6) + '" y="' + (y(t) + 3.5).toFixed(1) + '" text-anchor="end">' + fy(t) + '</text>'; }).join('');
    var k = (R - L) < 170 ? 2 : (R - L) < 260 ? 3 : 4;
    for (var j = 0; j < k; j++) { var i = Math.round(j * (n - 1) / (k - 1)); g += '<text class="ax" x="' + x(i).toFixed(1) + '" y="' + (H - 4) + '" text-anchor="' + (j === 0 ? 'start' : j === k - 1 ? 'end' : 'middle') + '">' + dateLabel(dates[i]).replace(/^\w+ /, '') + '</text>'; }
    series.forEach(function (s) {
      var d = '', pen = false;
      s.values.forEach(function (v, i) { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true; });
      g += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="' + (s.w || 1.6) + '" stroke-linejoin="round"' + (s.dash ? ' stroke-dasharray="4 3"' : '') + '/>';
    });
    return '<svg width="100%" viewBox="0 0 ' + W + ' ' + H + '" style="display:block" role="img" aria-label="' + (opt.label || 'chart') + '">' + g + '</svg>';
  }
  /** horizontal value bars (ranking, foreign net): rows [{label, value, text?}] */
  function hbars(rows, opt) {
    opt = opt || {}; var mx = Math.max.apply(null, rows.map(function (r) { return Math.abs(r.value); })) || 1;
    return '<div class="hbars">' + rows.map(function (r) {
      var col = opt.color || (r.value < 0 ? 'var(--down)' : 'var(--up)');
      return '<div class="hbar"><span class="sym">' + r.label + '</span><div class="trk"><i style="width:' + (Math.abs(r.value) / mx * 100).toFixed(1) + '%;background:' + col + '"></i></div><span class="val ' + (opt.neutral ? '' : cls(r.value)) + '">' + (r.text || pct(r.value, 1)) + '</span></div>';
    }).join('') + '</div>';
  }
  /** "k of N days" columns (Flow day counts): values [k] per session, N boxes high */
  function kofn(values, N) {
    return '<div class="kofn" role="img" aria-label="days out of ' + N + '">' + values.map(function (k) {
      var c = ''; for (var j = N - 1; j >= 0; j--) c += '<i' + (j < k ? ' class="on"' : '') + '></i>'; return '<div class="col">' + c + '</div>';
    }).join('') + '</div>';
  }
  /** one-row heat strip: signed values; colour = direction, opacity = size */
  function heat(values) {
    var m = Math.max.apply(null, values.map(Math.abs)) || 1;
    return '<div class="heat">' + values.map(function (v) { return '<i style="background:' + (v >= 0 ? 'var(--up)' : 'var(--down)') + ';opacity:' + (0.18 + 0.82 * Math.abs(v) / m).toFixed(2) + '" title="' + sign(v) + Math.abs(v) + '"></i>'; }).join('') + '</div>';
  }

  /* ---------------- decision 13 and UD71 (the user 2026-11-27): the reference copies of apps/edge-bff/shared ---------------- */
  /** the focus ring follows the last input: data-modality="pointer" | "keyboard" on <html> (shared/focus-modality.ts);
      the canonical layer turns --focus-ring transparent under "pointer" */
  function trackFocusModality(win) {
    var root = win.document.documentElement, set = function (m) { if (root.dataset.modality !== m) root.dataset.modality = m; };
    win.addEventListener('pointerdown', function () { set('pointer'); }, true);
    win.addEventListener('keydown', function (e) { if (!e.ctrlKey && !e.altKey && !e.metaKey) set('keyboard'); }, true);
  }
  /** a company name the source writes "Pt …" shows as "PT …" (shared/company-name.ts) */
  function companyName(name) { return typeof name === 'string' && name.indexOf('Pt ') === 0 ? 'PT ' + name.slice(3) : name; }

  G.EdgeDS = { MINUS: MINUS, sign: sign, num: num, pct: pct, price: price, rp: rp, amount: amount, cls: cls, dateLabel: dateLabel,
               changeColor: changeColor, spark: spark, trend: trend, ticks: ticks, lines: lines, hbars: hbars, kofn: kofn, heat: heat,
               trackFocusModality: trackFocusModality, companyName: companyName };
})(typeof window !== 'undefined' ? window : this);
