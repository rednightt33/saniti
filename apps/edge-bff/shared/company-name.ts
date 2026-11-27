/* A company's name as EDGE shows it (the user 2026-11-27, UD71: "Untuk nama perusahaan PT, tambah satu aturan tampilan
   saja"; ERRORS M575 D-5). IDX_Stock_Universe."Company Name" holds 3 of 862 names that start "Pt " (AADI "Pt Adaro
   Andalan Indonesia Tbk", DKHH "Pt Cipta Sarana Medika Tbk.", YUPI "Pt Yupi Indo Jelly Gum Tbk"): every page shows them
   as "PT …", the legal form's own spelling. Only the display changes: the database, the publisher's files and what a
   page sends back keep the source's text. Every page that shows a company name reads it through this function
   (tests/test_company_name.py lists where). */

/** The name with a leading "Pt " shown as "PT "; any other text, null or undefined as it is. */
export function companyName<T extends string | null | undefined>(name: T): T {
  return (typeof name === 'string' && name.startsWith('Pt ') ? `PT ${name.slice(3)}` : name) as T;
}
