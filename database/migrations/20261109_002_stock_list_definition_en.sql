-- EXEC-SCREENER-STOCK-LISTS (user 2026-11-09, on the language of the list definitions the Screener shows: "1. Inggris"):
-- an English definition beside the Indonesian one for each of the 66 Stock_List rows. The Screener page is English and
-- shows the definition as the list's tooltip; the Indonesian `definition` stays for people and the AI (unchanged).
-- Each English text translates the seeded Indonesian definition of 20261109_001 (same facts, same caveats; no new claim).
-- Evidence read 2026-11-09: the stockbit-updater never writes Stock_List.definition or inserts a list
-- (apply_stock_list_snapshot updates member_count, first_seen_at and last_seen_at only, 20261109_001 :499-503), so a
-- column set here stays as set; a list a later migration adds must give its definition_en too (NOT NULL).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."Stock_List"') IS NULL THEN
        RAISE EXCEPTION 'Stock_List is missing: apply 20261109_001 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'Stock_List'
               AND column_name = 'definition_en') THEN
        RAISE EXCEPTION 'Stock_List.definition_en exists: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM public."Stock_List") <> 66 THEN
        RAISE EXCEPTION 'expected the 66 seeded lists, found %', (SELECT count(*) FROM public."Stock_List");
    END IF;
END $preflight$;

ALTER TABLE public."Stock_List" ADD COLUMN definition_en text;

WITH t(list_key, definition_en) AS (VALUES
 ('INDEX:467', 'Jakarta Composite Index: every stock listed on the IDX.'),
 ('INDEX:550', '45 stocks with high liquidity and large market capitalisation, reviewed periodically by the IDX.'),
 ('INDEX:551', 'Jakarta Islamic Index: the 30 most liquid sharia stocks.'),
 ('INDEX:552', 'Main Board Index: stocks listed on the IDX Main Board.'),
 ('INDEX:553', 'Development Board Index: stocks on the IDX Development Board.'),
 ('INDEX:554', 'Index of the IDX and the daily Bisnis Indonesia: 27 selected stocks.'),
 ('INDEX:555', 'Index of the IDX and the daily Kompas: 100 liquid stocks with large market capitalisation.'),
 ('INDEX:557', 'Index of the IDX and the KEHATI Foundation: 25 stocks with good performance and sustainability criteria.'),
 ('INDEX:558', 'Indonesia Sharia Stock Index: every sharia stock listed on the IDX.'),
 ('INDEX:559', '30 stocks with high liquidity and large market capitalisation (a subset of LQ45).'),
 ('INDEX:560', 'Index of the IDX and Infobank magazine: 15 bank stocks.'),
 ('INDEX:1837', 'Index of the IDX and Beritasatu (Investor magazine), launched 21 March 2014: 33 stocks from Investor''s 100 best issuers.'),
 ('INDEX:1868', 'Index of the IDX and MNC: 36 selected stocks.'),
 ('INDEX:1890', 'Index of the IDX and PT Sarana Multi Infrastruktur: 18 infrastructure-related stocks.'),
 ('INDEX:1000000010', 'IDX High Dividend 20: 20 liquid stocks with high cash dividends.'),
 ('INDEX:1000000011', 'IDX BUMN20: 20 liquid stocks of state-owned enterprises, their subsidiaries and affiliates.'),
 ('INDEX:1000000012', 'Jakarta Islamic Index 70: the 70 most liquid sharia stocks.'),
 ('INDEX:1000002393', 'IDX Growth30: 30 stocks with a growth trend in earnings and revenue.'),
 ('INDEX:1000002398', 'IDX Value30: 30 stocks with relatively low valuations.'),
 ('INDEX:1000003123', 'IDX Quality30: 30 stocks with good profitability and solvency.'),
 ('INDEX:1000003185', 'IDX ESG Leaders: liquid stocks with good ESG ratings.'),
 ('INDEX:1000003288', '80 stocks with high liquidity and large market capitalisation.'),
 ('INDEX:1000003289', 'IDX MES BUMN 17: sharia stocks of state-owned enterprises and their affiliates, an index of the IDX and Masyarakat Ekonomi Syariah.'),
 ('INDEX:1000003575', 'IDX ESG Sector Leaders KEHATI: the ESG leaders of each sector, with the KEHATI Foundation.'),
 ('INDEX:1000003576', 'IDX ESG Quality 45 KEHATI: 45 stocks with good ESG and financial quality, with the KEHATI Foundation.'),
 ('INDEX:1000003583', 'IDX SMC Liquid: liquid small and mid capitalisation stocks.'),
 ('INDEX:1000003584', 'IDX SMC Composite: small and mid capitalisation stocks.'),
 ('INDEX:1000003585', 'PEFINDO i-Grade, an index of the IDX and PEFINDO (since 21 December 2017): 30 stocks rated investment grade, reviewed in December and June.'),
 ('INDEX:1000003830', 'IDX Sharia Growth: 30 sharia stocks with a growth trend.'),
 ('INDEX:1000003847', 'IDX LQ45 Low Carbon Leaders: LQ45 constituents with relatively low carbon emissions.'),
 ('INDEX:1000004351', 'IDX-PEFINDO Prime Bank: 10 bank stocks with good fundamentals and ratings.'),
 ('INDEX:1000004908', 'IDX Economic30: 30 cyclical stocks whose performance follows the economic cycle.'),
 ('INDEX:1000004998', 'IDX-Infovesta Multi-Factor 28, an index of the IDX and Infovesta (since 2 September 2024): 28 stocks, weights based on fundamentals.'),
 ('KONGLO:9', 'Stockbit''s business group: issuers Stockbit links to the Salim family (Anthoni Salim). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:13', 'Stockbit''s group for Danantara (Badan Pengelola Investasi Daya Anagata Nusantara), the state''s shareholder in state-owned enterprises: its members are state-owned enterprises and their subsidiaries. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:59', 'Stockbit''s business group: issuers Stockbit links to the Hartono family (Djarum). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:2', 'Stockbit''s business group: issuers Stockbit links to the Widjaja family (Sinar Mas). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:57', 'Stockbit''s business group: issuers Stockbit links to Prajogo Pangestu (Barito). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:17', 'Stockbit''s business group: issuers Stockbit links to the Thohir family (Garibaldi and Erick Thohir). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:56', 'Stockbit''s business group: issuers Stockbit links to Sandiaga Uno. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:10', 'Stockbit''s business group: issuers Stockbit links to Saratoga Investama Sedaya. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:12', 'Stockbit''s business group: issuers Stockbit links to Andi Syamsuddin Arsyad (Haji Isam, Jhonlin). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:61', 'Stockbit''s business group: issuers Stockbit links to Low Tuck Kwong (Bayan). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:4', 'Stockbit''s business group: issuers Stockbit links to Astra International (Jardine Matheson). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:51', 'Stockbit''s business group: issuers Stockbit links to Agoes Projosasmito. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:29', 'Stockbit''s business group: issuers Stockbit links to Theodore Permadi Rachmat (Triputra). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:55', 'Stockbit''s business group named Provident; its owner or controller is not established. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:3', 'Stockbit''s business group: issuers Stockbit links to the Bakrie family. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:5', 'Stockbit''s business group: issuers Stockbit links to Sugianto Kusuma (Aguan, Agung Sedayu). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:15', 'Stockbit''s business group: issuers Stockbit links to Happy Hapsoro. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:14', 'Stockbit''s business group: issuers Stockbit links to the Sariaatmadja family (Emtek). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:8', 'Stockbit''s business group: issuers Stockbit links to the Riady family (Lippo). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:52', 'Stockbit''s business group named Danatama; its owner or controller is not established. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:19', 'Stockbit''s business group: issuers Stockbit links to Chairul Tanjung (CT Corp). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:23', 'Stockbit''s business group: issuers Stockbit links to the Lim family (Harita). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:18', 'Stockbit''s business group: issuers Stockbit links to the Tanoko family (Tancorp). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:11', 'Stockbit''s list of the holdings of the individual investor Lo Kheng Hong, not a business group. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:6', 'Stockbit''s business group: issuers Stockbit links to the Ciputra family. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:21', 'Stockbit''s business group: issuers Stockbit links to the Gunawan family (Mu''min Ali Gunawan, Panin). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:22', 'Stockbit''s business group: issuers Stockbit links to Peter Sondakh (Rajawali). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:16', 'Stockbit''s business group: issuers Stockbit links to Hary Tanoesoedibjo (MNC). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:25', 'Stockbit''s business group: issuers Stockbit links to Hashim Djojohadikusumo. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:24', 'Stockbit''s business group: issuers Stockbit links to the Punjabi family (MD Entertainment). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:50', 'Stockbit''s business group: issuers Stockbit links to Hutomo Mandala Putra (Tommy Soeharto, Humpuss). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:54', 'Stockbit''s business group named PAM Group; its owner or controller is not established. Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'),
 ('KONGLO:60', 'Stockbit''s business group: issuers Stockbit links to Tomy Winata (Artha Graha). Membership is set by Stockbit (catalog CATALOG_TYPE_KONGLO), not by the IDX, and is not proof of ownership, control or official affiliation; one stock can belong to several groups.'))
