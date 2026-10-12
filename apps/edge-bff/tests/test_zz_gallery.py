import json, os
from pathlib import Path
from test_browser import server  # noqa: F401
from test_visual import browser_page, dummy_orc, sign_in, submit, saved  # noqa: F401
OUT = Path(os.environ['GALLERY_OUT'])
FIX = json.loads((Path(__file__).parent / 'fixtures' / 'orc_responses.json').read_text())
MD = ("Ringkasnya, ini contoh **semua elemen teks** yang bisa muncul di jawaban.\n\n## Judul bagian\n\n"
      "Paragraf biasa dengan *teks miring*, **teks tebal**, `kode singkat` dan [tautan](https://www.idx.co.id).\n\n"
      "- Butir daftar pertama\n- Butir daftar kedua\n  - Butir bertingkat\n\n1. Langkah pertama\n2. Langkah kedua\n\n"
      "> Kutipan atau catatan penting ditampilkan seperti ini.\n\n---\n\n"
      "| Saham | Return 1 bulan | Net asing |\n|---|---|---|\n| BBRI | 4,12% | Rp 628,5 miliar |\n| BBCA | −0,85% | −Rp 1,2 triliun |\n| BMRI | 2,05% | Rp 176,6 miliar |\n\n"
      "| Sektor | Catatan |\n|---|---|\n| Perbankan | Contoh tabel kedua dalam satu jawaban |\n")
CASES = [
    ('markdown', 'Elemen teks jawaban', 'Paragraf, judul, huruf tebal/miring, kode, tautan, daftar butir dan bernomor, kutipan, garis pemisah, dan tabel (bisa lebih dari satu, judul kolom bisa diklik untuk mengurutkan).'),
    ('answer_table', 'Jawaban analisis dengan kartu temuan', 'Jawaban riset/analisis: teks, label bukti, kartu temuan per sudut, asumsi/batasan terlipat, metodologi.'),
    ('findings_v2', 'Kartu temuan riset (versi 2)', 'Temuan uji hipotesis: putusan, ukuran efek, sampel efektif, ketidakpastian.'),
    ('plan_v2', 'Kartu rencana riset dengan tombol', 'Rencana riset yang menunggu persetujuan: sudut, pertanyaan, metode, dan tombol Setujui / Revisi / Batal.'),
    ('clarify', 'Pertanyaan balik dengan pilihan', 'AI bertanya balik saat permintaan ambigu; pilihan tampil sebagai tombol.'),
    ('paused', 'Kartu jeda (jawaban dijeda)', 'Saat pemeriksa menahan jawaban: alasan dan pilihan lanjut (hitung ulang / terima sebagian / instruksi lain).'),
    ('annotated', 'Klaim ditandai (miring) + catatan', 'Kalimat sebab-akibat/prediksi ditandai miring dengan catatan, bukan ditolak.'),
    ('export_xlsx', 'File unduhan (Excel/CSV)', 'Jawaban dengan file: tombol Download di bawah jawaban.'),
    ('follow_ups', 'Pertanyaan lanjutan & ide insight', 'Tombol saran pertanyaan berikutnya; klik mengirimnya sebagai pesan baru.'),
    ('hurdles', 'Hambatan proses (panel Details → Sources)', 'Langkah yang ditolak/gagal lalu diperbaiki, dalam bahasa biasa.'),
]

def test_gallery(dummy_orc, browser_page):
    origin, orc = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    original = orc.run
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        key = payload['message'].split()[0]
        if key == 'markdown':
            result['response'].update(answer=MD, assumptions=['Contoh asumsi.'], limitations=['Contoh batasan.'], methodology='Contoh metodologi: data, langkah, metode.')
        elif key == 'clarify':
            result['status'] = 'NEEDS_CLARIFICATION'
            result['response'].update(response_type='CLARIFICATION', answer='', clarification_question='Yang dimaksud BBRI saja, atau semua bank BUMN?')
            result['options'] = [{'label': 'BBRI saja', 'route': 'ANALYSIS'}, {'label': 'Semua bank BUMN', 'route': 'ANALYSIS'}, {'label': 'Ringkasan cepat', 'route': 'QUICK_SUMMARY'}]
        elif key in FIX:
            fixture = FIX[key]
            for name, value in fixture.items():
                if name not in ('request_id', 'conversation'):
                    result[name] = value
        orc.saved[request_id]['response'] = result
        orc.saved[request_id]['run_status'] = result.get('status', 'COMPLETED')
        return result
    orc.run = run
    sign_in(page, origin)
    shots = []
    for index, (key, title, note) in enumerate(CASES):
        if index:
            page.get_by_role('button', name='New conversation').first.click()
        submit(page, f'{key} contoh')
        page.wait_for_function("() => document.querySelectorAll('article.result').length === 1 && !document.querySelector('.composer-status')")
        page.wait_for_timeout(400)
        for d in page.locator('article.result details').all():
            pass
        html = page.locator('article.result').evaluate('n => n.outerHTML')
        chain = page.locator('article.result').evaluate('n => { const out = []; let p = n.parentElement; while (p && p.id !== "root") { out.unshift([p.tagName.toLowerCase(), p.className || "", p.id || ""]); p = p.parentElement; } return out; }')
        extra = ''
        if key == 'hurdles':
            if page.get_by_role('button', name='Show Details', exact=True).count():
                page.get_by_role('button', name='Show Details', exact=True).click()
            page.get_by_role('tab', name='Sources').click() if page.get_by_role('tab', name='Sources').count() else page.get_by_text('Sources', exact=True).first.click()
            page.wait_for_timeout(300)
            extra = page.locator('#edge-details').evaluate('n => n.outerHTML')
        page.locator('article.result').screenshot(path=str(OUT / f'{key}.png'))
        shots.append({'key': key, 'title': title, 'note': note, 'html': html, 'extra': extra, 'chain': chain})
    styles = page.evaluate("() => [...document.querySelectorAll('style')].map(s => s.textContent).join('\\n')")
    root = page.evaluate("() => [document.documentElement.className, document.body.className, document.documentElement.getAttribute('data-theme') || '']")
    (OUT / 'parts.json').write_text(json.dumps({'styles': styles, 'root': root, 'shots': shots}, ensure_ascii=False))
