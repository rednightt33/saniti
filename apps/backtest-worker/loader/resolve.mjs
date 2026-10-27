/* Module resolution for the Terminal's sources under Node (registered by register.mjs).
   The worker and its tests import the Terminal's TypeScript by relative path: the indicator formulas at run time
   (edge-bff/terminal/src/calc, through the shared core), its data readers in the parity tests (data/worker.ts). Those
   sources are written for Vite, which resolves a relative import without an extension ('./timeframe'); Node resolves a
   specifier only as written, so such an import, the Terminal's usual style, stopped the worker's tests from loading
   (ERRORS M249) and would stop the worker from starting once the formulas had one. Only where Node finds nothing, a
   relative specifier without an extension is tried as Vite tries it for TypeScript: <specifier>.ts, then
   <specifier>/index.ts. Anything Node resolves itself resolves as before, and anything neither finds fails with Node's
   own error. */
const RELATIVE = /^\.\.?\//;
const NOT_FOUND = new Set(['ERR_MODULE_NOT_FOUND', 'ERR_UNSUPPORTED_DIR_IMPORT']);

/** the specifier's last path segment has an extension (a file name with a dot: 'x.ts', 'indRegistry.json') */
const hasExtension = specifier => /\.[^./]+$/.test(specifier.split('/').pop());

export async function resolve(specifier, context, next) {
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
