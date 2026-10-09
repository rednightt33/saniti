-- EXEC.md EXEC-Y Fase 3 (user decisions 2026-10-09: "E1 ok 2-4"; "kenapa tidak e2 let ai terjemahkan agar sesuai
-- dengan bahasa indonesia in default language"; go "gas"), ERRORS_AND_SOLUTIONS.md M128 (c) and (d).
--
-- 1. AI_table_catalog.row_presence: what a missing row means, so a model building a calendar from a table knows whether
--    an absent day is no activity or missing data (E1 part 2), and an export can say so (E1 part 1).
--      DENSE           every expected date has a row; an absent row is missing data
--      ACTIVITY_ONLY   a row exists only when something happened (a trade, a broker's activity); an absent row on a
--                      trading day means none happened, not missing data
--      NOT_APPLICABLE  the table has no time column (current state or bitemporal reference rows)
--    Seeded from time_column (a dated table here is ACTIVITY_ONLY, an undated one NOT_APPLICABLE). Measured read-only on
--    dev 2025-01-01..2025-12-31 (pgweb, 2026-10-09): Price_Stock_Indonesia_IDX and Feature_01_Stock_Daily miss trading
--    days inside their own span for 297 of 835 tickers; Feature_03_Stock_Broker_Daily misses days on the Nego and Tunai
--    boards; Feature_02_Broker_Rolling and IDX_Broker_Summary hold a row per broker only when that broker traded (their
--    grain). That an absent row means "no activity" (not lost data) is inferred: row_presence_status INFERRED.
-- 2. AI_column_catalog.description_id: the Indonesian meaning of each column (E2), translated once from description by
--    the production model (deepseek/deepseek-v4.1-flash through OpenRouter, temperature 0, 2026-10-09, USD 0.034) and
--    reviewed in this file; description_id_status DRAFT until a person reviews it. An English description changed
--    later no longer matches its translation: each UPDATE below applies only to the English text it translated.
--    market-ai-orc's export reads description_id first and the English text, marked as such, when it is missing.
-- 3. Column_Catalog rows for the four new columns.
--
-- Rollback (forward-only policy: write a new migration): drop the four columns and their Column_Catalog rows; the
-- market-ai-orc version that reads them uses to_jsonb, so older and newer code both run without them.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND ((table_name = 'AI_table_catalog' AND column_name IN ('row_presence', 'row_presence_status'))
                 OR (table_name = 'AI_column_catalog' AND column_name IN ('description_id', 'description_id_status')))) THEN
        RAISE EXCEPTION 'row_presence or description_id already exists';
    END IF;
END
$preflight$;

ALTER TABLE public."AI_table_catalog"
    ADD COLUMN row_presence text,
    ADD COLUMN row_presence_status text,
    ADD CONSTRAINT "AI_table_catalog_row_presence_check" CHECK (
        row_presence IS NULL OR row_presence IN ('DENSE', 'ACTIVITY_ONLY', 'NOT_APPLICABLE')),
    ADD CONSTRAINT "AI_table_catalog_row_presence_status_check" CHECK (
        row_presence_status IS NULL OR row_presence_status IN ('INFERRED', 'REVIEWED', 'VERIFIED')),
    ADD CONSTRAINT "AI_table_catalog_row_presence_time_check" CHECK (
        row_presence IS NULL OR (row_presence = 'NOT_APPLICABLE') = (time_column IS NULL));

UPDATE public."AI_table_catalog"
SET row_presence = CASE WHEN time_column IS NULL THEN 'NOT_APPLICABLE' ELSE 'ACTIVITY_ONLY' END,
    row_presence_status = 'INFERRED';

COMMENT ON COLUMN public."AI_table_catalog".row_presence IS
    'What a missing row means: DENSE (missing data), ACTIVITY_ONLY (no activity on that date), NOT_APPLICABLE (no time column).';
COMMENT ON COLUMN public."AI_table_catalog".row_presence_status IS
    'INFERRED until a person reviews row_presence; REVIEWED or VERIFIED only after review.';

ALTER TABLE public."AI_column_catalog"
    ADD COLUMN description_id text,
    ADD COLUMN description_id_status text,
    ADD CONSTRAINT "AI_column_catalog_description_id_status_check" CHECK (
        (description_id IS NULL AND description_id_status IS NULL)
        OR (description_id IS NOT NULL AND description_id_status IN ('DRAFT', 'REVIEWED')));

UPDATE public."AI_column_catalog" AS c
SET description_id = t.description_id, description_id_status = 'DRAFT'
FROM (VALUES
    ('Feature_01_Stock_Daily', 'date', 'Trading date of the source candle represented by the feature row.',
     'Tanggal perdagangan candle sumber yang diwakili oleh baris fitur.'),
    ('Feature_01_Stock_Daily', 'ticker', 'Exact IDX ticker identifying the security represented by the feature row.',
     'Kode saham IDX persis yang mengidentifikasi efek yang diwakili oleh baris fitur.'),
    ('Feature_01_Stock_Daily', 'close', 'Closing price for the ticker on the trading date.',
     'Harga penutupan untuk kode saham pada tanggal perdagangan.'),
    ('Feature_01_Stock_Daily', 'volume', 'Trading volume reported for the ticker on the trading date.',
     'Volume perdagangan yang dilaporkan untuk kode saham pada tanggal perdagangan.'),
    ('Feature_01_Stock_Daily', 'sector', 'Current Sector classification for the ticker; it is not point-in-time historical classification. ''Undefined'' means the source gives no classification for the security (not a real sector or industry); report those securities apart, never as a category of their own.',
     'Klasifikasi Sector saat ini untuk kode saham; ini bukan klasifikasi historis point-in-time. ''Undefined'' berarti sumber tidak memberikan klasifikasi untuk efek (bukan sektor atau industri riil); laporkan efek tersebut secara terpisah, jangan pernah sebagai kategori tersendiri.'),
    ('Feature_01_Stock_Daily', 'industry', 'Current Industry classification for the ticker; it is not point-in-time historical classification. ''Undefined'' means the source gives no classification for the security (not a real sector or industry); report those securities apart, never as a category of their own.',
     'Klasifikasi Industry saat ini untuk kode saham; ini bukan klasifikasi historis point-in-time. ''Undefined'' berarti sumber tidak memberikan klasifikasi untuk efek (bukan sektor atau industri riil); laporkan efek tersebut secara terpisah, jangan pernah sebagai kategori tersendiri.'),
    ('Feature_01_Stock_Daily', 'close_1d_ago', 'Closing price one prior valid trading observation earlier for the same ticker.',
     'Harga penutupan satu observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'close_5d_ago', 'Closing price five prior valid trading observations earlier for the same ticker.',
     'Harga penutupan lima observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'close_20d_ago', 'Closing price twenty prior valid trading observations earlier for the same ticker.',
     'Harga penutupan dua puluh observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'close_60d_ago', 'Closing price sixty prior valid trading observations earlier for the same ticker.',
     'Harga penutupan enam puluh observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'return_1d_pct', 'Percentage price return between the current close and the close one valid trading observation earlier for the same ticker.',
     'Persentase imbal hasil harga antara harga penutupan saat ini dan harga penutupan satu observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'return_5d_pct', 'Percentage price return between the current close and the close five valid trading observations earlier for the same ticker.',
     'Persentase imbal hasil harga antara harga penutupan saat ini dan harga penutupan lima observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'return_20d_pct', 'Percentage price return between the current close and the close twenty valid trading observations earlier for the same ticker.',
     'Persentase imbal hasil harga antara harga penutupan saat ini dan harga penutupan dua puluh observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'return_60d_pct', 'Percentage price return between the current close and the close sixty valid trading observations earlier for the same ticker.',
     'Persentase imbal hasil harga antara harga penutupan saat ini dan harga penutupan enam puluh observasi perdagangan valid sebelumnya untuk kode saham yang sama.'),
    ('Feature_01_Stock_Daily', 'abs_return_1d_pct', 'Absolute magnitude of the one-trading-observation percentage return, without direction.',
     'Nilai absolut dari persentase imbal hasil satu observasi perdagangan, tanpa arah.'),
    ('Feature_01_Stock_Daily', 'volatility_5d_ann_pct', 'Annualized sample standard deviation of the latest five valid daily decimal returns for the ticker, expressed as percent.',
     'Simpangan baku sampel tahunan dari lima return harian desimal valid terbaru untuk kode saham, dinyatakan dalam persen.'),
    ('Feature_01_Stock_Daily', 'volatility_20d_ann_pct', 'Annualized sample standard deviation of the latest twenty valid daily decimal returns for the ticker, expressed as percent.',
     'Simpangan baku sampel tahunan dari dua puluh return harian desimal valid terbaru untuk kode saham, dinyatakan dalam persen.'),
    ('Feature_01_Stock_Daily', 'volatility_60d_ann_pct', 'Annualized sample standard deviation of the latest sixty valid daily decimal returns for the ticker, expressed as percent.',
     'Simpangan baku sampel tahunan dari enam puluh return harian desimal valid terbaru untuk kode saham, dinyatakan dalam persen.'),
    ('Feature_01_Stock_Daily', 'volatility_5d_change_pct', 'Percentage change in annualized five-return volatility versus its value five valid trading observations earlier.',
     'Perubahan persentase dalam volatilitas lima return disetahunkan dibandingkan dengan nilainya lima observasi perdagangan valid sebelumnya.'),
    ('Feature_01_Stock_Daily', 'volatility_20d_change_pct', 'Percentage change in annualized twenty-return volatility versus its value twenty valid trading observations earlier.',
     'Perubahan persentase dalam volatilitas dua puluh return disetahunkan dibandingkan dengan nilainya dua puluh observasi perdagangan valid sebelumnya.'),
    ('Feature_01_Stock_Daily', 'volatility_60d_change_pct', 'Percentage change in annualized sixty-return volatility versus its value sixty valid trading observations earlier.',
     'Perubahan persentase dalam volatilitas enam puluh return disetahunkan dibandingkan dengan nilainya enam puluh observasi perdagangan valid sebelumnya.'),
    ('Feature_01_Stock_Daily', 'volume_avg_20d', 'Average source trading volume over the latest twenty valid trading observations for the ticker.',
     'Rata-rata volume perdagangan sumber selama dua puluh observasi perdagangan valid terbaru untuk kode saham.'),
    ('Feature_01_Stock_Daily', 'volume_std_20d', 'Sample standard deviation of source trading volume over the latest twenty valid trading observations for the ticker.',
     'Simpangan baku sampel dari volume perdagangan sumber selama dua puluh observasi perdagangan valid terbaru untuk kode saham.'),
    ('Feature_01_Stock_Daily', 'volume_ratio_20d', 'Current trading volume divided by the average volume of the latest twenty valid trading observations.',
     'Volume perdagangan saat ini dibagi dengan rata-rata volume dari dua puluh observasi perdagangan valid terbaru.'),
    ('Feature_01_Stock_Daily', 'volume_zscore_20d', 'Current trading-volume deviation from its latest twenty-observation average, measured in sample standard deviations.',
     'Deviasi volume perdagangan saat ini dari rata-rata dua puluh observasi terbarunya, diukur dalam simpangan baku sampel.'),
    ('Feature_01_Stock_Daily', 'high_20d', 'Highest closing price among the latest twenty valid trading observations for the ticker.',
     'Harga penutupan tertinggi di antara dua puluh observasi perdagangan valid terbaru untuk kode saham.'),
    ('Feature_01_Stock_Daily', 'high_60d', 'Highest closing price among the latest sixty valid trading observations for the ticker.',
     'Harga penutupan tertinggi di antara enam puluh observasi perdagangan valid terbaru untuk kode saham.'),
    ('Feature_01_Stock_Daily', 'drawdown_20d_pct', 'Percentage position of the current close below the highest close in the latest twenty valid trading observations.',
     'Posisi persentase harga penutupan saat ini di bawah harga penutupan tertinggi dalam dua puluh observasi perdagangan valid terbaru.'),
    ('Feature_01_Stock_Daily', 'drawdown_60d_pct', 'Percentage position of the current close below the highest close in the latest sixty valid trading observations.',
     'Posisi persentase harga penutupan saat ini di bawah harga penutupan tertinggi dalam enam puluh observasi perdagangan valid terbaru.'),
    ('Feature_02_Broker_Rolling', 'date', 'Ticker transaction date from IDX_Broker_Summary; the rolling calendar uses all observed dates for the ticker across investor types and boards.',
     'Tanggal transaksi kode saham dari IDX_Broker_Summary; kalender bergulir menggunakan semua tanggal yang teramati untuk kode saham di seluruh tipe investor dan papan.'),
    ('Feature_02_Broker_Rolling', 'ticker', 'Exact IDX_Broker_Summary Symbol; no Stock Universe filter is applied.',
     'Symbol IDX_Broker_Summary yang tepat; tidak ada filter Stock Universe yang diterapkan.'),
    ('Feature_02_Broker_Rolling', 'broker', 'Exact source Broker code identifying the executing broker.',
     'Kode Broker sumber yang tepat yang mengidentifikasi broker pelaksana.'),
    ('Feature_02_Broker_Rolling', 'investor_type', 'Exact source Investor Type: Domestic or Foreign. This describes the investor represented by the source row, not the broker domicile.',
     'Tipe investor sumber yang tepat: Domestic atau Foreign. Ini menjelaskan investor yang diwakili oleh baris sumber, bukan domisili broker.'),
    ('Feature_02_Broker_Rolling', 'market_board', 'Exact source Market Board: Regular, Nego or Tunai; boards never mix in rolling calculations.',
     'Papan pasar sumber yang tepat: Regular, Nego atau Tunai; papan tidak pernah tercampur dalam perhitungan bergulir.'),
    ('Feature_02_Broker_Rolling', 'broker_classification', 'Current broker usage classification from IDX_Broker_Profile; metadata only and not point-in-time history.',
     'Klasifikasi penggunaan broker saat ini dari IDX_Broker_Profile; hanya metadata dan bukan riwayat point-in-time.'),
    ('Feature_02_Broker_Rolling', 'buy_value_1d', 'Source Buy Value for this date, ticker, broker, investor type and board.',
     'Nilai beli sumber untuk tanggal ini, kode saham, broker, tipe investor, dan papan.'),
    ('Feature_02_Broker_Rolling', 'sell_value_1d', 'Source Sell Value for this date, ticker, broker, investor type and board.',
     'Nilai jual sumber untuk tanggal ini, kode saham, broker, tipe investor, dan papan.'),
    ('Feature_02_Broker_Rolling', 'net_value_1d', 'Buy value minus sell value for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling.',
     'Nilai beli dikurangi nilai jual untuk tanggal ini, kode saham, broker, tipe investor sumber, dan papan. Positif berarti beli bersih; negatif berarti jual bersih.'),
    ('Feature_02_Broker_Rolling', 'buy_lots_1d', 'Source Buy Lots for this date, ticker, broker, investor type and board.',
     'Lot beli sumber untuk tanggal ini, kode saham, broker, tipe investor, dan papan.'),
    ('Feature_02_Broker_Rolling', 'sell_lots_1d', 'Source Sell Lots for this date, ticker, broker, investor type and board.',
     'Lot jual sumber untuk tanggal ini, kode saham, broker, tipe investor, dan papan.'),
    ('Feature_02_Broker_Rolling', 'net_lots_1d', 'Buy lots minus sell lots for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling.',
     'Lot beli dikurangi lot jual untuk tanggal ini, kode saham, broker, tipe investor sumber, dan papan. Positif berarti beli bersih; negatif berarti jual bersih.'),
    ('Feature_02_Broker_Rolling', 'net_value_5d', 'Sum of net_value_1d over 5 ticker transaction dates within broker, investor type and board; missing activity contributes zero.',
     'Jumlah net_value_1d selama 5 tanggal perdagangan kode saham dalam broker, tipe investor, dan papan; aktivitas yang hilang berkontribusi nol.'),
    ('Feature_02_Broker_Rolling', 'net_value_20d', 'Sum of net_value_1d over 20 ticker transaction dates within broker, investor type and board; missing activity contributes zero.',
     'Jumlah net_value_1d selama 20 tanggal perdagangan kode saham dalam broker, tipe investor, dan papan; aktivitas yang hilang berkontribusi nol.'),
    ('Feature_02_Broker_Rolling', 'net_value_60d', 'Sum of net_value_1d over 60 ticker transaction dates within broker, investor type and board; missing activity contributes zero.',
     'Jumlah net_value_1d selama 60 tanggal perdagangan kode saham dalam broker, tipe investor, dan papan; aktivitas yang hilang berkontribusi nol.'),
    ('Feature_02_Broker_Rolling', 'net_lots_5d', 'Sum of net_lots_1d over 5 ticker transaction dates within broker, investor type and board.',
     'Jumlah net_lots_1d selama 5 tanggal perdagangan kode saham dalam broker, tipe investor, dan papan.'),
    ('Feature_02_Broker_Rolling', 'net_lots_20d', 'Sum of net_lots_1d over 20 ticker transaction dates within broker, investor type and board.',
     'Jumlah net_lots_1d selama 20 tanggal transaksi kode saham dalam broker, tipe investor, dan papan pasar.'),
    ('Feature_02_Broker_Rolling', 'net_lots_60d', 'Sum of net_lots_1d over 60 ticker transaction dates within broker, investor type and board.',
     'Jumlah net_lots_1d selama 60 tanggal transaksi kode saham dalam broker, tipe investor, dan papan pasar.'),
    ('Feature_02_Broker_Rolling', 'buy_days_20d', 'Number of positive net-value dates in the complete 20-date window for this broker, investor type and board.',
     'Jumlah tanggal nilai bersih positif dalam jendela lengkap 20 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'sell_days_20d', 'Number of negative net-value dates in the complete 20-date window for this broker, investor type and board.',
     'Jumlah tanggal nilai bersih negatif dalam jendela lengkap 20 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'active_days_20d', 'Number of dates with nonzero gross activity in the complete 20-date window for this broker, investor type and board.',
     'Jumlah tanggal dengan aktivitas bruto tidak nol dalam jendela lengkap 20 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'stock_trading_days_20d', '20 after the ticker has 20 observed transaction dates across any investor type or board; otherwise NULL.',
     '20 setelah kode saham memiliki 20 tanggal transaksi teramati lintas tipe investor atau papan pasar mana pun; selain itu NULL.'),
    ('Feature_02_Broker_Rolling', 'buy_day_ratio_20d', 'buy_days_20d divided by 20; for example 12 positive dates produces 0.60.',
     'buy_days_20d dibagi 20; sebagai contoh, 12 tanggal positif menghasilkan 0.60.'),
    ('Feature_02_Broker_Rolling', 'buy_share_active_days_20d', 'buy_days_20d divided by active_days_20d; NULL when there are no active dates.',
     'buy_days_20d dibagi active_days_20d; NULL jika tidak ada tanggal aktif.'),
    ('Feature_02_Broker_Rolling', 'buy_days_60d', 'Number of positive net-value dates in the complete 60-date window for this broker, investor type and board.',
     'Jumlah tanggal nilai bersih positif dalam jendela lengkap 60 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'sell_days_60d', 'Number of negative net-value dates in the complete 60-date window for this broker, investor type and board.',
     'Jumlah tanggal nilai bersih negatif dalam jendela lengkap 60 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'active_days_60d', 'Number of dates with nonzero gross activity in the complete 60-date window for this broker, investor type and board.',
     'Jumlah tanggal dengan aktivitas bruto tidak nol dalam jendela lengkap 60 tanggal untuk broker, tipe investor, dan papan pasar ini.'),
    ('Feature_02_Broker_Rolling', 'stock_trading_days_60d', '60 after the ticker has 60 observed transaction dates across any investor type or board; otherwise NULL.',
     '60 setelah kode saham memiliki 60 tanggal transaksi teramati lintas tipe investor atau papan pasar mana pun; selain itu NULL.'),
    ('Feature_02_Broker_Rolling', 'buy_day_ratio_60d', 'buy_days_60d divided by 60.',
     'buy_days_60d dibagi 60.'),
    ('Feature_02_Broker_Rolling', 'buy_share_active_days_60d', 'buy_days_60d divided by active_days_60d; NULL when there are no active dates.',
     'buy_days_60d dibagi active_days_60d; NULL jika tidak ada tanggal aktif.'),
    ('Feature_02_Broker_Rolling', 'net_value_zscore_20d', 'Current 20-date net value minus the mean of the preceding 252 complete 20-date values, divided by their sample standard deviation; current date excluded.',
     'Nilai bersih 20 tanggal saat ini dikurangi rata-rata dari 252 nilai 20 tanggal lengkap sebelumnya, dibagi dengan simpangan baku sampelnya; tanggal saat ini dikecualikan.'),
    ('Feature_02_Broker_Rolling', 'net_value_zscore_60d', 'Current 60-date net value minus the mean of the preceding 252 complete 60-date values, divided by their sample standard deviation; current date excluded.',
     'Nilai bersih 60-date saat ini dikurangi rata-rata dari 252 nilai 60-date lengkap sebelumnya, dibagi dengan simpangan baku sampelnya; tanggal saat ini dikecualikan.'),
    ('Feature_02_Broker_Rolling', 'net_value_percentile_20d', 'Empirical midrank percentile of current 20-date net value against the preceding 252 complete values in the same broker, investor type and board partition.',
     'Persentil midrank empiris dari nilai bersih 20-date saat ini terhadap 252 nilai lengkap sebelumnya dalam partisi broker, tipe investor, dan papan yang sama.'),
    ('Feature_02_Broker_Rolling', 'net_value_percentile_60d', 'Empirical midrank percentile of current 60-date net value against the preceding 252 complete values in the same broker, investor type and board partition.',
     'Persentil midrank empiris dari nilai bersih 60-date saat ini terhadap 252 nilai lengkap sebelumnya dalam partisi broker, tipe investor, dan papan yang sama.'),
    ('Feature_02_Broker_Rolling', 'positive_net_value_20d', 'Sum of positive daily net values in the complete 20-date window; zero when the complete window has no positive date.',
     'Jumlah nilai bersih harian positif dalam jendela 20-date lengkap; nol jika jendela lengkap tidak memiliki tanggal positif.'),
    ('Feature_02_Broker_Rolling', 'largest_buy_day_20d', 'Largest positive daily net value in the complete 20-date window; NULL when no positive date exists.',
     'Nilai bersih harian positif terbesar dalam jendela 20-date lengkap; NULL jika tidak ada tanggal positif.'),
    ('Feature_02_Broker_Rolling', 'largest_buy_day_share_20d', 'largest_buy_day_20d divided by positive_net_value_20d; for example 40 of 100 total positive flow produces 0.40.',
     'largest_buy_day_20d dibagi positive_net_value_20d; misalnya 40 dari 100 total arus positif menghasilkan 0.40.'),
    ('Feature_02_Broker_Rolling', 'calculated_at', 'Database statement timestamp when this canonical v2 row was materialized; not source event time or data availability time.',
     'Stempel waktu pernyataan basis data saat baris canonical v2 ini dimaterialisasi; bukan waktu kejadian sumber atau waktu ketersediaan data.'),
    ('Feature_03_Stock_Broker_Daily', 'date', 'Source transaction date for this ticker and market board.',
     'Tanggal transaksi sumber untuk kode saham dan papan pasar ini.'),
    ('Feature_03_Stock_Broker_Daily', 'ticker', 'Source broker-summary Symbol, including instruments outside the current stock universe.',
     'Symbol ringkasan broker sumber, termasuk instrumen di luar universe saham saat ini.'),
    ('Feature_03_Stock_Broker_Daily', 'market_board', 'Exact source board: Regular, Nego or Tunai; aggregates never mix boards.',
     'Papan sumber persis: Regular, Nego, atau Tunai; agregat tidak pernah mencampur papan.'),
    ('Feature_03_Stock_Broker_Daily', 'total_buy_value', 'Sum of all broker buy_value_1d for the ticker, date and board.',
     'Jumlah semua buy_value_1d broker untuk kode saham, tanggal, dan papan.'),
    ('Feature_03_Stock_Broker_Daily', 'total_sell_value', 'Sum of all broker sell_value_1d for the ticker, date and board.',
     'Jumlah semua sell_value_1d broker untuk kode saham, tanggal, dan papan.'),
    ('Feature_03_Stock_Broker_Daily', 'active_broker_count', 'Brokers with nonzero gross buy/sell value or lots on the ticker, date and board.',
     'Broker dengan nilai beli/jual bruto atau lot bukan nol pada kode saham, tanggal, dan papan.'),
    ('Feature_03_Stock_Broker_Daily', 'net_buy_broker_count', 'Brokers whose aggregated daily net value is positive.',
     'Broker yang nilai bersih harian agregatnya positif.'),
    ('Feature_03_Stock_Broker_Daily', 'net_sell_broker_count', 'Brokers whose aggregated daily net value is negative.',
     'Broker yang nilai bersih harian agregatnya negatif.'),
    ('Feature_03_Stock_Broker_Daily', 'net_buy_broker_ratio', 'net_buy_broker_count divided by active_broker_count; null when no broker is active.',
     'net_buy_broker_count dibagi active_broker_count; null jika tidak ada broker yang aktif.'),
    ('Feature_03_Stock_Broker_Daily', 'foreign_net_value', 'Sum of daily net value for source Foreign Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile.',
     'Jumlah nilai bersih harian untuk tipe investor asing sumber di seluruh broker. Tipe investor mengidentifikasi investor sumber, bukan domisili broker.'),
    ('Feature_03_Stock_Broker_Daily', 'domestic_net_value', 'Sum of daily net value for source Domestic Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile.',
     'Jumlah nilai bersih harian untuk tipe investor domestik sumber di seluruh broker. Tipe investor mengidentifikasi investor sumber, bukan domisili broker.'),
    ('Feature_03_Stock_Broker_Daily', 'institutional_net_value', 'Sum of daily broker net value where current broker_classification is Institutional-heavy.',
     'Jumlah nilai bersih harian broker di mana broker_classification saat ini adalah Institutional-heavy.'),
    ('Feature_03_Stock_Broker_Daily', 'retail_net_value', 'Sum of daily broker net value where current broker_classification is Retail-heavy.',
     'Jumlah nilai bersih harian broker di mana broker_classification saat ini adalah Retail-heavy.'),
    ('Feature_03_Stock_Broker_Daily', 'mixed_net_value', 'Sum of daily broker net value where current broker_classification is Mixed.',
     'Jumlah nilai bersih harian broker di mana broker_classification saat ini adalah Mixed.'),
    ('Feature_03_Stock_Broker_Daily', 'niche_net_value', 'Sum of daily broker net value where current broker_classification is Niche.',
     'Jumlah nilai bersih harian broker di mana broker_classification saat ini adalah Niche.'),
    ('Feature_03_Stock_Broker_Daily', 'top_buyer', 'Positive-net broker with the greatest daily net value; ties use broker code ascending.',
     'broker dengan net positif dengan nilai bersih harian terbesar; jika seri, gunakan kode broker secara menaik.'),
    ('Feature_03_Stock_Broker_Daily', 'top_buyer_net_value', 'Positive daily net value of top_buyer.',
     'nilai bersih harian positif dari top_buyer.'),
    ('Feature_03_Stock_Broker_Daily', 'top_seller', 'Negative-net broker with the lowest daily net value; ties use broker code ascending.',
     'broker dengan net negatif dengan nilai bersih harian terendah; jika seri, gunakan kode broker secara menaik.'),
    ('Feature_03_Stock_Broker_Daily', 'top_seller_net_value', 'Negative daily net value of top_seller.',
     'nilai bersih harian negatif dari top_seller.'),
    ('Feature_03_Stock_Broker_Daily', 'top3_buyer_net_value', 'Sum of the three greatest positive broker net values, with fewer used when fewer exist.',
     'Jumlah dari tiga nilai bersih broker positif terbesar, dengan yang lebih sedikit digunakan bila yang ada lebih sedikit.'),
    ('Feature_03_Stock_Broker_Daily', 'positive_net_value_total', 'Sum of every positive broker daily net value.',
     'Jumlah setiap nilai bersih harian broker yang positif.'),
    ('Feature_03_Stock_Broker_Daily', 'top3_buyer_share', 'top3_buyer_net_value divided by positive_net_value_total; null when the denominator is zero.',
     'top3_buyer_net_value dibagi positive_net_value_total; null jika penyebutnya nol.'),
    ('Feature_03_Stock_Broker_Daily', 'broker_concentration_hhi', 'Sum of squared absolute-net-flow weights across brokers; null when total absolute net value is zero.',
     'Jumlah bobot aliran net absolut yang dikuadratkan di seluruh broker; null jika total nilai bersih absolut adalah nol.'),
    ('Feature_03_Stock_Broker_Daily', 'calculated_at', 'Database statement timestamp when the row was calculated.',
     'Stempel waktu pernyataan database saat baris dihitung.'),
    ('IDX_Broker_Profile', 'broker_code', 'Two-character IDX broker code.',
     'Kode broker IDX dua karakter.'),
    ('IDX_Broker_Profile', 'broker_name', 'Registered broker or securities-company name.',
     'Nama broker atau perusahaan sekuritas terdaftar.'),
    ('IDX_Broker_Profile', 'broker_type', 'Broker classification: Domestic or Foreign.',
     'Klasifikasi broker: Domestik atau Asing.'),
    ('IDX_Broker_Profile', 'broker_classification', 'Observed broker usage profile: Institutional-heavy, Retail-heavy, Mixed, or Niche; this is distinct from domestic/foreign broker_type.',
     'Profil penggunaan broker yang teramati: Institutional-heavy, Retail-heavy, Mixed, atau Niche; ini berbeda dari broker_type domestik/asing.'),
    ('IDX_Broker_Profile_History', 'history_id', 'Row id of one version (identity only).',
     'ID baris dari satu versi (hanya identitas).'),
    ('IDX_Broker_Profile_History', 'broker_code', 'Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row).',
     'Kode broker IDX dua karakter: kunci entitas (beberapa baris per broker, satu per versi; history_id mengidentifikasi satu baris).'),
    ('IDX_Broker_Profile_History', 'broker_name', 'Registered broker or securities-company name. Value of this version.',
     'Nama broker atau perusahaan sekuritas terdaftar. Nilai dari versi ini.'),
    ('IDX_Broker_Profile_History', 'broker_type', 'Broker classification: Domestic or Foreign. Value of this version.',
     'Klasifikasi broker: Domestik atau Asing. Nilai dari versi ini.'),
    ('IDX_Broker_Profile_History', 'broker_classification', 'Observed broker usage profile: Institutional-heavy, Retail-heavy, Mixed, or Niche; this is distinct from domestic/foreign broker_type. Value of this version.',
     'Profil penggunaan broker yang teramati: Institutional-heavy, Retail-heavy, Mixed, atau Niche; ini berbeda dari broker_type domestik/asing. Nilai dari versi ini.'),
    ('IDX_Broker_Profile_History', 'valid_from', 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).',
     'Awal berlaku versi ini (inklusif). Baris FIRST_CAPTURE dan CHANGE_CAPTURED menggunakan tanggal Asia/Jakarta saat Saniti mencatatnya; tanggal sebenarnya adalah pada atau sebelum itu dan tidak diketahui (valid_basis).'),
    ('IDX_Broker_Profile_History', 'valid_to', 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.',
     'Akhir berlaku versi ini (eksklusif); NULL = masih berlaku dalam versi pengetahuan ini.'),
    ('IDX_Broker_Profile_History', 'valid_basis', 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).',
     'FIRST_CAPTURE (valid_from adalah tanggal pencatatan pertama; awal sebenarnya lebih awal dan tidak diketahui), CHANGE_CAPTURED (valid_from adalah tanggal perubahan dicatat; tanggal perubahan sebenarnya adalah pada atau sebelum itu) atau DOCUMENTED (tanggal berlaku terdokumentasi yang diberikan oleh koreksi).'),
    ('IDX_Broker_Profile_History', 'available_at', 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.',
     'Kapan informasi tersedia untuk keputusan: waktu pencatatan (available_basis RECORDED) atau waktu publikasi terdokumentasi (DOCUMENTED_PUBLICATION, hanya koreksi). Pemilihan point-in-time menggunakan waktu pencatatan, batas konservatifnya.'),
    ('IDX_Broker_Profile_History', 'available_basis', 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.',
     'RECORDED atau DOCUMENTED_PUBLICATION: dari mana available_at berasal.'),
    ('IDX_Broker_Profile_History', 'recorded_from', 'When Saniti recorded this row (start of the knowledge period).',
     'Saat Saniti mencatat baris ini (awal periode pengetahuan).'),
    ('IDX_Broker_Profile_History', 'recorded_to', 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.',
     'Saat Saniti menggantikan baris ini (akhir periode pengetahuan, eksklusif); NULL = pengetahuan saat ini. Baris yang digantikan tetap disimpan.'),
    ('IDX_Broker_Profile_History', 'superseded_reason', 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.',
     'Alasan baris digantikan: CHANGE_CAPTURED, SAME_DAY_REVISION, atau CORRECTION; NULL untuk pengetahuan saat ini.'),
    ('IDX_Broker_Profile_History', 'pit_valid_from', 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.',
     'Tanggal observasi pertama yang menjadi awal berlakunya baris ini pada titik waktu: nilai yang lebih akhir antara valid_from dan tanggal Asia/Jakarta setelah recorded_from (nilai yang dicatat pada suatu tanggal digunakan mulai tanggal berikutnya). Join EFFECTIVE_DATED menggunakan pit_valid_from <= date < pit_valid_to.'),
    ('IDX_Broker_Profile_History', 'pit_valid_to', 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.',
     'Tanggal observasi yang menjadi awal baris ini tidak lagi berlaku pada titik waktu (eksklusif): nilai yang lebih awal antara valid_to dan tanggal Asia/Jakarta setelah recorded_to; NULL = terbuka. Baris dengan pit_valid_to <= pit_valid_from tidak berlaku pada tanggal mana pun.'),
    ('IDX_Broker_Summary', 'Date', 'Exchange trading date.',
     'Tanggal perdagangan bursa.'),
    ('IDX_Broker_Summary', 'Symbol', 'IDX security ticker.',
     'Kode saham efek IDX.'),
    ('IDX_Broker_Summary', 'Broker', 'Two-character broker code.',
     'Kode broker dua karakter.'),
    ('IDX_Broker_Summary', 'Investor Type', 'Investor classification: Domestic or Foreign.',
     'Klasifikasi investor: Domestik atau Asing.'),
    ('IDX_Broker_Summary', 'Market Board', 'IDX market board: Regular, Nego, or Tunai.',
     'Papan pasar IDX: Regular, Nego, atau Tunai.'),
    ('IDX_Broker_Summary', 'Buy Value', 'Gross purchase value for the key combination.',
     'Nilai pembelian bruto untuk kombinasi kunci.'),
    ('IDX_Broker_Summary', 'Sell Value', 'Gross sale value for the key combination.',
     'Nilai penjualan bruto untuk kombinasi kunci.'),
    ('IDX_Broker_Summary', 'Net Value', 'Buy Value minus Sell Value.',
     'Nilai Beli dikurangi Nilai Jual.'),
    ('IDX_Broker_Summary', 'Buy Lots', 'Number of lots purchased.',
     'Jumlah lot yang dibeli.'),
    ('IDX_Broker_Summary', 'Sell Lots', 'Number of lots sold.',
     'Jumlah lot yang dijual.'),
    ('IDX_Broker_Summary', 'Net Lots', 'Buy Lots minus Sell Lots.',
     'Lot Beli dikurangi Lot Jual.'),
    ('IDX_Broker_Summary', 'Avg Buy', 'Average purchase price when supplied by Stockbit.',
     'Harga beli rata-rata bila disediakan oleh Stockbit.'),
    ('IDX_Broker_Summary', 'Avg Sell', 'Average sale price when supplied by Stockbit.',
     'Harga jual rata-rata bila disediakan oleh Stockbit.'),
    ('IDX_Stock_Universe', 'Region', 'Geographic market region.',
     'Wilayah pasar geografis.'),
    ('IDX_Stock_Universe', 'Country', 'Country represented by the listing.',
     'Negara yang diwakili oleh pencatatan.'),
    ('IDX_Stock_Universe', 'Company Name', 'Issuer or company name.',
     'Nama emiten atau perusahaan.'),
    ('IDX_Stock_Universe', 'Ticker', 'IDX ticker and primary identifier for this table.',
     'Kode saham IDX dan pengenal utama untuk tabel ini.'),
    ('IDX_Stock_Universe', 'Exchange', 'Exchange on which the security is listed.',
     'Bursa tempat efek dicatatkan.'),
    ('IDX_Stock_Universe', 'TradingView Symbol', 'Symbol used by TradingView.',
     'Simbol yang digunakan oleh TradingView.'),
    ('IDX_Stock_Universe', 'TradingView URL', 'TradingView instrument page URL.',
     'URL halaman instrumen TradingView.'),
    ('IDX_Stock_Universe', 'Security Type', 'Broad security classification.',
     'Klasifikasi efek secara umum.'),
    ('IDX_Stock_Universe', 'Type Specs', 'More specific security-type detail.',
     'Detail jenis efek yang lebih spesifik.'),
    ('IDX_Stock_Universe', 'Is Common Stock', 'Source flag indicating whether the security is common stock.',
     'Flag sumber yang menunjukkan apakah efek tersebut adalah saham biasa.'),
    ('IDX_Stock_Universe', 'TradingView Country', 'Country value used by TradingView.',
     'Nilai negara yang digunakan oleh TradingView.'),
    ('IDX_Stock_Universe', 'Currency', 'Trading currency.',
     'Mata uang perdagangan.'),
    ('IDX_Stock_Universe', 'Fundamental Currency', 'Currency used for fundamental figures.',
     'Mata uang yang digunakan untuk angka fundamental.'),
    ('IDX_Stock_Universe', 'ISIN', 'International Securities Identification Number.',
     'Nomor Identifikasi Sekuritas Internasional.'),
    ('IDX_Stock_Universe', 'Sector', 'Source sector classification. ''Undefined'' means the source gives no classification for the security (not a real sector or industry); report those securities apart, never as a category of their own.',
     'Klasifikasi sektor sumber. ''Undefined'' berarti sumber tidak memberikan klasifikasi untuk sekuritas (bukan sektor atau industri yang sebenarnya); laporkan sekuritas tersebut secara terpisah, jangan pernah sebagai kategori tersendiri.'),
    ('IDX_Stock_Universe', 'Industry', 'Source industry classification. ''Undefined'' means the source gives no classification for the security (not a real sector or industry); report those securities apart, never as a category of their own.',
     'Klasifikasi industri sumber. ''Undefined'' berarti sumber tidak memberikan klasifikasi untuk sekuritas (bukan sektor atau industri yang sebenarnya); laporkan sekuritas tersebut secara terpisah, jangan pernah sebagai kategori tersendiri.'),
    ('IDX_Stock_Universe_History', 'history_id', 'Row id of one version (identity only).',
     'Row id dari satu versi (hanya identitas).'),
    ('IDX_Stock_Universe_History', 'Ticker', 'IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row).',
     'IDX ticker: kunci entitas (beberapa baris per kode saham, satu per versi; history_id mengidentifikasi satu baris).'),
    ('IDX_Stock_Universe_History', 'Company Name', 'Issuer or company name. Value of this version.',
     'Nama emiten atau perusahaan. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Exchange', 'Exchange on which the security is listed. Value of this version.',
     'Bursa tempat sekuritas tercatat. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Security Type', 'Broad security classification. Value of this version.',
     'Klasifikasi sekuritas secara umum. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Type Specs', 'More specific security-type detail. Value of this version.',
     'Rincian jenis sekuritas yang lebih spesifik. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Is Common Stock', 'Source flag indicating whether the security is common stock. Value of this version.',
     'Flag sumber yang menunjukkan apakah sekuritas tersebut adalah saham biasa. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'ISIN', 'International Securities Identification Number. Value of this version.',
     'Nomor Identifikasi Sekuritas Internasional. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Sector', 'Source sector classification. Value of this version.',
     'Klasifikasi sektor sumber. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'Industry', 'Source industry classification. Value of this version.',
     'Klasifikasi industri sumber. Nilai dari versi ini.'),
    ('IDX_Stock_Universe_History', 'valid_from', 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).',
     'Awal berlaku dari versi ini (inklusif). Baris FIRST_CAPTURE dan CHANGE_CAPTURED menggunakan tanggal Asia/Jakarta saat Saniti mencatatnya; tanggal sebenarnya adalah pada atau sebelum tanggal itu dan tidak diketahui (valid_basis).'),
    ('IDX_Stock_Universe_History', 'valid_to', 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.',
     'Akhir berlaku versi ini (eksklusif); NULL = masih berlaku pada versi pengetahuan ini.'),
    ('IDX_Stock_Universe_History', 'valid_basis', 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).',
     'FIRST_CAPTURE (valid_from adalah tanggal pencatatan pertama; awal sebenarnya lebih awal dan tidak diketahui), CHANGE_CAPTURED (valid_from adalah tanggal perubahan dicatat; tanggal perubahan sebenarnya pada atau sebelum tanggal itu) atau DOCUMENTED (tanggal efektif terdokumentasi yang diberikan oleh koreksi).'),
    ('IDX_Stock_Universe_History', 'available_at', 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.',
     'Kapan informasi tersedia untuk keputusan: waktu pencatatan (available_basis RECORDED) atau waktu publikasi terdokumentasi (DOCUMENTED_PUBLICATION, hanya koreksi). Pemilihan point-in-time menggunakan waktu pencatatan, batas konservatifnya.'),
    ('IDX_Stock_Universe_History', 'available_basis', 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.',
     'RECORDED atau DOCUMENTED_PUBLICATION: dari mana available_at berasal.'),
    ('IDX_Stock_Universe_History', 'recorded_from', 'When Saniti recorded this row (start of the knowledge period).',
     'Kapan Saniti mencatat baris ini (awal periode pengetahuan).'),
    ('IDX_Stock_Universe_History', 'recorded_to', 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.',
     'Kapan Saniti menggantikan baris ini (akhir periode pengetahuan, eksklusif); NULL = pengetahuan saat ini. Baris yang digantikan tetap disimpan.'),
    ('IDX_Stock_Universe_History', 'superseded_reason', 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.',
     'Mengapa baris ini digantikan: CHANGE_CAPTURED, SAME_DAY_REVISION atau CORRECTION; NULL untuk pengetahuan saat ini.'),
    ('IDX_Stock_Universe_History', 'pit_valid_from', 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.',
     'Tanggal observasi pertama baris ini berlaku secara point in time: yang lebih akhir antara valid_from dan tanggal Asia/Jakarta setelah recorded_from (nilai yang dicatat pada suatu tanggal digunakan dari tanggal berikutnya). Join EFFECTIVE_DATED menggunakan pit_valid_from <= date < pit_valid_to.'),
    ('IDX_Stock_Universe_History', 'pit_valid_to', 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.',
     'Tanggal observasi sejak baris ini tidak lagi berlaku secara point in time (eksklusif): yang lebih awal antara valid_to dan tanggal Asia/Jakarta setelah recorded_to; NULL = terbuka. Baris dengan pit_valid_to <= pit_valid_from tidak berlaku untuk tanggal mana pun.'),
    ('Price_Stock_Indonesia_IDX', 'company_name', 'Listed company name.',
     'Nama perusahaan tercatat.'),
    ('Price_Stock_Indonesia_IDX', 'ticker', 'Four-character IDX ticker.',
     'Kode saham IDX empat karakter.'),
    ('Price_Stock_Indonesia_IDX', 'tradingview_symbol', 'TradingView exchange-qualified symbol.',
     'Simbol TradingView dengan kualifikasi bursa.'),
    ('Price_Stock_Indonesia_IDX', 'date', 'Trading date represented by the price row.',
     'Tanggal perdagangan yang diwakili oleh baris harga.'),
    ('Price_Stock_Indonesia_IDX', 'open', 'Opening price.',
     'Harga pembukaan.'),
    ('Price_Stock_Indonesia_IDX', 'high', 'Highest price.',
     'Harga tertinggi.'),
    ('Price_Stock_Indonesia_IDX', 'low', 'Lowest price.',
     'Harga terendah.'),
    ('Price_Stock_Indonesia_IDX', 'close', 'Closing price.',
     'Harga penutupan.'),
    ('Price_Stock_Indonesia_IDX', 'volume', 'Trading volume reported by the source.',
     'Volume perdagangan yang dilaporkan oleh sumber.'),
    ('Price_Stock_Indonesia_IDX', 'source', 'Price data source.',
     'Sumber data harga.'),
    ('Price_Stock_Indonesia_IDX', 'query_date', 'Date the source data was queried.',
     'Tanggal data sumber dikueri.'),
    ('Price_Stock_Indonesia_IDX', 'timeframe', 'Price-series interval.',
     'Interval seri harga.'),
    ('Price_Stock_Indonesia_IDX', 'ingestion_time', 'Timezone-aware database statement time of the latest successful insert or upsert; null for historical rows whose exact ingestion time is unknown.',
     'Waktu statement database yang sadar zona waktu dari insert atau upsert sukses terbaru; null untuk baris historis yang waktu ingestinya tidak diketahui secara pasti.')
) AS t (table_name, column_name, description, description_id)
WHERE c.table_name = t.table_name AND c.column_name = t.column_name AND c.description = t.description;

