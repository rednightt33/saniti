-- EXEC-STOCK-CATALOG (user 2026-11-02 "kita mau ambil each ticker for every group ... sama seperti point 1" for
-- stockbit.com/stock-group and stockbit.com/catalog/indeks; "Riwayat ... yes", "Runner ... yes"; 2026-11-09 "D1 OK, D2 OK,
-- D3 OK, D4 OK", "keep as is", "Opsi B"): the Stockbit stock groups (KONGLO) and the Indeks lists the user chose, with
-- their members per ticker, refreshed by every stockbit-updater round (apps/stockbit-updater/stock_lists.py).
--
-- Evidence read 2026-11-09 (pgweb read-only, code at main 1cbfac2; EXEC.md EXEC-STOCK-CATALOG):
-- - the 66 lists: 33 indices (the 36 Indeks lists that are indices, without ABX, AKSELERASI-SYARIAH and IDXCMDTY20 whose
--   meaning is not established) and the 33 KONGLO groups; Stockbit ids re-read 2026-11-09 with the user's token, all 66
--   present; 18 indices carry their member count in their name and had exactly that many members on 2026-11-02;
-- - members: 963 tickers, 104 not in IDX_Stock_Universe (mostly suspended): "Ticker" is not a foreign key;
-- - public tables are owned by postgres and pg_default_acl gives pgweb_reader SELECT on new relations; the explicit grant
--   below repeats it like 20261029_001; stockbit-updater and telegram-monitor write and read as the owner;
-- - the history follows 20260927_006 (bitemporal, pit_valid_* generated from the Asia/Jakarta day after recording,
--   GiST exclusion, superseded knowledge kept); btree_gist is installed.
-- A round writes all lists or none (apply_stock_list_snapshot refuses a snapshot that lacks an enabled list, holds a list
-- that is not enabled, an empty list, a repeated ticker or a numbered index whose count differs); the caller records a
-- refusal as a FAILED Stock_List_Load_Log row and the stockbit-updater round stays SUCCESS with a warning (D2).
-- Not exposed to the AI. Small tables (about 4,200 members): no index beyond the keys.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF to_regclass('public."Stock_List"') IS NOT NULL OR to_regclass('public."Stock_List_Member"') IS NOT NULL
       OR to_regclass('public."Stock_List_Member_History"') IS NOT NULL
       OR to_regclass('public."Stock_List_Load_Log"') IS NOT NULL
       OR to_regclass('public."Stock_List_By_Ticker"') IS NOT NULL
       OR to_regprocedure('public.apply_stock_list_snapshot(jsonb, uuid)') IS NOT NULL THEN
        RAISE EXCEPTION 'stock list objects exist: reconcile before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'Monitoring_Stockbit_Update' AND column_name = 'stock_lists') THEN
        RAISE EXCEPTION 'Monitoring_Stockbit_Update.stock_lists exists: reconcile before applying';
    END IF;
    IF to_regclass('public."Monitoring_Stockbit_Update"') IS NULL OR to_regclass('public."IDX_Stock_Universe"') IS NULL
       OR to_regclass('public."Table_Catalog"') IS NULL OR to_regclass('public."Column_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'a table this migration depends on is missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist') THEN
        RAISE EXCEPTION 'btree_gist is not installed';
    END IF;
END $preflight$;

CREATE TABLE public."Stock_List" (
    list_key text NOT NULL,
    list_kind text NOT NULL,
    source_id text NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    definition text NOT NULL,
    semantic_review_status text NOT NULL,
    expected_count integer,
    sort_order integer NOT NULL,
    is_enabled boolean NOT NULL DEFAULT true,
    member_count integer,
    first_seen_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT "Stock_List_pkey" PRIMARY KEY (list_key),
    CONSTRAINT "Stock_List_kind_check" CHECK (list_kind IN ('INDEX', 'KONGLO')),
    CONSTRAINT "Stock_List_key_check" CHECK (source_id ~ '^[0-9]{1,20}$' AND list_key = list_kind || ':' || source_id),
    CONSTRAINT "Stock_List_text_check" CHECK (btrim(code) <> '' AND btrim(name) <> '' AND btrim(definition) <> ''),
    CONSTRAINT "Stock_List_review_check" CHECK (semantic_review_status IN ('INFERRED', 'SOURCE_CHECKED', 'VERIFIED')),
    CONSTRAINT "Stock_List_expected_check" CHECK (expected_count IS NULL OR (list_kind = 'INDEX' AND expected_count > 0)),
    CONSTRAINT "Stock_List_member_count_check" CHECK (member_count IS NULL OR member_count > 0),
    CONSTRAINT "Stock_List_seen_check" CHECK ((first_seen_at IS NULL) = (last_seen_at IS NULL)
                                              AND (last_seen_at IS NULL OR last_seen_at >= first_seen_at))
);

CREATE TABLE public."Stock_List_Load_Log" (
    run_id bigint GENERATED ALWAYS AS IDENTITY,
    execution_id uuid,
    started_at timestamp with time zone NOT NULL DEFAULT statement_timestamp(),
    finished_at timestamp with time zone,
    status text NOT NULL,
    lists_applied integer,
    members integer,
    added integer,
    removed integer,
    changes jsonb NOT NULL DEFAULT '{}'::jsonb,
    unlisted jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    CONSTRAINT "Stock_List_Load_Log_pkey" PRIMARY KEY (run_id),
    CONSTRAINT "Stock_List_Load_Log_status_check" CHECK (status IN ('SUCCESS', 'NO_CHANGE', 'FAILED')),
    CONSTRAINT "Stock_List_Load_Log_error_check" CHECK ((status = 'FAILED') = (error IS NOT NULL AND btrim(error) <> '')),
    CONSTRAINT "Stock_List_Load_Log_json_check" CHECK (jsonb_typeof(changes) = 'object' AND jsonb_typeof(unlisted) = 'array'),
    CONSTRAINT "Stock_List_Load_Log_finished_check" CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE public."Stock_List_Member" (
    list_key text NOT NULL,
    "Ticker" text NOT NULL,
    source_order integer NOT NULL,
    source_name text,
    first_seen_date date NOT NULL,
    last_seen_date date NOT NULL,
    run_id bigint NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT "Stock_List_Member_pkey" PRIMARY KEY (list_key, "Ticker"),
    CONSTRAINT "Stock_List_Member_list_fkey" FOREIGN KEY (list_key) REFERENCES public."Stock_List" (list_key),
    CONSTRAINT "Stock_List_Member_run_fkey" FOREIGN KEY (run_id) REFERENCES public."Stock_List_Load_Log" (run_id),
    CONSTRAINT "Stock_List_Member_ticker_check" CHECK ("Ticker" ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'),
    CONSTRAINT "Stock_List_Member_order_check" CHECK (source_order > 0),
    CONSTRAINT "Stock_List_Member_dates_check" CHECK (last_seen_date >= first_seen_date)
);

CREATE TABLE public."Stock_List_Member_History" (
    history_id bigint GENERATED ALWAYS AS IDENTITY,
    list_key text NOT NULL,
    "Ticker" text NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    valid_basis text NOT NULL,
    available_at timestamp with time zone NOT NULL,
    available_basis text NOT NULL,
    recorded_from timestamp with time zone NOT NULL,
    recorded_to timestamp with time zone,
    superseded_reason text,
    pit_valid_from date GENERATED ALWAYS AS
        (greatest(valid_from, (timezone('Asia/Jakarta', recorded_from))::date + 1)) STORED,
    pit_valid_to date GENERATED ALWAYS AS
        (least(valid_to, (timezone('Asia/Jakarta', recorded_to))::date + 1)) STORED,
    run_id bigint NOT NULL,
    source_provenance jsonb NOT NULL,
    CONSTRAINT "Stock_List_Member_History_pkey" PRIMARY KEY (history_id),
    CONSTRAINT "Stock_List_Member_History_list_fkey" FOREIGN KEY (list_key) REFERENCES public."Stock_List" (list_key),
    CONSTRAINT "Stock_List_Member_History_run_fkey" FOREIGN KEY (run_id) REFERENCES public."Stock_List_Load_Log" (run_id),
    CONSTRAINT "Stock_List_Member_History_ticker_check" CHECK ("Ticker" ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'),
    CONSTRAINT "Stock_List_Member_History_valid_check" CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT "Stock_List_Member_History_recorded_check" CHECK (recorded_to IS NULL OR recorded_to >= recorded_from),
    CONSTRAINT "Stock_List_Member_History_available_check" CHECK (available_at <= recorded_from),
    CONSTRAINT "Stock_List_Member_History_valid_basis_check" CHECK (valid_basis IN ('FIRST_CAPTURE', 'CHANGE_CAPTURED', 'DOCUMENTED')),
    CONSTRAINT "Stock_List_Member_History_available_basis_check" CHECK (available_basis IN ('RECORDED', 'DOCUMENTED_PUBLICATION')),
    CONSTRAINT "Stock_List_Member_History_superseded_check" CHECK (
        (recorded_to IS NULL AND superseded_reason IS NULL)
        OR (recorded_to IS NOT NULL AND superseded_reason IN ('CHANGE_CAPTURED', 'SAME_DAY_REVISION', 'CORRECTION'))),
    CONSTRAINT "Stock_List_Member_History_provenance_check" CHECK (jsonb_typeof(source_provenance) = 'object'),
    -- one membership version per (list, ticker) for every (validity date, knowledge time) pair, as 20260927_006
    CONSTRAINT "Stock_List_Member_History_no_overlap" EXCLUDE USING gist (
        list_key WITH =,
        "Ticker" WITH =,
        daterange(valid_from, valid_to, '[)') WITH &&,
        tstzrange(recorded_from, recorded_to, '[)') WITH &&)
);

COMMENT ON TABLE public."Stock_List" IS
 'EXEC-STOCK-CATALOG: the Stockbit stock groups (KONGLO) and Indeks lists the user chose (66), one row per list with its plain definition; members in Stock_List_Member, history in Stock_List_Member_History.';
COMMENT ON TABLE public."Stock_List_Member" IS
 'EXEC-STOCK-CATALOG: current members of each Stock_List as of the last complete stockbit-updater round (last_seen_date).';
COMMENT ON TABLE public."Stock_List_Member_History" IS
 'EXEC-STOCK-CATALOG: point-in-time membership intervals of each list and ticker from the first capture onward (pattern of IDX_Stock_Universe_History).';
COMMENT ON TABLE public."Stock_List_Load_Log" IS
 'EXEC-STOCK-CATALOG: one row per stock list round: SUCCESS, NO_CHANGE or FAILED (nothing written), counts, changes and lists Stockbit shows outside the whitelist.';

INSERT INTO public."Stock_List" (list_key, list_kind, source_id, code, name, definition, semantic_review_status,
                                 expected_count, sort_order)
VALUES
 ('INDEX:467', 'INDEX', '467', 'IHSG', 'IHSG',
  'Indeks Harga Saham Gabungan: seluruh saham tercatat di BEI.',
  'INFERRED', NULL, 1),
 ('INDEX:550', 'INDEX', '550', 'LQ45', 'LQ45',
  '45 saham dengan likuiditas tinggi dan kapitalisasi pasar besar, dievaluasi berkala oleh BEI.',
  'INFERRED', 45, 2),
 ('INDEX:551', 'INDEX', '551', 'JII', 'JII',
  'Jakarta Islamic Index: 30 saham syariah paling likuid.',
  'INFERRED', NULL, 3),
 ('INDEX:552', 'INDEX', '552', 'MBX', 'MBX',
  'Indeks Papan Utama (Main Board Index): saham yang tercatat di Papan Utama BEI.',
  'INFERRED', NULL, 4),
 ('INDEX:553', 'INDEX', '553', 'DBX', 'DBX',
  'Indeks Papan Pengembangan (Development Board Index): saham di Papan Pengembangan BEI.',
  'INFERRED', NULL, 5),
 ('INDEX:554', 'INDEX', '554', 'BISNIS-27', 'BISNIS-27',
  'Indeks kerja sama BEI dan harian Bisnis Indonesia: 27 saham pilihan.',
  'INFERRED', 27, 6),
 ('INDEX:555', 'INDEX', '555', 'KOMPAS100', 'KOMPAS100',
  'Indeks kerja sama BEI dan harian Kompas: 100 saham likuid berkapitalisasi besar.',
  'INFERRED', 100, 7),
 ('INDEX:557', 'INDEX', '557', 'SRI-KEHATI', 'SRI-KEHATI',
  'Indeks kerja sama BEI dan Yayasan KEHATI: 25 saham dengan kinerja baik dan kriteria keberlanjutan.',
  'INFERRED', NULL, 8),
 ('INDEX:558', 'INDEX', '558', 'ISSI', 'ISSI',
  'Indeks Saham Syariah Indonesia: seluruh saham syariah yang tercatat di BEI.',
  'INFERRED', NULL, 9),
 ('INDEX:559', 'INDEX', '559', 'IDX30', 'IDX30',
  '30 saham dengan likuiditas tinggi dan kapitalisasi pasar besar (bagian dari LQ45).',
  'INFERRED', 30, 10),
 ('INDEX:560', 'INDEX', '560', 'INFOBANK15', 'INFOBANK15',
  'Indeks kerja sama BEI dan majalah Infobank: 15 saham bank.',
  'INFERRED', 15, 11),
 ('INDEX:1837', 'INDEX', '1837', 'Investor33', 'Investor33',
  'Indeks kerja sama BEI dan Beritasatu (majalah Investor), diluncurkan 21 Maret 2014: 33 saham dari 100 emiten terbaik versi Investor.',
  'SOURCE_CHECKED', 33, 12),
 ('INDEX:1868', 'INDEX', '1868', 'MNC36', 'MNC36',
  'Indeks kerja sama BEI dan MNC: 36 saham pilihan.',
  'INFERRED', 36, 13),
 ('INDEX:1890', 'INDEX', '1890', 'SMinfra18', 'SMinfra18',
  'Indeks kerja sama BEI dan PT Sarana Multi Infrastruktur: 18 saham terkait infrastruktur.',
  'INFERRED', 18, 14),
 ('INDEX:1000000010', 'INDEX', '1000000010', 'IDXHIDIV20', 'IDXHIDIV20',
  'IDX High Dividend 20: 20 saham likuid dengan dividen tunai tinggi.',
  'INFERRED', 20, 15),
 ('INDEX:1000000011', 'INDEX', '1000000011', 'IDXBUMN20', 'IDXBUMN20',
  'IDX BUMN20: 20 saham BUMN, anak usaha BUMN dan afiliasinya yang likuid.',
  'INFERRED', 20, 16),
 ('INDEX:1000000012', 'INDEX', '1000000012', 'JII70', 'JII70',
  'Jakarta Islamic Index 70: 70 saham syariah paling likuid.',
  'INFERRED', 70, 17),
 ('INDEX:1000002393', 'INDEX', '1000002393', 'IDXG30', 'IDXG30',
  'IDX Growth30: 30 saham dengan tren pertumbuhan laba dan pendapatan.',
  'INFERRED', 30, 18),
 ('INDEX:1000002398', 'INDEX', '1000002398', 'IDXV30', 'IDXV30',
  'IDX Value30: 30 saham dengan valuasi relatif murah.',
  'INFERRED', 30, 19),
 ('INDEX:1000003123', 'INDEX', '1000003123', 'IDXQ30', 'IDXQ30',
  'IDX Quality30: 30 saham dengan profitabilitas dan solvabilitas baik.',
  'INFERRED', 30, 20),
 ('INDEX:1000003185', 'INDEX', '1000003185', 'IDXESGL', 'IDXESGL',
  'IDX ESG Leaders: saham dengan penilaian ESG baik dan likuid.',
  'INFERRED', NULL, 21),
 ('INDEX:1000003288', 'INDEX', '1000003288', 'IDX80', 'IDX80',
  '80 saham dengan likuiditas tinggi dan kapitalisasi pasar besar.',
  'INFERRED', 80, 22),
 ('INDEX:1000003289', 'INDEX', '1000003289', 'IDXMESBUMN', 'IDXMESBUMN',
  'IDX MES BUMN 17: saham syariah BUMN dan afiliasinya, kerja sama BEI dan Masyarakat Ekonomi Syariah.',
  'INFERRED', NULL, 23),
 ('INDEX:1000003575', 'INDEX', '1000003575', 'ESGSKEHATI', 'ESGSKEHATI',
  'IDX ESG Sector Leaders KEHATI: saham pemimpin ESG per sektor, kerja sama dengan Yayasan KEHATI.',
  'INFERRED', NULL, 24),
 ('INDEX:1000003576', 'INDEX', '1000003576', 'ESGQKEHATI', 'ESGQKEHATI',
  'IDX ESG Quality 45 KEHATI: 45 saham dengan kualitas ESG dan keuangan baik, kerja sama dengan Yayasan KEHATI.',
  'INFERRED', NULL, 25),
 ('INDEX:1000003583', 'INDEX', '1000003583', 'IDXSMC-LIQ', 'IDXSMC-LIQ',
  'IDX SMC Liquid: saham berkapitalisasi kecil dan menengah yang likuid.',
  'INFERRED', NULL, 26),
 ('INDEX:1000003584', 'INDEX', '1000003584', 'IDXSMC-COM', 'IDXSMC-COM',
  'IDX SMC Composite: saham berkapitalisasi kecil dan menengah.',
  'INFERRED', NULL, 27),
 ('INDEX:1000003585', 'INDEX', '1000003585', 'I-GRADE', 'I-GRADE',
  'PEFINDO i-Grade, kerja sama BEI dan PEFINDO (sejak 21 Desember 2017): 30 saham berperingkat investment grade, dievaluasi Desember dan Juni.',
  'SOURCE_CHECKED', NULL, 28),
 ('INDEX:1000003830', 'INDEX', '1000003830', 'IDXSHAGROW', 'IDXSHAGROW',
  'IDX Sharia Growth: 30 saham syariah dengan tren pertumbuhan.',
  'INFERRED', NULL, 29),
 ('INDEX:1000003847', 'INDEX', '1000003847', 'IDXLQ45LCL', 'IDXLQ45LCL',
  'IDX LQ45 Low Carbon Leaders: konstituen LQ45 dengan emisi karbon relatif rendah.',
  'INFERRED', NULL, 30),
 ('INDEX:1000004351', 'INDEX', '1000004351', 'PRIMBANK10', 'PRIMBANK10',
  'IDX-PEFINDO Prime Bank: 10 saham bank dengan fundamental dan peringkat baik.',
  'INFERRED', 10, 31),
 ('INDEX:1000004908', 'INDEX', '1000004908', 'ECONOMIC30', 'ECONOMIC30',
  'IDX Economic30: 30 saham siklikal yang kinerjanya mengikuti siklus ekonomi.',
  'SOURCE_CHECKED', 30, 32),
 ('INDEX:1000004998', 'INDEX', '1000004998', 'IDXVESTA28', 'IDXVESTA28',
  'IDX-Infovesta Multi-Factor 28, kerja sama BEI dan Infovesta (sejak 2 September 2024): 28 saham, bobot berbasis fundamental.',
  'SOURCE_CHECKED', 28, 33),
 ('KONGLO:9', 'KONGLO', '9', 'SALIM', 'Salim',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Salim (Anthoni Salim). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 1),
 ('KONGLO:13', 'KONGLO', '13', 'DANANTARA', 'Danantara',
  'Grup versi Stockbit untuk Danantara (Badan Pengelola Investasi Daya Anagata Nusantara), pemegang saham negara atas BUMN: anggotanya BUMN dan anak usahanya. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 2),
 ('KONGLO:59', 'KONGLO', '59', 'DJARUM', 'Djarum',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Hartono (Djarum). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 3),
 ('KONGLO:2', 'KONGLO', '2', 'SINARMAS', 'Sinarmas',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Widjaja (Sinar Mas). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 4),
 ('KONGLO:57', 'KONGLO', '57', 'PRAJOGO-PANGESTU', 'Prajogo Pangestu',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Prajogo Pangestu (Barito). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 5),
 ('KONGLO:17', 'KONGLO', '17', 'THOHIR', 'Thohir',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Thohir (Garibaldi dan Erick Thohir). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 6),
 ('KONGLO:56', 'KONGLO', '56', 'SANDIAGA', 'Sandiaga Uno',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Sandiaga Uno. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 7),
 ('KONGLO:10', 'KONGLO', '10', 'SARATOGA', 'Saratoga',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Saratoga Investama Sedaya. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 8),
 ('KONGLO:12', 'KONGLO', '12', 'HAJI-ISAM', 'Haji Isam',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Andi Syamsuddin Arsyad (Haji Isam, Jhonlin). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 9),
 ('KONGLO:61', 'KONGLO', '61', 'LOW-TUCK-KWONG', 'Low Tuck Kwong',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Low Tuck Kwong (Bayan). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 10),
 ('KONGLO:4', 'KONGLO', '4', 'ASTRA', 'Astra',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Astra International (Jardine Matheson). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 11),
 ('KONGLO:51', 'KONGLO', '51', 'AGOES-PROJOSASMITO', 'Agoes Projosasmito',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Agoes Projosasmito. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 12),
 ('KONGLO:29', 'KONGLO', '29', 'TP-RACHMAT', 'TP Rachmat',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Theodore Permadi Rachmat (Triputra). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 13),
 ('KONGLO:55', 'KONGLO', '55', 'PROVIDENT', 'Provident',
  'Grup usaha versi Stockbit bernama Provident; pemilik atau pengendalinya belum dipastikan. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 14),
 ('KONGLO:3', 'KONGLO', '3', 'BAKRIE', 'Bakrie',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Bakrie. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 15),
 ('KONGLO:5', 'KONGLO', '5', 'AGUAN', 'Aguan',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Sugianto Kusuma (Aguan, Agung Sedayu). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 16),
 ('KONGLO:15', 'KONGLO', '15', 'HAPSORO', 'Happy Hapsoro',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Happy Hapsoro. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 17),
 ('KONGLO:14', 'KONGLO', '14', 'EMTEK', 'Emtek',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Sariaatmadja (Emtek). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 18),
 ('KONGLO:8', 'KONGLO', '8', 'LIPPO', 'Lippo',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Riady (Lippo). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 19),
 ('KONGLO:52', 'KONGLO', '52', 'DANATAMA', 'Danatama',
  'Grup usaha versi Stockbit bernama Danatama; pemilik atau pengendalinya belum dipastikan. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 20),
 ('KONGLO:19', 'KONGLO', '19', 'CT-CORP', 'CT Corp',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Chairul Tanjung (CT Corp). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 21),
 ('KONGLO:23', 'KONGLO', '23', 'HARITA', 'Harita',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Lim (Harita). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 22),
 ('KONGLO:18', 'KONGLO', '18', 'TANCORP', 'Tancorp',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Tanoko (Tancorp). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 23),
 ('KONGLO:11', 'KONGLO', '11', 'LO-KHENG-HONG', 'Lo Kheng Hong',
  'Portofolio investor perorangan Lo Kheng Hong versi Stockbit, bukan grup usaha. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 24),
 ('KONGLO:6', 'KONGLO', '6', 'CIPUTRA', 'Ciputra',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Ciputra. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 25),
 ('KONGLO:21', 'KONGLO', '21', 'PANIN', 'Panin',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Gunawan (Mu''min Ali Gunawan, Panin). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 26),
 ('KONGLO:22', 'KONGLO', '22', 'RAJAWALI', 'Rajawali',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Peter Sondakh (Rajawali). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 27),
 ('KONGLO:16', 'KONGLO', '16', 'MNC', 'MNC',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Hary Tanoesoedibjo (MNC). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 28),
 ('KONGLO:25', 'KONGLO', '25', 'HASHIM', 'Hashim',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Hashim Djojohadikusumo. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 29),
 ('KONGLO:24', 'KONGLO', '24', 'PUNJABI', 'Punjabi',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan keluarga Punjabi (MD Entertainment). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 30),
 ('KONGLO:50', 'KONGLO', '50', 'TOMMY-SOEHARTO', 'Tommy Soeharto',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Hutomo Mandala Putra (Tommy Soeharto, Humpuss). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 31),
 ('KONGLO:54', 'KONGLO', '54', 'PAM-GROUP', 'PAM Group',
  'Grup usaha versi Stockbit bernama PAM Group; pemilik atau pengendalinya belum dipastikan. Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 32),
 ('KONGLO:60', 'KONGLO', '60', 'TOMY-WINATA', 'Tomy Winata',
  'Grup usaha versi Stockbit: emiten yang dikaitkan Stockbit dengan Tomy Winata (Artha Graha). Keanggotaan ditetapkan Stockbit (katalog CATALOG_TYPE_KONGLO), bukan BEI, dan bukan bukti kepemilikan, kendali atau afiliasi resmi; satu saham bisa masuk beberapa grup.',
  'INFERRED', NULL, 33)
;

-- One round's snapshot, all lists or none. p_snapshot: {"lists": [{"list_key": "INDEX:554", "members": [{"ticker":
-- "BBCA", "name": "...", "order": 1}, ...]}, ...], "unlisted": [...]}. Membership changes are dated with the
-- Asia/Jakarta date of the round; a ticker that left a list keeps its earlier interval (closed, never deleted), as the
-- universe history does. Returns the round's summary (also the Stock_List_Load_Log row).
CREATE FUNCTION public.apply_stock_list_snapshot(p_snapshot jsonb, p_execution_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamp with time zone := now();
    v_day date := (timezone('Asia/Jakarta', now()))::date;
    v_run bigint;
    v_problem text;
    v_ids bigint[];
    v_added integer;
    v_removed integer;
    v_members integer;
    v_lists integer;
    v_first integer;
    v_changes jsonb;
    v_status text;
    v_unlisted jsonb := coalesce(p_snapshot -> 'unlisted', '[]'::jsonb);
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('Stock_List_Member'));
    IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' OR jsonb_typeof(p_snapshot -> 'lists') IS DISTINCT FROM 'array'
       OR jsonb_typeof(v_unlisted) <> 'array' THEN
        RAISE EXCEPTION 'stock list snapshot refused: no lists array';
    END IF;

    DROP TABLE IF EXISTS pg_temp.stock_list_snapshot;
    CREATE TEMP TABLE stock_list_snapshot ON COMMIT DROP AS
    SELECT l.value ->> 'list_key' AS list_key, m.value ->> 'ticker' AS ticker,
           (m.value ->> 'order')::integer AS source_order, nullif(btrim(m.value ->> 'name'), '') AS source_name
    FROM jsonb_array_elements(p_snapshot -> 'lists') AS l
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(l.value -> 'members', '[]'::jsonb)) AS m;

    -- every refusal names what is wrong; nothing is written before all checks pass
    SELECT string_agg(problem, '; ') INTO v_problem FROM (
        SELECT 'missing enabled list ' || s.list_key AS problem FROM public."Stock_List" s
         WHERE s.is_enabled AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p_snapshot -> 'lists') l
                                            WHERE l.value ->> 'list_key' = s.list_key)
        UNION ALL
        SELECT 'list not enabled or unknown ' || coalesce(l.value ->> 'list_key', '(none)')
          FROM jsonb_array_elements(p_snapshot -> 'lists') l
         WHERE NOT EXISTS (SELECT 1 FROM public."Stock_List" s WHERE s.is_enabled AND s.list_key = l.value ->> 'list_key')
        UNION ALL
        SELECT 'list given twice ' || (l.value ->> 'list_key') FROM jsonb_array_elements(p_snapshot -> 'lists') l
         GROUP BY l.value ->> 'list_key' HAVING count(*) > 1
        UNION ALL
        SELECT 'empty list ' || (l.value ->> 'list_key') FROM jsonb_array_elements(p_snapshot -> 'lists') l
         WHERE jsonb_typeof(l.value -> 'members') IS DISTINCT FROM 'array' OR jsonb_array_length(l.value -> 'members') = 0
        UNION ALL
        SELECT 'ticker given twice ' || list_key || ' ' || ticker FROM stock_list_snapshot
         GROUP BY list_key, ticker HAVING count(*) > 1
        UNION ALL
        SELECT 'invalid member ' || coalesce(list_key, '(none)') || ' ' || coalesce(ticker, '(none)') FROM stock_list_snapshot
         WHERE ticker IS NULL OR ticker !~ '^[A-Z0-9][A-Z0-9-]{0,15}$' OR source_order IS NULL OR source_order <= 0
        UNION ALL
        SELECT format('%s has %s members, expected %s', s.list_key, count(n.ticker), s.expected_count)
          FROM public."Stock_List" s LEFT JOIN stock_list_snapshot n ON n.list_key = s.list_key
         WHERE s.is_enabled AND s.expected_count IS NOT NULL
         GROUP BY s.list_key, s.expected_count HAVING count(n.ticker) <> s.expected_count
    ) AS problems;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'stock list snapshot refused: %', left(v_problem, 1800);
    END IF;

    INSERT INTO public."Stock_List_Load_Log" (execution_id, status, unlisted)
    VALUES (p_execution_id, 'NO_CHANGE', v_unlisted) RETURNING run_id INTO v_run;

    -- the changes of this round, per list (a list's first capture is reported by its count only)
    WITH added AS (
        SELECT n.list_key, n.ticker FROM stock_list_snapshot n
         WHERE NOT EXISTS (SELECT 1 FROM public."Stock_List_Member" m WHERE m.list_key = n.list_key AND m."Ticker" = n.ticker)
    ), removed AS (
        SELECT m.list_key, m."Ticker" AS ticker FROM public."Stock_List_Member" m
         WHERE NOT EXISTS (SELECT 1 FROM stock_list_snapshot n WHERE n.list_key = m.list_key AND n.ticker = m."Ticker")
         AND EXISTS (SELECT 1 FROM stock_list_snapshot x WHERE x.list_key = m.list_key)
    ), per_list AS (
        SELECT s.list_key, s.name, s.first_seen_at IS NULL AS first_capture,
               (SELECT coalesce(jsonb_agg(a.ticker ORDER BY a.ticker), '[]'::jsonb) FROM added a WHERE a.list_key = s.list_key) AS added,
               (SELECT coalesce(jsonb_agg(r.ticker ORDER BY r.ticker), '[]'::jsonb) FROM removed r WHERE r.list_key = s.list_key) AS removed
          FROM public."Stock_List" s WHERE s.is_enabled
    )
    SELECT (SELECT count(*) FROM added), (SELECT count(*) FROM removed),
           coalesce(jsonb_object_agg(p.list_key, CASE WHEN p.first_capture
                    THEN jsonb_build_object('name', p.name, 'first_capture', true, 'members', jsonb_array_length(p.added))
                    ELSE jsonb_build_object('name', p.name, 'added', p.added, 'removed', p.removed) END)
                    FILTER (WHERE p.first_capture OR jsonb_array_length(p.added) > 0 OR jsonb_array_length(p.removed) > 0),
                    '{}'::jsonb)
      INTO v_added, v_removed, v_changes
      FROM per_list p;
    SELECT count(*) FILTER (WHERE first_seen_at IS NULL) INTO v_first FROM public."Stock_List" WHERE is_enabled;

    -- history 1: the open versions of tickers that left a list; the superseded knowledge is kept (recorded_to)
    SELECT coalesce(array_agg(h.history_id), '{}') INTO v_ids
      FROM public."Stock_List_Member_History" h
     WHERE h.recorded_to IS NULL AND h.valid_to IS NULL
       AND EXISTS (SELECT 1 FROM public."Stock_List_Member" m WHERE m.list_key = h.list_key AND m."Ticker" = h."Ticker")
       AND NOT EXISTS (SELECT 1 FROM stock_list_snapshot n WHERE n.list_key = h.list_key AND n.ticker = h."Ticker")
       AND EXISTS (SELECT 1 FROM stock_list_snapshot x WHERE x.list_key = h.list_key);
    UPDATE public."Stock_List_Member_History" h
       SET recorded_to = v_now,
           superseded_reason = CASE WHEN h.valid_from >= v_day THEN 'SAME_DAY_REVISION' ELSE 'CHANGE_CAPTURED' END
     WHERE h.history_id = ANY (v_ids);
    -- history 2: current knowledge, the membership closed at the date the change was recorded (a membership that began
    -- the same day is not kept as current knowledge: it applied to no observation date)
    INSERT INTO public."Stock_List_Member_History" (list_key, "Ticker", valid_from, valid_to, valid_basis, available_at,
                available_basis, recorded_from, run_id, source_provenance)
    SELECT h.list_key, h."Ticker", h.valid_from, v_day, h.valid_basis, v_now, 'RECORDED', v_now, v_run,
           jsonb_build_object('source', 'Stockbit', 'run_id', v_run, 'closes_history_id', h.history_id)
      FROM public."Stock_List_Member_History" h
     WHERE h.history_id = ANY (v_ids) AND h.valid_from < v_day;
    -- history 3: tickers that entered a list, valid from the date recorded (the true date is on or before it); the
    -- first capture of a list says so
    INSERT INTO public."Stock_List_Member_History" (list_key, "Ticker", valid_from, valid_to, valid_basis, available_at,
                available_basis, recorded_from, run_id, source_provenance)
    SELECT n.list_key, n.ticker, v_day, NULL,
           CASE WHEN s.first_seen_at IS NULL THEN 'FIRST_CAPTURE' ELSE 'CHANGE_CAPTURED' END,
           v_now, 'RECORDED', v_now, v_run, jsonb_build_object('source', 'Stockbit', 'run_id', v_run)
      FROM stock_list_snapshot n JOIN public."Stock_List" s ON s.list_key = n.list_key
     WHERE NOT EXISTS (SELECT 1 FROM public."Stock_List_Member" m WHERE m.list_key = n.list_key AND m."Ticker" = n.ticker);

    -- current members
    DELETE FROM public."Stock_List_Member" m
     WHERE NOT EXISTS (SELECT 1 FROM stock_list_snapshot n WHERE n.list_key = m.list_key AND n.ticker = m."Ticker")
         AND EXISTS (SELECT 1 FROM stock_list_snapshot x WHERE x.list_key = m.list_key);
    UPDATE public."Stock_List_Member" m
       SET source_order = n.source_order, source_name = n.source_name, last_seen_date = v_day, run_id = v_run,
           updated_at = v_now
      FROM stock_list_snapshot n
     WHERE n.list_key = m.list_key AND n.ticker = m."Ticker";
    INSERT INTO public."Stock_List_Member" (list_key, "Ticker", source_order, source_name, first_seen_date, last_seen_date,
                run_id, updated_at)
    SELECT n.list_key, n.ticker, n.source_order, n.source_name, v_day, v_day, v_run, v_now
      FROM stock_list_snapshot n
     WHERE NOT EXISTS (SELECT 1 FROM public."Stock_List_Member" m WHERE m.list_key = n.list_key AND m."Ticker" = n.ticker);

    UPDATE public."Stock_List" s
       SET member_count = c.members, first_seen_at = coalesce(s.first_seen_at, v_now), last_seen_at = v_now,
           updated_at = v_now
      FROM (SELECT list_key, count(*)::integer AS members FROM stock_list_snapshot GROUP BY list_key) c
     WHERE c.list_key = s.list_key;

    SELECT count(*), count(DISTINCT list_key) INTO v_members, v_lists FROM stock_list_snapshot;
    v_status := CASE WHEN v_added + v_removed > 0 THEN 'SUCCESS' ELSE 'NO_CHANGE' END;
    UPDATE public."Stock_List_Load_Log"
       SET status = v_status, finished_at = clock_timestamp(), lists_applied = v_lists, members = v_members,
           added = v_added, removed = v_removed, changes = v_changes
     WHERE run_id = v_run;
    DROP TABLE IF EXISTS pg_temp.stock_list_snapshot;
    RETURN jsonb_build_object('run_id', v_run, 'status', v_status, 'lists', v_lists, 'members', v_members,
                              'added', v_added, 'removed', v_removed, 'first_capture_lists', v_first,
                              'changes', v_changes, 'unlisted', v_unlisted);
END
$function$;

CREATE VIEW public."Stock_List_By_Ticker" AS
SELECT m."Ticker",
       u."Ticker" IS NOT NULL AS in_universe,
       u."Security Type" AS universe_security_type,
       array_agg(l.name ORDER BY l.sort_order) FILTER (WHERE l.list_kind = 'KONGLO') AS konglo_groups,
       array_agg(l.name ORDER BY l.sort_order) FILTER (WHERE l.list_kind = 'INDEX') AS indices,
       count(*)::integer AS list_count,
       max(m.last_seen_date) AS last_seen_date
  FROM public."Stock_List_Member" m
  JOIN public."Stock_List" l ON l.list_key = m.list_key AND l.is_enabled
  LEFT JOIN public."IDX_Stock_Universe" u ON u."Ticker" = m."Ticker"
 GROUP BY m."Ticker", u."Ticker", u."Security Type";
COMMENT ON VIEW public."Stock_List_By_Ticker" IS
 'EXEC-STOCK-CATALOG: per ticker, the KONGLO groups and indices that hold it now, and whether it is in IDX_Stock_Universe.';

ALTER TABLE public."Monitoring_Stockbit_Update" ADD COLUMN stock_lists jsonb;

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."Stock_List", public."Stock_List_Member", public."Stock_List_Member_History",
                        public."Stock_List_Load_Log", public."Stock_List_By_Ticker" TO pgweb_reader;
    END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule, point_in_time_status,
 historical_metadata_method)
VALUES
 ('public', 'Stock_List', 'Reference',
  'The Stockbit stock groups (KONGLO: companies Stockbit links to one owner or controller) and Indeks lists (indices) the user chose, one row per list with its plain Indonesian definition, review status and, for indices that carry it in their name, the expected member count.',
  'One Stockbit list (INDEX or KONGLO)', ARRAY['list_key'], 'Stockbit API (/emitten/catalog, /emitten/sectors/88/subsectors), EXEC-STOCK-CATALOG',
  ARRAY[]::text[], ARRAY['database/migrations/20261109_001_stock_list.sql', 'apps/stockbit-updater/stock_lists.py'],
  'Seeded by the migration (66 lists); member_count, first_seen_at and last_seen_at set by every complete stockbit-updater round.',
  ARRAY['apply_stock_list_snapshot(jsonb, uuid)'], 'PARTIAL', 'REFERENCE_STATE', NULL, NULL,
  'Current list definitions; membership over time is in Stock_List_Member_History.', 'UNAVAILABLE',
  'CURRENT_STATE: one row per list as defined now.'),
 ('public', 'Stock_List_Member', 'Reference',
  'Current members of each Stock_List as Stockbit showed them in the last complete stockbit-updater round: one row per list and ticker, with Stockbit''s order and name. A ticker may be in several lists and need not be in IDX_Stock_Universe (suspended stocks stay listed).',
  'One list and ticker', ARRAY['list_key', 'Ticker'], 'Stockbit API (/order-trade/market-mover, /emitten/v3/sector/88/subsector/{id}/company)',
  ARRAY['Stock_List'], ARRAY['database/migrations/20261109_001_stock_list.sql', 'apps/stockbit-updater/stock_lists.py'],
  'Replaced list by list by apply_stock_list_snapshot in every complete stockbit-updater round: members that left are deleted (their history is kept), new ones inserted, last_seen_date moved to the round date.',
  ARRAY['apply_stock_list_snapshot(jsonb, uuid)'], 'PARTIAL', 'REFERENCE_STATE', NULL, NULL,
  'Current membership as of last_seen_date; never use it for an earlier date: use Stock_List_Member_History.', 'UNAVAILABLE',
  'CURRENT_STATE_FALLBACK; historical use requires Stock_List_Member_History.'),
 ('public', 'Stock_List_Member_History', 'Reference',
  'Point-in-time membership of each Stockbit list and ticker recorded by Saniti from its first capture onward: valid_from/valid_to effective interval, recorded_from/recorded_to knowledge interval, pit_valid_from/pit_valid_to the validity a dated join uses. Holds nothing before the first capture.',
  'One membership version of a list and ticker', ARRAY['history_id'], 'Derived from Stock_List_Member changes (EXEC-STOCK-CATALOG)',
  ARRAY['Stock_List', 'Stock_List_Member'], ARRAY['database/migrations/20261109_001_stock_list.sql', 'apps/stockbit-updater/stock_lists.py'],
  'Written only by apply_stock_list_snapshot: an entering ticker opens a version valid from the round date; a leaving one closes it at the round date; superseded knowledge is kept (recorded_to), never deleted.',
  ARRAY['apply_stock_list_snapshot(jsonb, uuid)'], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'valid_from',
  'Point-in-time use selects the row with pit_valid_from <= observation date < pit_valid_to: a version is used from the Asia/Jakarta date after it was recorded. The true change date is on or before valid_from and unknown (valid_basis).',
  'PARTIAL',
  'PROSPECTIVE_CAPTURE from the first stockbit-updater round that loaded the lists; no history before it. A round that is refused writes nothing, so absence from Stockbit for one round is never recorded.'),
 ('public', 'Stock_List_Load_Log', 'Monitoring',
  'One row per stock list round of stockbit-updater: SUCCESS (members changed), NO_CHANGE or FAILED (nothing written, error says why), counts, the changes per list and the lists Stockbit shows outside the 66 chosen.',
  'One stock list round', ARRAY['run_id'], 'stockbit-updater (EXEC-STOCK-CATALOG)',
  ARRAY['Stock_List_Member'], ARRAY['database/migrations/20261109_001_stock_list.sql', 'apps/stockbit-updater/stock_lists.py'],
  'One row per round: written by apply_stock_list_snapshot (SUCCESS, NO_CHANGE) or by stock_lists.py when the round is refused (FAILED).',
  ARRAY['apply_stock_list_snapshot(jsonb, uuid)'], 'PARTIAL', 'NOT_APPLICABLE', NULL, NULL,
  'Operational log, not market data.', 'NOT_APPLICABLE', NULL),
 ('public', 'Stock_List_By_Ticker', 'Reference',
  'View: per ticker, the KONGLO groups and indices that hold it now (enabled lists), whether it is in IDX_Stock_Universe and its universe Security Type.',
  'One ticker', ARRAY['Ticker'], 'View over Stock_List_Member, Stock_List and IDX_Stock_Universe',
  ARRAY['Stock_List_Member', 'Stock_List', 'IDX_Stock_Universe'], ARRAY['database/migrations/20261109_001_stock_list.sql'],
  'A view: always the current Stock_List_Member.', ARRAY[]::text[], 'PARTIAL', 'REFERENCE_STATE', NULL, NULL,
  'Current state only, like Stock_List_Member.', 'UNAVAILABLE', 'CURRENT_STATE_FALLBACK; historical use requires Stock_List_Member_History.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(table_name, column_name, pk, definition, unit, null_rule) AS (VALUES
 ('Stock_List', 'list_key', true, 'List key: list_kind, a colon and the Stockbit id (INDEX:554 = BISNIS-27, KONGLO:13 = Danantara).', NULL, 'Never NULL.'),
 ('Stock_List', 'list_kind', false, 'INDEX (Stockbit Indeks list that is a stock index) or KONGLO (Stockbit stock group).', NULL, 'Never NULL.'),
 ('Stock_List', 'source_id', false, 'Stockbit id: the Indeks subsector id or the KONGLO catalog id.', NULL, 'Never NULL.'),
 ('Stock_List', 'code', false, 'Stockbit code of the list (symbol of an index, catalog_code of a group).', NULL, 'Never NULL.'),
 ('Stock_List', 'name', false, 'Display name as on Stockbit.', NULL, 'Never NULL.'),
 ('Stock_List', 'definition', false, 'Plain Indonesian definition of the list for people and the AI.', NULL, 'Never NULL.'),
 ('Stock_List', 'semantic_review_status', false, 'SOURCE_CHECKED (checked against a public source 2026-11-02), INFERRED (not checked) or VERIFIED (reviewed by the user).', NULL, 'Never NULL.'),
 ('Stock_List', 'expected_count', false, 'Member count the index carries in its name (LQ45 = 45); a round with another count is refused.', 'members', 'NULL for lists without a count in the name and for groups.'),
 ('Stock_List', 'sort_order', false, 'Display order: Stockbit''s order of the Indeks lists and of the groups.', NULL, 'Never NULL.'),
 ('Stock_List', 'is_enabled', false, 'The round loads the list; a disabled list is neither fetched nor changed.', NULL, 'Never NULL.'),
 ('Stock_List', 'member_count', false, 'Members in the last complete round.', 'members', 'NULL before the first round.'),
 ('Stock_List', 'first_seen_at', false, 'Time of the first complete round that loaded the list.', NULL, 'NULL before the first round.'),
 ('Stock_List', 'last_seen_at', false, 'Time of the last complete round that loaded the list.', NULL, 'NULL before the first round.'),
 ('Stock_List', 'created_at', false, 'Row creation time.', NULL, 'Never NULL.'),
 ('Stock_List', 'updated_at', false, 'Last change of the row.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'list_key', true, 'The list (Stock_List.list_key).', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'Ticker', true, 'Ticker as Stockbit gives it; not necessarily in IDX_Stock_Universe.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'source_order', false, 'Position of the ticker in Stockbit''s answer for the list.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'source_name', false, 'Company name as Stockbit gives it.', NULL, 'NULL when Stockbit gives none.'),
 ('Stock_List_Member', 'first_seen_date', false, 'Asia/Jakarta date of the round that first saw the ticker in the list in its current membership.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'last_seen_date', false, 'Asia/Jakarta date of the last complete round that saw it.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'run_id', false, 'Stock_List_Load_Log round that last wrote the row.', NULL, 'Never NULL.'),
 ('Stock_List_Member', 'updated_at', false, 'Time of that round.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'history_id', true, 'Row id of one version (identity only).', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'list_key', false, 'The list (Stock_List.list_key).', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'Ticker', false, 'Ticker as Stockbit gives it.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'valid_from', false, 'Effective start of the membership (inclusive): the Asia/Jakarta date the round recorded it; the true date is on or before it (valid_basis).', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'valid_to', false, 'Effective end (exclusive): the date the round recorded the ticker gone; NULL = still a member in this knowledge version.', NULL, 'NULL while open.'),
 ('Stock_List_Member_History', 'valid_basis', false, 'FIRST_CAPTURE (the list''s first round; the true start is earlier and unknown), CHANGE_CAPTURED (the date the change was recorded) or DOCUMENTED (a documented effective date given by a correction).', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'available_at', false, 'When the information was available to decisions: the recording time (RECORDED) or a documented publication time.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'available_basis', false, 'RECORDED or DOCUMENTED_PUBLICATION.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'recorded_from', false, 'When Saniti recorded this row.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'recorded_to', false, 'When Saniti superseded this row; NULL = current knowledge. Superseded rows are kept.', NULL, 'NULL for current knowledge.'),
 ('Stock_List_Member_History', 'superseded_reason', false, 'CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION.', NULL, 'NULL for current knowledge.'),
 ('Stock_List_Member_History', 'pit_valid_from', false, 'First observation date the row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from. Dated joins use pit_valid_from <= date < pit_valid_to.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'pit_valid_to', false, 'Observation date from which the row no longer applies (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open.', NULL, 'NULL while open.'),
 ('Stock_List_Member_History', 'run_id', false, 'Stock_List_Load_Log round that wrote the row.', NULL, 'Never NULL.'),
 ('Stock_List_Member_History', 'source_provenance', false, 'How the row was written: source, round and the version it closes.', NULL, 'Never NULL.'),
 ('Stock_List_Load_Log', 'run_id', true, 'Identity of one round.', NULL, 'Never NULL.'),
 ('Stock_List_Load_Log', 'execution_id', false, 'Monitoring_Stockbit_Update round that ran it.', NULL, 'NULL when run outside a stockbit-updater round.'),
 ('Stock_List_Load_Log', 'started_at', false, 'Start of the round.', NULL, 'Never NULL.'),
 ('Stock_List_Load_Log', 'finished_at', false, 'End of the round.', NULL, 'NULL only for a FAILED row written before it finished.'),
 ('Stock_List_Load_Log', 'status', false, 'SUCCESS (members changed or a first capture), NO_CHANGE, or FAILED (nothing written).', NULL, 'Never NULL.'),
 ('Stock_List_Load_Log', 'lists_applied', false, 'Lists written by the round.', 'lists', 'NULL for FAILED.'),
 ('Stock_List_Load_Log', 'members', false, 'Members over all lists after the round.', 'members', 'NULL for FAILED.'),
 ('Stock_List_Load_Log', 'added', false, 'List and ticker pairs that entered (a first capture counts all its members).', 'pairs', 'NULL for FAILED.'),
 ('Stock_List_Load_Log', 'removed', false, 'List and ticker pairs that left.', 'pairs', 'NULL for FAILED.'),
 ('Stock_List_Load_Log', 'changes', false, 'JSON per changed list: name and added/removed tickers, or first_capture with the member count.', NULL, 'Never NULL; empty object when none.'),
 ('Stock_List_Load_Log', 'unlisted', false, 'JSON array of lists Stockbit showed outside the 66 chosen (reported, never loaded).', NULL, 'Never NULL; empty array when none.'),
 ('Stock_List_Load_Log', 'error', false, 'Why a FAILED round wrote nothing (the token is never stored).', NULL, 'NULL unless FAILED.'),
 ('Stock_List_By_Ticker', 'Ticker', true, 'Ticker that is a member of at least one enabled list.', NULL, 'Never NULL.'),
 ('Stock_List_By_Ticker', 'in_universe', false, 'The ticker is in IDX_Stock_Universe.', NULL, 'Never NULL.'),
 ('Stock_List_By_Ticker', 'universe_security_type', false, 'IDX_Stock_Universe Security Type of the ticker.', NULL, 'NULL when not in the universe.'),
 ('Stock_List_By_Ticker', 'konglo_groups', false, 'Names of the KONGLO groups that hold the ticker, in Stockbit order.', NULL, 'NULL when none.'),
 ('Stock_List_By_Ticker', 'indices', false, 'Names of the indices that hold the ticker, in Stockbit order.', NULL, 'NULL when none.'),
 ('Stock_List_By_Ticker', 'list_count', false, 'Number of enabled lists that hold the ticker.', 'lists', 'Never NULL.'),
 ('Stock_List_By_Ticker', 'last_seen_date', false, 'Latest last_seen_date of its memberships.', NULL, 'Never NULL.'),
 ('Monitoring_Stockbit_Update', 'stock_lists', false, 'Stock list step result (EXEC-STOCK-CATALOG): the round summary of apply_stock_list_snapshot, or the warning when the step was refused or failed (the round stays SUCCESS).', NULL, 'NULL for rounds before the step or VERIFY rounds.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 d.pk, d.definition, NULL, d.unit, d.null_rule,
 ARRAY['database/migrations/20261109_001_stock_list.sql', 'apps/stockbit-updater/stock_lists.py'], 'PARTIAL'
FROM information_schema.columns c JOIN d ON d.table_name = c.table_name AND d.column_name = c.column_name
WHERE c.table_schema = 'public'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; seeded int; counted int; BEGIN
    SELECT count(*) INTO missing FROM information_schema.columns c
     WHERE c.table_schema = 'public'
       AND (c.table_name IN ('Stock_List', 'Stock_List_Member', 'Stock_List_Member_History', 'Stock_List_Load_Log',
                             'Stock_List_By_Ticker')
            OR (c.table_name = 'Monitoring_Stockbit_Update' AND c.column_name = 'stock_lists'))
       AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public'
                       AND k.table_name = c.table_name AND k.column_name = c.column_name);
    IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
    SELECT count(*) INTO missing FROM unnest(ARRAY['Stock_List', 'Stock_List_Member', 'Stock_List_Member_History',
                                                   'Stock_List_Load_Log', 'Stock_List_By_Ticker']) t
     WHERE NOT EXISTS (SELECT 1 FROM public."Table_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = t);
    IF missing > 0 THEN RAISE EXCEPTION '% objects lack a Table_Catalog row', missing; END IF;
    SELECT count(*), count(expected_count) INTO seeded, counted FROM public."Stock_List";
    IF seeded <> 66 OR counted <> 18
       OR (SELECT count(*) FROM public."Stock_List" WHERE list_kind = 'INDEX') <> 33 THEN
        RAISE EXCEPTION 'expected 66 lists (33 INDEX, 33 KONGLO) and 18 counts, found % and %', seeded, counted;
    END IF;
END $check$;

COMMIT;

-- Rollback (only with the user's go; the history and the round logs go with it):
-- BEGIN;
-- DELETE FROM public."Column_Catalog" WHERE table_schema = 'public' AND (table_name IN ('Stock_List', 'Stock_List_Member',
--   'Stock_List_Member_History', 'Stock_List_Load_Log', 'Stock_List_By_Ticker')
--   OR (table_name = 'Monitoring_Stockbit_Update' AND column_name = 'stock_lists'));
-- DELETE FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name IN ('Stock_List', 'Stock_List_Member',
--   'Stock_List_Member_History', 'Stock_List_Load_Log', 'Stock_List_By_Ticker');
-- ALTER TABLE public."Monitoring_Stockbit_Update" DROP COLUMN stock_lists;
-- DROP VIEW public."Stock_List_By_Ticker";
-- DROP FUNCTION public.apply_stock_list_snapshot(jsonb, uuid);
-- DROP TABLE public."Stock_List_Member_History", public."Stock_List_Member", public."Stock_List_Load_Log",
--   public."Stock_List";
-- COMMIT;
