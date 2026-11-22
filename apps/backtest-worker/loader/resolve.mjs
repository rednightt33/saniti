/* Module resolution for the Terminal's sources under Node (registered by register.mjs).
   The worker and its tests import the Terminal's TypeScript by relative path: the indicator formulas at run time
   (edge-bff/terminal/src/calc, through the shared core), its data readers in the parity tests (data/worker.ts). Those
   sources are written for Vite, which resolves a relative import without an extension ('./timeframe'); Node resolves a
   specifier only as written, so such an import, the Terminal's usual style, stopped the worker's tests from loading
   (ERRORS M249) and would stop the worker from starting once the formulas had one. Only where Node finds nothing, a
   relative specifier without an extension is tried as Vite tries it for TypeScript: <specifier>.ts, then
   <specifier>/index.ts. Anything Node resolves itself resolves as before, and anything neither finds fails with Node's
   own error. */
/* 3f checker TR-2, B3 (FUTURE_PLAN.md "Before the first lab item or tab"; the user's go 2026-11-22): the one registration
   point of the lab formulas. '@edge-lab' is the Terminal's src/lab/index.ts in every Node process that runs a formula
   (both workers, their compute threads, the registry generators: each imports '@edge-lab' first); a browser page build
   resolves it with its own alias (shared/release-filter.mjs labAlias: the formulas in the lab build, none.ts in the
   public one). The workers compute for principals by their allow, so they hold every formula, a lab one included. */
const LAB = new URL('../../edge-bff/terminal/src/lab/index.ts', import.meta.url).href;
const RELATIVE = /^\.\.?\//;
const NOT_FOUND = new Set(['ERR_MODULE_NOT_FOUND', 'ERR_UNSUPPORTED_DIR_IMPORT']);

/** the specifier's last path segment has an extension (a file name with a dot: 'x.ts', 'indRegistry.json') */
const hasExtension = specifier => /\.[^./]+$/.test(specifier.split('/').pop());

export async function resolve(specifier, context, next) {
  if (specifier === '@edge-lab') return next(LAB, context);
  try {
    return await next(specifier, context);
  } catch (error) {
    if (!NOT_FOUND.has(error?.code) || !RELATIVE.test(specifier) || hasExtension(specifier)) throw error;
    for (const candidate of [`${specifier}.ts`, `${specifier}/index.ts`]) {
      try {
        return await next(candidate, context);
      } catch (e) {
        if (!NOT_FOUND.has(e?.code)) throw e;
      }
    }
    throw error;
  }
}