UPDATE public."Stock_List" s SET definition_en = t.definition_en, updated_at = now()
  FROM t WHERE t.list_key = s.list_key;

DO $filled$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Stock_List" WHERE definition_en IS NULL) THEN
        RAISE EXCEPTION 'lists without an English definition: %',
            (SELECT string_agg(list_key, ', ' ORDER BY list_key) FROM public."Stock_List" WHERE definition_en IS NULL);
    END IF;
END $filled$;

ALTER TABLE public."Stock_List" ALTER COLUMN definition_en SET NOT NULL;
ALTER TABLE public."Stock_List" ADD CONSTRAINT "Stock_List_definition_en_check" CHECK (btrim(definition_en) <> '');
COMMENT ON COLUMN public."Stock_List".definition_en IS
 'EXEC-SCREENER-STOCK-LISTS: plain English definition of the list (the Screener''s tooltip); translates definition.';

INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 false, 'Plain English definition of the list, the translation of definition; shown by the Screener as the list''s tooltip.',
 NULL, NULL, 'Never NULL.',
 ARRAY['database/migrations/20261109_002_stock_list_definition_en.sql', 'apps/terminal-publisher/publisher.py'], 'PARTIAL'
FROM information_schema.columns c
WHERE c.table_schema = 'public' AND c.table_name = 'Stock_List' AND c.column_name = 'definition_en'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Stock_List'
                   AND column_name = 'definition_en') THEN
        RAISE EXCEPTION 'definition_en lacks its Column_Catalog row';
    END IF;
    IF (SELECT count(*) FROM public."Stock_List" WHERE btrim(definition_en) <> '') <> 66 THEN
        RAISE EXCEPTION 'expected 66 English definitions';
    END IF;
END $check$;

COMMIT;

-- Rollback (only with the user's go):
-- BEGIN;
-- DELETE FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Stock_List' AND column_name = 'definition_en';
-- ALTER TABLE public."Stock_List" DROP COLUMN definition_en;
-- COMMIT;
