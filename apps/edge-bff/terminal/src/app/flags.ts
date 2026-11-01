/* User 2026-11-01 (search screenshot of the bonds): "untuk logo, tambahkan logo Indonesia dan US ya di search bar". A
   government bond shows its country's flag where a stock shows its logo (search, symbol pill, asset badges). Which
   country a bond belongs to comes from the data (ref/fixed_income `country`); only the drawing of a flag is written
   here. A country without a drawing keeps the monogram, so a new country's bonds still show, with their first letters. */
const svg = (body: string) => `<svg viewBox="0 0 30 20" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${body}</svg>`;

/** country name as ref/fixed_income writes it → its flag (SVG, drawn to fill a round avatar) */
export const FLAGS: Record<string, string> = {
  Indonesia: svg('<rect width="30" height="10" fill="#ce1126"/><rect y="10" width="30" height="10" fill="#fff"/>'),
  'United States': svg(
    Array.from({ length:13 }, (_, i) => `<rect y="${(i * 20 / 13).toFixed(3)}" width="30" height="${(20 / 13 + .02).toFixed(3)}" fill="${i % 2 ? '#fff' : '#b22234'}"/>`).join('')
    + '<rect width="13" height="10.77" fill="#3c3b6e"/>'
    + Array.from({ length:4 }, (_, r) => Array.from({ length:5 }, (_, c) => `<circle cx="${1.5 + c * 2.5}" cy="${1.6 + r * 2.5}" r=".55" fill="#fff"/>`).join('')).join('')),
};

/** the flag of a country, or null (no drawing: the caller keeps the monogram) */
export const flagOf = (country: string | undefined | null) => (country && FLAGS[country]) || null;