COMMENT ON COLUMN public."AI_column_catalog".description_id IS
    'The column meaning in Indonesian, translated from description; description stays the source text.';
COMMENT ON COLUMN public."AI_column_catalog".description_id_status IS
    'DRAFT (machine translation, not yet reviewed) or REVIEWED; NULL when there is no translation.';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
    is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES',
       c.column_default, false,
       CASE c.table_name || '.' || c.column_name
        WHEN 'AI_table_catalog.row_presence' THEN 'What a missing row of the table means: DENSE (every expected date '
             'has a row; an absent row is missing data), ACTIVITY_ONLY (a row exists only when something happened; an '
             'absent row on a trading day means none happened) or NOT_APPLICABLE (no time column).'
        WHEN 'AI_table_catalog.row_presence_status' THEN 'Review state of row_presence: INFERRED (seeded by migration '
             '20261009_002 from time_column and a read-only measurement), REVIEWED or VERIFIED after a person confirms it.'
        WHEN 'AI_column_catalog.description_id' THEN 'The column meaning in Indonesian, translated once from '
             'description by the production model; description stays the source text.'
        WHEN 'AI_column_catalog.description_id_status' THEN 'DRAFT (machine translation, not yet reviewed) or REVIEWED; '
             'NULL exactly when description_id is NULL.'
       END,
       'Curated by migration 20261009_002', NULL,
       'NULL when not yet recorded.',
       ARRAY['database/migrations/20261009_002_row_presence_and_indonesian_meanings.sql',
             'apps/market-ai-orc/app/tools/export.py'],
       'PARTIAL'
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND ((c.table_name = 'AI_table_catalog' AND c.column_name IN ('row_presence', 'row_presence_status'))
    OR (c.table_name = 'AI_column_catalog' AND c.column_name IN ('description_id', 'description_id_status')));

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE row_presence IS NULL OR row_presence_status <> 'INFERRED') THEN
        RAISE EXCEPTION 'Every AI_table_catalog row needs an INFERRED row_presence';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE description_id IS NOT NULL) <> 172 THEN
        RAISE EXCEPTION 'Expected 172 translated column meanings, found %',
            (SELECT count(*) FROM public."AI_column_catalog" WHERE description_id IS NOT NULL);
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE (table_name = 'AI_table_catalog' AND column_name IN ('row_presence', 'row_presence_status'))
           OR (table_name = 'AI_column_catalog' AND column_name IN ('description_id', 'description_id_status'))) <> 4 THEN
        RAISE EXCEPTION 'Every new column needs a Column_Catalog definition';
    END IF;
END
$verify$;

COMMIT;
