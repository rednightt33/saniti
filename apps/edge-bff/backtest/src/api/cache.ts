/* The browser's file cache, shared with the Terminal: since EXEC-BACKTEST-LOAD (K3) one module for every page that reads
   the rack, apps/edge-bff/terminal/src/data/rack.ts (database 'terminal-files' version 1, store 'files', record {sha,
   bytes, size, used}, CACHE_LIMIT, least recently used first; any IndexedDB failure only means no cache). The page
   stores only bytes that passed inflateVerified (load.ts), and a cached file goes through inflateVerified again before it
   is used, so an entry whose bytes do not match the manifest is never used (the download that follows replaces it). */
export { CACHE_DB, CACHE_LIMIT, CACHE_STORE, CACHE_VERSION, fileCache, type FileCache } from '../../../terminal/src/data/rack.ts';
