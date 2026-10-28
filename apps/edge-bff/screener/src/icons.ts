/* The prototype's icon set (IC) and its svg helper, kept 1:1, plus the warning mark of the remarks (P4). */
export const ico = (d: string, s = '') => `<svg class="ico ${s}" viewBox="0 0 24 24">${d}</svg>`;
export const IC: Record<string, string> = {
  expand:'<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>', sliders:'<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  trend:'<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>', check:'<path d="m5 12 5 5 9-10"/>', filter:'<path d="M4 5h16l-6 7.5V19l-4 1v-7.5Z"/>',
  moon:'<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/>', eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  left:'<path d="m15 6-6 6 6 6"/>', right:'<path d="m9 6 6 6-6 6"/>', export:'<path d="M12 15V3m-4 4 4-4 4 4"/><path d="M5 13v6h14v-6"/>', plus:'<path d="M12 5v14M5 12h14"/>',
  x:'<path d="m6 6 12 12M18 6 6 18"/>', search:'<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>', chev:'<path d="m9 6 6 6-6 6"/>',
  save:'<path d="M5 4h12l2 2v14H5Z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/>', dl:'<path d="M12 3v12m-4-4 4 4 4-4"/><path d="M4 20h16"/>', send:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>', sort:'<path d="m8 9 4-4 4 4M8 15l4 4 4-4"/>', up:'<path d="M12 19V5m-5 5 5-5 5 5"/>',
  down:'<path d="M12 5v14m5-5-5 5-5-5"/>', copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  reset:'<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>', trash:'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9Z"/>', dup:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V5a1 1 0 0 1 1-1h11"/>',
  panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>', side:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  chart:'<path d="M4 19V5M4 19h16M7 15l4-5 3 3 5-7"/>', book:'<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z"/><path d="M8 7h7"/>',
  warn:'<path d="M12 4 2.5 20h19Z"/><path d="M12 10v4M12 17v.5"/>', terminal:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
};
/** the condition colours: c1-c6 of the design spec, then extras (the prototype's COLORS) */
export const COLORS = ['#0070f3', '#7928ca', '#f5a623', '#089981', '#e5484d', '#17348c', '#0ea5e9', '#db2777', '#65a30d', '#a16207'];
