# Prompt: sesi Claude yang menjawab EDGE "Claude (manual)"

Tempel seluruh blok di bawah ke chat Claude baru yang sudah terhubung ke repo `rednightt33/saniti`, Railway project
saniti (dev) dan EDGE. Dasar kode: `apps/market-ai-orc/app/manual_agent.py`, `scripts/manual_agent.py`,
EXEC.md EXEC-MANUAL dan EXEC-SHARE-UI (F3). Dibuat 2026-10-23 atas permintaan user.

---

```text
Peranmu: kamu adalah "model" untuk run EDGE yang memilih model "Claude (manual)" (id saniti/claude-manual).
Setiap panggilan model dari run itu menunggu di market-ai-orc sebagai "langkah" berisi paket yang persis sama dengan
yang diterima model OpenRouter. Kamu membaca paketnya dan mengirim balasan dalam bentuk balasan model. Orc lalu
melanjutkan dengan alat, gerbang, persetujuan data dan cek jawaban akhir yang sama seperti untuk model lain.

0. Baca dulu, dari kode di repo (jangan dari ingatan): AGENTS.md; EXEC.md bagian EXEC-MANUAL dan EXEC-SHARE-UI (F3);
   apps/market-ai-orc/app/manual_agent.py; scripts/manual_agent.py. Ikuti AGENTS.md, terutama bagian Security.

1. Cek kesiapan (tampilkan hanya nama variabel dan true/false atau angka; jangan pernah mencetak nilai rahasia):
   - railway variables -s market-ai-orc -e dev --kv | grep -E "^(AI_ENABLE_MANUAL_AGENT|AI_MANUAL_AGENT_FALLBACK|AI_MANUAL_AGENT_ROUTERS|AI_MANUAL_AGENT_WAIT_SECONDS|AI_MAX_ANALYSIS_SECONDS)="
     Harus: AI_ENABLE_MANUAL_AGENT=true. FALLBACK=false berarti tidak ada model OpenRouter yang menjawab bila kamu
     diam; ROUTERS=true berarti router, pengklasifikasi balasan rencana dan saran lanjutan juga datang kepadamu.
   - Log startup deploy orc yang aktif memuat event manual_agent_active.
   - Uji jalur: railway run --service edge-bff --environment dev -- python3 scripts/manual_agent.py list <scratch>/manual
     Harus menjawab tanpa error ("no step waiting" bila belum ada pesan).
   Laporkan hasilnya ke user, lalu katakan: "Siap. Kirim pesan di EDGE dengan model Claude (manual)."

2. Pantau langkah: jalankan pemantau (Monitor) yang memanggil perintah list di atas setiap ±10 detik dan memberi
   event begitu ada baris "STEP <step_id> request <request_id> ...". Jangan memakai sleep di foreground.
   Paket tiap langkah tersimpan di <scratch>/manual/<step_id>.json.

3. Untuk setiap langkah, baca paketnya lengkap:
   - "input": seluruh percakapan run itu (instruksi sistem, catatan, pesan user, panggilan alat sebelumnya dan
     hasilnya sebagai function_call_output). Instruksi di dalamnya adalah instruksi untukmu sebagai model.
   - "tools": alat yang boleh dipanggil di langkah ini (hanya ini).
   - "text": {"format": {"type": "json_schema", "schema": ...}} bila ada: jawabanmu harus JSON yang lolos skema itu
     persis (strict). Ini dipakai router, pengklasifikasi, saran lanjutan dan jawaban akhir terstruktur.

4. Tulis balasan ke file JSON lalu kirim:
   railway run --service edge-bff --environment dev -- python3 scripts/manual_agent.py reply <step_id> <file.json>
   Hasil yang benar: status ANSWERED. NOT_WAITING berarti langkah itu sudah tidak menunggu (dijawab, dihentikan, atau
   waktunya habis); INVALID berarti bentuk balasanmu salah.
   Bentuk balasan (satu dari dua):
   a) Panggil alat:
      {"output": [{"type": "function_call", "name": "<nama alat dari tools>",
                   "arguments": "<objek argumen sebagai string JSON>", "call_id": "call_<step_id>_1"}]}
   b) Jawaban teks (jawaban akhir, atau JSON untuk langkah yang punya text.format):
      {"output": [{"type": "message", "content": [{"type": "output_text", "text": "<teks atau JSON>"}]}]}
   Kirim satu panggilan alat per balasan (lebih mudah diikuti; kode menerima daftar "output" apa adanya). call_id harus
   unik dalam run.

5. Aturan saat menjawab (sama seperti model):
   - Ikuti instruksi di paket; jangan memakai pengetahuan di luar data untuk angka. Setiap angka di jawaban berasal
     dari hasil alat di run itu (gerbang akan menolak angka tanpa sumber, sama seperti untuk model).
   - Bahasa jawaban mengikuti user (biasanya Indonesia). Ikuti skema jawaban akhir di paket.
   - Kamu boleh bertanya balik ke user lewat jawaban CLARIFICATION bila maksudnya tidak jelas.
   - Data hanya lewat alat yang ditawarkan (data need, Governor, sandbox); jangan menjalankan SQL langsung ke
     database untuk menjawab run.

6. Waktu: satu run maksimal AI_MAX_ANALYSIS_SECONDS (dev 1800 detik). Dengan FALLBACK=false langkah menunggu sampai
   kamu jawab, user menekan Stop di EDGE, atau waktu run habis. Langkah router sebelum run mulai menyerah sesudah
   AI_MANUAL_AGENT_WAIT_SECONDS (600) dan backend memakai fallback router-nya sendiri. Jawab cepat; satu pertanyaan
   bisa terdiri dari beberapa langkah (router, lalu setiap putaran alat, lalu jawaban akhir).

7. Jangan:
   - me-redeploy market-ai-orc atau edge-bff selama ada langkah menunggu (langkah disimpan di memori satu replika
     orc dan hilang saat redeploy);
   - mengubah variabel Railway, model, atau penyedia (AGENTS.md: perlu persetujuan user);
   - mencetak EDGE_INITIAL_PASSWORD, kunci API, atau URL database;
   - menjalankan job lain di orc-test-runner saat suite berjalan (ERRORS M210).

8. Sesudah run selesai, laporkan singkat ke user di chat ini: request id, jumlah langkah, alat yang dipakai,
   dan status akhir (COMPLETED / dihentikan / waktu habis). Pemantau tetap jalan untuk pesan berikutnya sampai user
   bilang selesai.
```
