"""Mutation check of the delete-replaced rules (EXEC-PUBLISHER-SPEED, 2026-10-29): each mutant must fail at least one
test of apps/terminal-publisher/tests. Works on a copy. Usage: mutate_delete_replaced.py PYTHON (a venv with the
publisher's requirements-dev.txt)."""
import shutil, subprocess, sys, tempfile, pathlib
SRC = pathlib.Path(__file__).resolve().parents[3] / 'apps' / 'terminal-publisher'
PY = sys.argv[1]
MUTANTS = {
    'no wait': ("        wait(self.delete_after)\n", "\n"),
    'no floor': ("self.delete_after = max(MIN_DELETE_AFTER_SECONDS, int(", "self.delete_after = max(0, int("),
    'named keys not protected': ("        return gone - named_now", "        return gone"),
    'index part dropped': ("            gone |= index_keys(entries) - index_keys(indexes.get(family))", "            pass"),
    'manifest part dropped': ("                gone |= was - named_keys(self.manifests[ticker])", "                pass"),
    'held-manifest guard dropped': ("            if ticker in self.manifests:                          # a manifest this run no longer holds replaced nothing\n                gone |= was - named_keys(self.manifests[ticker])",
                                    "            if True:\n                gone |= was - named_keys(self.manifests.get(ticker))"),
    'guard and reset both dropped': None,
    'reset after failure dropped': ("self.manifests, self.changed, self.loaded_named = {}, set(), {}", "self.manifests, self.changed = {}, set()"),
    'still_current dropped in delete': ("            if not self.still_current():\n                log('replaced_skipped'", "            if False:\n                log('replaced_skipped'"),
    'still_current dropped in sweep': ("            if not self.still_current():\n                log('gc_skipped', reason='a newer publication came out after this run')",
                                       "            if False:\n                log('gc_skipped', reason='a newer publication came out after this run')"),
    'sweep_due ignores manual': ("    return mode == 'daily' and not manual and near_time(", "    return mode == 'daily' and near_time("),
    'sweep_due ignores mode': ("    return mode == 'daily' and not manual and near_time(", "    return not manual and near_time("),
    'sweep_due ignores time': ("and not manual and near_time(run_times(os.environ.get('TERMINAL_SWEEP_WIB') or SWEEP_WIB), now)", "and not manual"),
    'main ignores sweep_due': ("    sweep = sweep_due(mode, manual, started)", "    sweep = None"),
    'cleanup mode does nothing': ("        Publisher(None, Bucket()).collect_garbage()\n        return 0", "        return 0"),
    'no MaxKeys': ("'MaxKeys': LIST_PAGE_KEYS,", ""),
    'slow page never logged': ("            if took > SLOW_PAGE_SECONDS:", "            if False:"),
    'listed never logged': ("                log('listed', prefix=prefix,", "                (lambda **k: None)(prefix=prefix,"),
    'retry request dropped': ("**({'request': what} if what else {})", ""),
    'indexed folders not listed': ("            prefixes = sorted(families | set(INDEXED))", "            prefixes = sorted(families)"),
    'keep_manifest forgets reads': ("        self.loaded_named[ticker] = named_keys(m)", "        pass"),
    'wait before state.json skipped (delete first)': ("        log('replaced_wait', objects=len(self.replaced), seconds=self.delete_after)\n        wait(self.delete_after)\n",
                                                      "        log('replaced_wait', objects=len(self.replaced), seconds=self.delete_after)\n"),
}
g, r = MUTANTS['held-manifest guard dropped'], MUTANTS['reset after failure dropped']
MUTANTS['guard and reset both dropped'] = [g, r]
results = {}
MUTANTS = {'(baseline, no mutation)': ('', ''), **MUTANTS}
for name, pair in MUTANTS.items():
    pairs = pair if isinstance(pair, list) else [pair]
    with tempfile.TemporaryDirectory() as d:
        # the copy sits at apps/terminal-publisher of a tree whose other apps are the real ones (cross-service tests)
        root = pathlib.Path(d)
        (root / 'apps').mkdir()
        for other in SRC.parent.iterdir():
            if other.name != SRC.name:
                (root / 'apps' / other.name).symlink_to(other)
        dst = root / 'apps' / SRC.name
        shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        f = dst / 'publisher.py'
        s = f.read_text()
        bad = [s.count(old) for old, _ in pairs if old and s.count(old) != 1]
        if bad:
            results[name] = f'NOT APPLIED (found {bad})'; continue
        for old, new in pairs:
            if old:
                s = s.replace(old, new)
        f.write_text(s)
        r = subprocess.run([PY, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'], cwd=dst, capture_output=True, text=True, timeout=600)
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
        failed = [l.split('::')[1].split(' ')[0] for l in r.stdout.splitlines() if l.startswith('FAILED')]
        results[name] = (f'KILLED {len(failed)} ' + ', '.join(failed[:3]) if failed else last) if r.returncode else 'SURVIVED ' + last
for k, v in results.items():
    print(f'{k:48s} {v}')
