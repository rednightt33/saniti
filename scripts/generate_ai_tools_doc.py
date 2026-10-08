"""Write AI_TOOLS.md: every tool the market-ai-orc model can call, every session helper of the Python sandbox and every
method guide, with the switch that turns each on and a plain-language summary (round 2026-10-03, A3).

Derived from the code, not written by hand:
- model tools: market-ai-orc's registry built with every switch on, then once with each switch off; a tool that
  disappears needs that switch, a tool that appears only with a switch off is the older path the switch replaces;
- session helpers: HELPERS and RESEARCH_HELPERS of apps/market-python-sandbox/app/sessions.py and EXTRA_HELPERS of
  runtime/saniti_session.py, read with ast (the sandbox is not imported);
- method guides: GUIDES of apps/market-ai-orc/app/method_guides.py.
The only hand-written part is PLAIN, one sentence per name; the generator fails on a name without a sentence or a
sentence for a name that no longer exists. market-ai-orc tests/test_ai_tools_doc.py fails when AI_TOOLS.md drifts.

The dev snapshot (which switches are on) is live state, not code: pass --flags with a JSON object of AI_ENABLE_*
names to true/false (names and booleans only, e.g. from `railway variables --kv`, never other values). Without --flags
the snapshot already in AI_TOOLS.md is kept.

Usage (from apps/market-ai-orc, its venv): python ../../scripts/generate_ai_tools_doc.py [--flags flags.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "AI_TOOLS.md"
SNAPSHOT_START = "<!-- dev-snapshot:start -->"
SNAPSHOT_END = "<!-- dev-snapshot:end -->"

# switch name -> build_default_registry argument
SWITCHES = {
    "AI_ENABLE_LOOKUP_FACT": "lookup_fact_enabled", "AI_ENABLE_REQUEST_DATA": "request_data_enabled",
    "AI_ENABLE_DATANEED": "dataneed_enabled", "AI_ENABLE_STANDARD_PERIOD_RETURN": "standard_period_return",
    "AI_ENABLE_EVENT_STUDY": "event_study", "AI_ENABLE_HYPOTHESIS_PLAN": "hypothesis_plan",
    "AI_ENABLE_METHOD_GUIDES": "method_guides", "AI_ENABLE_CATALOG_DISCOVERY_V2": "catalog_discovery_v2",
    "AI_ENABLE_PLAN_FEASIBILITY": "plan_feasibility", "AI_ENABLE_COMPOSITE_KEYS": "composite_keys",
    "AI_ENABLE_POINT_IN_TIME": "point_in_time", "AI_ENABLE_RESEARCH_FINDINGS": "research_findings",
    "AI_ENABLE_PREFLIGHT_PARTS": "preflight_parts", "AI_ENABLE_MULTI_ANGLE_RESEARCH": "multi_angle",
    "AI_ENABLE_LINEAGE_TOOL": "lineage_tool", "AI_ENABLE_EXPORT": "export", "AI_ENABLE_QUERY_METRIC": "metrics",
    "AI_ENABLE_WEB_FACT": "web_fact_client",
    "AI_ENABLE_REFERENCE_LOOKUP": "reference_lookup", "AI_ENABLE_ADDRESS_MENU": "reference_check",
    "AI_ENABLE_WEB_RESEARCH": "web_research_client",
    "AI_ENABLE_RUN_MEMORY": "run_memory", "AI_ENABLE_MERGED_STEPS": "merged_steps",
}

# One plain-language sentence per name (Indonesian, for non-developers).
PLAIN = {
    # model tools
    "get_system_capabilities": "Melaporkan kemampuan dan alat apa saja yang sedang aktif.",
    "discover_catalog": "Mencari tabel data di katalog dari kata kunci (broker, harga, dan seterusnya).",
    "get_catalog_details": "Detail sampai 3 tabel: arti kolom, satuan, cara menyambung tabel, cakupan tanggal, rumus.",
    "read_catalog_rows": "Membaca isi lengkap satu tabel katalog, halaman per halaman.",
    "preview_table_rows": "Contoh maksimal 20 baris dari tabel pasar; hanya contoh, bukan untuk analisis.",
    "lookup_reference": "Membaca tabel referensi database (sektor, industri, profil emiten, data broker): daftar kolomnya, atau baris satu emiten / semua emiten dengan satu kategori / nama yang mengandung kata tertentu, maksimal 100 baris. Dipakai sebelum web; alat web ditolak untuk atribut yang ada di tabel ini sampai tabelnya dibaca.",
    "get_dimension_values": "Nilai persis sebuah kategori (misalnya ejaan 'Banks' atau 'Regular'), supaya saringan tidak salah tulis.",
    "request_data": "Jalur lama: query data langsung lewat SQL Governor (diganti alur DataNeed).",
    "lookup_fact": "Jalur lama: mengambil satu fakta pendek dari data (diganti alur DataNeed).",
    "submit_data_need_spec": "AI menyatakan data yang dibutuhkan (tabel, kolom, saringan, periode); sistem memeriksa sebelum data diambil.",
    "prepare_data_bundle": "Mengambil data yang sudah disetujui secara utuh dan memeriksa kelengkapannya.",
    "open_analysis_session": "Membuka ruang kerja Python di atas data yang sudah disiapkan.",
    "run_python": "Menjalankan hitungan di ruang kerja dengan alat bantu bawaan; setiap tabel hasil wajib membawa definisinya.",
    "inspect_session": "Melihat isi variabel di ruang kerja sebelum hasil dirilis, atau statistik semua kolom satu dataset (kosong, min/median/maks, celah) tanpa baris data.",
    "export_result": "Membuat file unduhan dari tabel hasil (CSV, XLSX dengan lembar definisi dan asal data, atau Parquet), maks. 20 MB; AI hanya melihat nama dan ukurannya.",
    "find_web_fact": "Mencari satu fakta yang tidak ada di data pasar (misalnya status BUMN, pemegang saham pengendali) di web dalam ± 30 detik; status ditentukan sistem dari kutipan persis (TERKONFIRMASI, BERTENTANGAN, SEBAGIAN, TIDAK DITEMUKAN).",
    "research_web": "Mencari informasi yang tidak ada di database (fakta, angka, peristiwa dengan tanggalnya, deret per periode, daftar) di web untuk konteks atau saat data tidak ada; banyak perusahaan dalam satu panggilan; hanya butir dengan kutipan persis, konflik palsu (beda periode/definisi) dibedakan dari konflik nyata, batas biaya per giliran; setiap butir bisa dikutip dan tampil sebagai fakta web dengan domainnya.",
    "check_references": "Memeriksa alamat angka (value reference) sebelum jawaban ditulis: menampilkan nilai yang akan muncul, atau kenapa alamat salah dan alamat yang ada; tanpa memanggil model dan tanpa mengambil data.",
    "query_metric": "Jalan pintas pertanyaan sederhana: metrik resmi (net beli asing, net beli per broker, volume, harga penutupan, tertinggi/terendah) dihitung langsung oleh database dalam satu panggilan per periode.",
    "read_conversation_memory": "Membaca memori run sebelumnya di percakapan yang sama (EXEC-C): memo, pesan, jawaban lengkap, catatan AI, rencana, setiap penolakan beserta drafnya, nilai desain dan asalnya, fakta web, kode, detail katalog, sumber angka, dan pikiran AI; per halaman, tanpa model dan tanpa data baru.",
    "get_lineage": "Menelusuri asal angka: tabel hasil, kode yang membuatnya, data yang dibaca, saringan baris, query Governor, dan tabel sumbernya; tanpa isi baris.",
    "get_session_output": "Membaca ulang tabel atau JSON hasil, termasuk dari giliran sebelumnya lewat ref (out.o3) setelah sandbox menghapusnya, dan kode yang dijalankan sebuah eksekusi.",
    "complete_analysis": "Menutup analisis: sistem memeriksa kelengkapan data dan definisi, lalu merilis hasil yang boleh dikutip.",
    "check_data_feasibility": "Sebelum mengajukan rencana riset, mengecek data ada dan ukurannya muat (tanpa membaca data).",
    "get_research_library": "Daftar metode riset beserta aturan dan cara membaca hasilnya.",
    "check_research_feasibility": "Mengecek desain dan data setiap sudut riset sebelum rencana diajukan.",
    "start_research_run": "Menjalankan rencana riset yang disetujui: menyiapkan data per kelompok sudut.",
    "run_research_code": "Mencatat setiap sudut riset tepat satu kali dengan alat bantu riset.",
    "complete_research_run": "Sistem menghitung ulang statistik setiap sudut dan memberi vonis (SUPPORTED, INSUFFICIENT_EVIDENCE, NOT_RUN, dan seterusnya).",
    "get_method_guide": "Membuka buku panduan satu metode atau alat bantu.",
    "prepare_analysis_data": "Jalur lama (tanpa DataNeed): menyiapkan data analisis.",
    "create_analysis_spec": "Jalur lama (tanpa DataNeed): menulis spesifikasi analisis.",
    "run_python_analysis": "Jalur lama (tanpa DataNeed): menjalankan analisis Python sekali jalan.",
    "get_analysis_result": "Jalur lama (tanpa DataNeed): membaca hasil analisis.",
    "get_dataset_manifest": "Jalur lama (tanpa DataNeed): membaca daftar isi dataset yang disiapkan.",
    # session helpers
    "requests": "Daftar permintaan data di sesi ini.",
    "manifest": "Daftar isi data bundle (baris, rentang, kualitas).",
    "quality": "Catatan kualitas satu permintaan data (celah tanggal, nilai kosong).",
    "load": "Membaca satu permintaan data secara utuh.",
    "load_range": "Membaca satu rentang tanggal yang disetujui.",
    "in_period": "Penanda baris yang berada di dalam periode yang disetujui (tanpa baris pemanasan), untuk menghitung sampel.",
    "backtest": "Simulasi transaksi aturan beli/jual yang disebut user di harga database; dihitung ulang sistem.",
    "sql": "Query DuckDB atas data sesi.",
    "relation": "Data satu permintaan sebagai relasi DuckDB.",
    "load_output": "Membuka tabel hasil yang dirilis di giliran sebelumnya.",
    "carried": "Daftar tabel giliran sebelumnya yang bisa dibuka.",
    "join": "Menyambung dua permintaan lewat relasi katalog yang disetujui.",
    "resample": "Mengubah data harian menjadi mingguan/bulanan dengan aturan katalog.",
    "period_return": "Return untuk periode bernama (YTD, bulan, kuartal, tahun).",
    "event_study": "Event study: hasil setelah kejadian dibanding pembanding; dihitung ulang sistem, termasuk tabel alur.",
    "event_summary": "Ringkasan hipotesis dengan aturan sukses dari rencana yang disetujui.",
    "insufficient_data": "Menyatakan data tidak cukup untuk suatu hitungan, dengan alasannya.",
    "intermediate_path": "Lokasi file kerja sementara di sesi.",
    "emit_table": "Merilis tabel hasil beserta definisinya.",
    "emit_chart": "Merilis grafik.",
    "emit_json": "Merilis hasil JSON beserta definisinya.",
    "emit_text": "Merilis teks.",
    "emit_file": "Merilis file (Parquet, CSV, PNG, dan lain-lain).",
    "add_warning": "Menambah peringatan ke hasil.",
    "research_conditional": "Riset: hasil setelah kondisi dibanding tanpa kondisi.",
    "research_persistence": "Riset: apakah kondisi cenderung berlanjut (streak).",
    "research_group_comparison": "Riset: perbandingan antar kelompok atau rezim.",
    "research_quantiles": "Riset: peringkat kuantil dan selisih atas-bawah.",
    "research_temporal_dependency": "Riset: korelasi dan hubungan mendahului (lead-lag).",
    "research_custom": "Riset: rumus khusus yang tetap diperiksa sistem.",
    # method guides
    "free_code": "Panduan G1: analisis kode bebas.",
    "event_study_guide": "Panduan G2: event study.",
    "backtest_guide": "Panduan backtest: aturan masuk/keluar, konvensi pengisian order, dan tabel hasilnya.",
    "hypothesis_plan": "Panduan G3: rencana hipotesis dengan vonis backend.",
    "multi_angle": "Panduan G4: riset multi-sudut.",
    "reading_data": "Panduan membaca data bundle.",
    "resample_guide": "Panduan resample harian ke mingguan/bulanan.",
    "join_and_preaggregate": "Panduan menyambung dua permintaan.",
    "period_return_guide": "Panduan return per periode.",
}
# a guide that shares its name with a helper is listed under "<name>_guide" in PLAIN
GUIDE_ALIAS = {"event_study": "event_study_guide", "resample": "resample_guide", "period_return": "period_return_guide",
               "backtest": "backtest_guide"}


def _build(off: tuple[str, ...] = ()):
    sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
    import httpx

    from app import research_library
    from app.tools import build_default_registry
    from app.tools import method_guides
    from app.tools.analysis import SandboxClient
    from app.tools.request_data import GovernorClient

    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    names = method_guides.active_guides(dataneed=True, event_study=True, hypothesis_plan=True, multi_angle=True,
                                        period_return=True, backtest=True)
    kwargs = {argument: True for argument in SWITCHES.values()}
    kwargs["backtest"] = True  # P32: offered when the sandbox reports the backtest capability (no switch)
    # EXEC-V 2026-10-08: the sessions one answer may keep open, from the sandbox's session_release (dev: four)
    kwargs["session_limit"] = 4
    kwargs["method_guides"] = {"names": names, "menu": method_guides.menu(names)}
    kwargs["multi_angle"] = {"max_groups": 2, "min_angles": 2, "max_angles": 5, "library": research_library.rows()}
    kwargs["metrics"] = [{"metric_id": "example", "label": "x", "description": "x", "source_table": "t",
                          "measure_column": "c", "time_function": "SUM", "entity_column": "e",
                          "default_dimensions": ["e"], "allowed_dimensions": ["e"], "default_scope": {"type": "ALL"},
                          "misuse_warning": "x", "review_status": "INFERRED", "unit": None}]
    from app.tools.web_fact import WebFactClient
    from app.tools.web_research import WebResearchClient

    kwargs["web_fact_client"] = WebFactClient("http://w", "w" * 40, transport=transport)
    kwargs["web_research_client"] = WebResearchClient("http://w", "w" * 40, transport=transport)
    kwargs["value_references"] = True  # AI_ENABLE_VALUE_REFERENCES: a description sentence, no tool of its own
    from app.run_memory import MemoryStore

    kwargs["run_memory"] = MemoryStore("postgresql://unused")  # EXEC-C: never connected while the registry is built
    for switch in off:
        argument = SWITCHES[switch]
        kwargs[argument] = None if argument in ("method_guides", "multi_angle", "metrics", "web_fact_client",
                                                "web_research_client", "run_memory") else False
    registry = build_default_registry(
        object(), cursor_secret=b"x" * 32,
        governor_client=GovernorClient("http://g", "k" * 40, 90, transport=transport),
        sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=transport), **kwargs)
    return registry


def _registry(off: tuple[str, ...] = ()) -> dict[str, dict]:
    return {d["name"]: d for d in _build(off).definitions()}


def _effects(off: tuple[str, ...] = ()) -> dict[str, str]:
    """O3: each offered tool's effect class; read-only steps derive their tools from it, so an unclassed tool is a
    defect."""
    registry = _build(off)
    effects = {name: registry.get(name).effect for name in registry.names()}
    unclassed = sorted(name for name, effect in effects.items() if effect is None)
    if unclassed:
        raise SystemExit(f"tools without an effect class (ToolSpec.effect): {unclassed}")
    return effects


def model_tools() -> list[dict]:
    full = _effects()
    needs: dict[str, list[str]] = {name: [] for name in full}
    replaced_by: dict[str, list[str]] = {}
    for switch in SWITCHES:
        without = _effects((switch,))
        for name in set(full) - set(without):
            needs[name].append(switch)
        for name in set(without) - set(full):
            replaced_by.setdefault(name, []).append(switch)
    older = {}
    for switch in SWITCHES:
        older.update(_effects((switch,)))
    rows = [{"name": n, "path": "current", "switches": sorted(needs[n]), "effect": full[n]} for n in full]
    rows += [{"name": n, "path": "older", "switches": sorted(s), "effect": older[n]}
             for n, s in sorted(replaced_by.items())]
    return rows


def _literal(path: Path, name: str):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"{name} not found in {path}")


def session_helpers() -> list[str]:
    sandbox = ROOT / "apps/market-python-sandbox"
    names = [re.match(r"[A-Za-z_]\w*", h).group(0) for h in _literal(sandbox / "app/sessions.py", "HELPERS")]
    for extra in [*_literal(sandbox / "app/sessions.py", "RESEARCH_HELPERS"),
                  *_literal(sandbox / "runtime/saniti_session.py", "EXTRA_HELPERS")]:
        if extra not in names:
            names.append(extra)
    return names


def method_guides() -> list[dict]:
    sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
    from app import method_guides as guides

    return [{"name": g["name"], "g": g.get("g"), "kind": g.get("kind"), "title": g.get("title")}
            for g in guides.GUIDES]


def desk_matrix() -> list[str]:
    """EXEC-T (2026-10-06): the tools of each process, from app/tool_desks.py over the registry with every switch on."""
    sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
    from app import tool_desks as desks

    effects = _effects()
    table = desks.matrix(frozenset(effects), effects.get)
    processes = list(desks.DESKS)
    lines = ["", "## Meja alat per proses (EXEC-T)", "",
             "Dibuat dari `apps/market-ai-orc/app/tool_desks.py` (`DESKS`), saklar semua menyala. H = wajib ada dan "
             "ditawarkan; B = boleh dan ditawarkan; X = tidak boleh: tidak ditawarkan, ditolak bila dipanggil, dan tidak "
             "disebut di laporan kemampuan atau buku panduan langkah itu; kosong = boleh tetapi tidak ditawarkan. Alat "
             "jalur lama dan `find_web_fact` (selama `research_web` aktif) X di semua proses.", "",
             "| Alat | " + " | ".join(desks.DESK_LABELS[p] for p in processes) + " |",
             "|---|" + "---|" * len(processes)]
    lines += [f"| `{name}` | " + " | ".join(row[p] for p in processes) + " |" for name, row in table.items()]
    return lines


def _plain(name: str) -> str:
    if name not in PLAIN:
        raise SystemExit(f"PLAIN has no sentence for {name!r}: add one in scripts/generate_ai_tools_doc.py")
    return PLAIN[name]


def render(snapshot: str) -> str:
    tools, helpers, guides = model_tools(), session_helpers(), method_guides()
    used = {t["name"] for t in tools} | set(helpers) | {GUIDE_ALIAS.get(g["name"], g["name"]) for g in guides}
    stale = sorted(set(PLAIN) - used)
    if stale:
        raise SystemExit(f"PLAIN has sentences for names that no longer exist: {stale}")
    lines = ["# Alat AI (dibuat dari kode)", "",
             "GENERATED by `scripts/generate_ai_tools_doc.py` from market-ai-orc's tool registry, the sandbox session "
             "helpers and the method guides; `apps/market-ai-orc/tests/test_ai_tools_doc.py` fails when this file and the "
             "code drift apart. Do not edit by hand: change the code or the PLAIN sentences, then regenerate "
             "(AGENTS.md, Mandatory workflow).", "",
             "## Alat yang bisa dipanggil model (market-ai-orc)", "",
             "Sifat: READS tidak mengubah apa pun; OWN_ARTIFACT hanya menulis catatan percakapan itu sendiri (bukti, file "
             "ekspor); FETCHES_WEB membaca fakta web publik; FETCHES_DATA menarik data gudang; COMPUTES membuka sesi atau menjalankan kode. Langkah "
             "baca (CLARIFY, CONVERSATIONAL) hanya memakai alat READS dan OWN_ARTIFACT.", "",
             "| Alat | Fungsi | Sifat | Jalur | Saklar yang dibutuhkan |", "|---|---|---|---|---|"]
    for tool in tools:
        path = "sekarang" if tool["path"] == "current" else "lama (muncul bila saklar ini mati)"
        switches = ", ".join(f"`{s}`" for s in tool["switches"]) or "selalu"
        lines.append(f"| `{tool['name']}` | {_plain(tool['name'])} | {tool['effect']} | {path} | {switches} |")
    lines += desk_matrix()
    lines += ["", "## Alat bantu di ruang kerja Python (market-python-sandbox)", "",
              "| Alat bantu | Fungsi |", "|---|---|"]
    lines += [f"| `{h}` | {_plain(h)} |" for h in helpers]
    lines += ["", "## Buku panduan metode (get_method_guide)", "", "| Panduan | Jalur | Jenis | Judul | Fungsi |",
              "|---|---|---|---|---|"]
    for g in guides:
        lines.append(f"| `{g['name']}` | {g['g'] or '-'} | {g['kind']} | {g['title']} | "
                     f"{_plain(GUIDE_ALIAS.get(g['name'], g['name']))} |")
    lines += ["", "## Snapshot saklar di dev", "", SNAPSHOT_START, snapshot.strip("\n"), SNAPSHOT_END, ""]
    return "\n".join(lines)


def snapshot_from_flags(flags: dict[str, bool], date: str) -> str:
    rows = [f"Diambil {date} dari Railway (nama dan nilai true/false saja).", "", "| Saklar | dev |", "|---|---|"]
    rows += [f"| `{name}` | {'on' if flags.get(name) else 'off'} |" for name in sorted(SWITCHES)]
    return "\n".join(rows)


def current_snapshot() -> str:
    if not TARGET.exists():
        return "Belum diambil."
    text = TARGET.read_text(encoding="utf-8")
    if SNAPSHOT_START not in text or SNAPSHOT_END not in text:
        return "Belum diambil."
    return text.split(SNAPSHOT_START, 1)[1].split(SNAPSHOT_END, 1)[0].strip("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flags", help="JSON file: AI_ENABLE_* name -> true/false (names and booleans only)")
    parser.add_argument("--date", help="date of the snapshot, e.g. 2026-10-03")
    args = parser.parse_args()
    snapshot = current_snapshot()
    if args.flags:
        flags = json.loads(Path(args.flags).read_text())
        if not all(isinstance(v, bool) for v in flags.values()):
            raise SystemExit("--flags must map names to true/false only")
        snapshot = snapshot_from_flags(flags, args.date or "")
    TARGET.write_text(render(snapshot), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
