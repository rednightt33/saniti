-- EXEC-UNIVERSE-BROKER S1.1 (user go 2026-11-05: "ok" to "63 kode masuk universe -> harga -> dukungan ETF ->
-- publikasi"; "Benar semua 63 kode masuk, termasuk 13 saham Nego? OK"): the 63 four-letter codes that trade on IDX and
-- have broker summary rows but were not in IDX_Stock_Universe (verification/universe_63/codes.json) join it.
-- Values come from the TradingView scanner (verification/universe_63/tv_scanner.json, read 2026-11-05), not typed:
-- * Security Type and Type Specs are TradingView's type and typespecs: 18 'stock'/'common', 45 'fund'/'etf'
--   ('fund' is the value TradingView gives an ETF; Is Common Stock 'No' for them);
-- * Sector and Industry are 'Undefined' (D02): the universe holds the curated IDX classification
--   (Universe_Equity_Description.xlsx; e.g. BBCA Financials/Banks), TradingView's own taxonomy differs (BBCA
--   Finance/Major Banks) and is kept only in Universe_Equity_Description.TV_Sector/TV_Industry;
-- * IDX_Stock_Universe_History rows are written by its capture trigger.
-- Rollback: DELETE the 63 tickers from Universe_Equity_Description and IDX_Stock_Universe (the history trigger records
-- the removal); restore the Column_Catalog definition below.
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $pre$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM public."IDX_Stock_Universe" WHERE "Ticker" IN ('AKKU', 'ALTO', 'BEBS', 'BHAT', 'CRAB', 'EDGE', 'GAMA', 'GTBO', 'HILL', 'IBST', 'INDX', 'PLIN', 'PMMP', 'RAFI', 'SUPR', 'TAYS', 'TRUE', 'UNSP', 'XBGS', 'XBID', 'XBIN', 'XBLQ', 'XBSK', 'XCEG', 'XCLQ', 'XDES', 'XDIF', 'XGLD', 'XIFE', 'XIHD', 'XIID', 'XIIF', 'XIIT', 'XIJI', 'XILV', 'XIML', 'XIPB', 'XIPI', 'XISB', 'XISC', 'XISI', 'XISR', 'XKGS', 'XKID', 'XKIV', 'XKMS', 'XMES', 'XMGB', 'XMIG', 'XMLF', 'XMSK', 'XPDV', 'XPFT', 'XPIN', 'XPLQ', 'XPSG', 'XPTD', 'XRDN', 'XSBC', 'XSGO', 'XSSI', 'XSSK', 'XTRA');
    IF n <> 0 THEN RAISE EXCEPTION '% of the 63 tickers already in IDX_Stock_Universe', n; END IF;
    SELECT count(*) INTO n FROM public."Universe_Equity_Description" WHERE "Ticker" IN ('AKKU', 'ALTO', 'BEBS', 'BHAT', 'CRAB', 'EDGE', 'GAMA', 'GTBO', 'HILL', 'IBST', 'INDX', 'PLIN', 'PMMP', 'RAFI', 'SUPR', 'TAYS', 'TRUE', 'UNSP', 'XBGS', 'XBID', 'XBIN', 'XBLQ', 'XBSK', 'XCEG', 'XCLQ', 'XDES', 'XDIF', 'XGLD', 'XIFE', 'XIHD', 'XIID', 'XIIF', 'XIIT', 'XIJI', 'XILV', 'XIML', 'XIPB', 'XIPI', 'XISB', 'XISC', 'XISI', 'XISR', 'XKGS', 'XKID', 'XKIV', 'XKMS', 'XMES', 'XMGB', 'XMIG', 'XMLF', 'XMSK', 'XPDV', 'XPFT', 'XPIN', 'XPLQ', 'XPSG', 'XPTD', 'XRDN', 'XSBC', 'XSGO', 'XSSI', 'XSSK', 'XTRA');
    IF n <> 0 THEN RAISE EXCEPTION '% of the 63 tickers already in Universe_Equity_Description', n; END IF;
END
$pre$;

INSERT INTO public."IDX_Stock_Universe" ("Region", "Country", "Company Name", "Ticker", "Exchange", "TradingView Symbol",
    "TradingView URL", "Security Type", "Type Specs", "Is Common Stock", "TradingView Country", "Currency",
    "Fundamental Currency", "ISIN", "Sector", "Industry") VALUES
('Asia', 'Indonesia', 'PT Anugerah Kagum Karya Utama Tbk', 'AKKU', 'IDX', 'IDX:AKKU', 'https://www.tradingview.com/symbols/IDX-AKKU/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000099609', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Tri Banyan Tirta Tbk', 'ALTO', 'IDX', 'IDX:ALTO', 'https://www.tradingview.com/symbols/IDX-ALTO/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000123805', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Berkah Beton Sadaya Tbk', 'BEBS', 'IDX', 'IDX:BEBS', 'https://www.tradingview.com/symbols/IDX-BEBS/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000159601', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Bhakti Multi Artha Tbk', 'BHAT', 'IDX', 'IDX:BHAT', 'https://www.tradingview.com/symbols/IDX-BHAT/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000155807', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Toba Surimi Industries Tbk', 'CRAB', 'IDX', 'IDX:CRAB', 'https://www.tradingview.com/symbols/IDX-CRAB/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000171408', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Indointernet Tbk', 'EDGE', 'IDX', 'IDX:EDGE', 'https://www.tradingview.com/symbols/IDX-EDGE/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000159403', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Aksara Global Development Tbk', 'GAMA', 'IDX', 'IDX:GAMA', 'https://www.tradingview.com/symbols/IDX-GAMA/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000123201', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Garda Tujuh Buana Tbk', 'GTBO', 'IDX', 'IDX:GTBO', 'https://www.tradingview.com/symbols/IDX-GTBO/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000113004', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Hillcon Tbk', 'HILL', 'IDX', 'IDX:HILL', 'https://www.tradingview.com/symbols/IDX-HILL/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000186901', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Inti Bangun Sejahtera Tbk', 'IBST', 'IDX', 'IDX:IBST', 'https://www.tradingview.com/symbols/IDX-IBST/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000124506', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Tanah Laut Tbk', 'INDX', 'IDX', 'IDX:INDX', 'https://www.tradingview.com/symbols/IDX-INDX/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000102007', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Plaza Indonesia Realty Tbk', 'PLIN', 'IDX', 'IDX:PLIN', 'https://www.tradingview.com/symbols/IDX-PLIN/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000105406', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Panca Mitra Multiperdana Tbk', 'PMMP', 'IDX', 'IDX:PMMP', 'https://www.tradingview.com/symbols/IDX-PMMP/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000158306', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Sari Kreasi Boga Tbk', 'RAFI', 'IDX', 'IDX:RAFI', 'https://www.tradingview.com/symbols/IDX-RAFI/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000170509', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Solusi Tunas Pratama Tbk', 'SUPR', 'IDX', 'IDX:SUPR', 'https://www.tradingview.com/symbols/IDX-SUPR/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000120702', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Jaya Swarasa Agung Tbk', 'TAYS', 'IDX', 'IDX:TAYS', 'https://www.tradingview.com/symbols/IDX-TAYS/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000164601', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Triniti Dinamik Tbk', 'TRUE', 'IDX', 'IDX:TRUE', 'https://www.tradingview.com/symbols/IDX-TRUE/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000160807', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PT Bakrie Sumatera Plantations Tbk', 'UNSP', 'IDX', 'IDX:UNSP', 'https://www.tradingview.com/symbols/IDX-UNSP/', 'stock', 'common', 'Yes', 'Indonesia', 'IDR', 'IDR', 'ID1000099708', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Batavia Gold Sharia ETF Exchange Traded Fund Units', 'XBGS', 'IDX', 'IDX:XBGS', 'https://www.tradingview.com/symbols/IDX-XBGS/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000598604', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Batavia IDX30 ETF', 'XBID', 'IDX', 'IDX:XBID', 'https://www.tradingview.com/symbols/IDX-XBID/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000381100', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Bahana ETF Bisnis-27', 'XBIN', 'IDX', 'IDX:XBIN', 'https://www.tradingview.com/symbols/IDX-XBIN/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000412004', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Batavia Smart Liquid ETF', 'XBLQ', 'IDX', 'IDX:XBLQ', 'https://www.tradingview.com/symbols/IDX-XBLQ/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000333903', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Batavia SRI-KEHATI ETF', 'XBSK', 'IDX', 'IDX:XBSK', 'https://www.tradingview.com/symbols/IDX-XBSK/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000384500', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Capital ETF IDX ESG Leaders', 'XCEG', 'IDX', 'IDX:XCEG', 'https://www.tradingview.com/symbols/IDX-XCEG/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000483708', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Cipta ETF Indek LQ45', 'XCLQ', 'IDX', 'IDX:XCLQ', 'https://www.tradingview.com/symbols/IDX-XCLQ/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000418902', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Bri Mi Gold ETF Syariah Exchange Traded Fund Units', 'XDES', 'IDX', 'IDX:XDES', 'https://www.tradingview.com/symbols/IDX-XDES/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000597408', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'BRI ETF Indonesia Top 40', 'XDIF', 'IDX', 'IDX:XDIF', 'https://www.tradingview.com/symbols/IDX-XDIF/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000335908', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Premier ETF Gold Sharia Indonesia Exchange Traded Fund Units', 'XGLD', 'IDX', 'IDX:XGLD', 'https://www.tradingview.com/symbols/IDX-XGLD/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000597200', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Premier ETF FTSE Indonesia ESG', 'XIFE', 'IDX', 'IDX:XIFE', 'https://www.tradingview.com/symbols/IDX-XIFE/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000456902', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Premier ETF IDX High Dividend 20', 'XIHD', 'IDX', 'IDX:XIHD', 'https://www.tradingview.com/symbols/IDX-XIHD/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000372604', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Premier ETF Index IDX30', 'XIID', 'IDX', 'IDX:XIID', 'https://www.tradingview.com/symbols/IDX-XIID/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000441508', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PREMIER ETF INDONESIA FINANCIAL Units', 'XIIF', 'IDX', 'IDX:XIIF', 'https://www.tradingview.com/symbols/IDX-XIIF/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000189701', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Premier ETF IDX30', 'XIIT', 'IDX', 'IDX:XIIT', 'https://www.tradingview.com/symbols/IDX-XIIT/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000145307', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Premier ETF JII', 'XIJI', 'IDX', 'IDX:XIJI', 'https://www.tradingview.com/symbols/IDX-XIJI/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000154606', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Insight ETF FTSE Indonesia Low Volatility Factor Index', 'XILV', 'IDX', 'IDX:XILV', 'https://www.tradingview.com/symbols/IDX-XILV/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000440104', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Premier ETF MSCI Indonesia Large Cap', 'XIML', 'IDX', 'IDX:XIML', 'https://www.tradingview.com/symbols/IDX-XIML/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000430006', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Premier ETF IDX-Pefindo Prime Bank Units', 'XIPB', 'IDX', 'IDX:XIPB', 'https://www.tradingview.com/symbols/IDX-XIPB/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000555505', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Premier ETF Pefindo I-Grade', 'XIPI', 'IDX', 'IDX:XIPI', 'https://www.tradingview.com/symbols/IDX-XIPI/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000374105', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'REKSA DANA PREMIER ETF INDONESIA SOVEREIGN BONDS Units', 'XISB', 'IDX', 'IDX:XISB', 'https://www.tradingview.com/symbols/IDX-XISB/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000276706', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PREMIER ETF INDONESIA STATE-OWNED COMPANIES', 'XISC', 'IDX', 'IDX:XISC', 'https://www.tradingview.com/symbols/IDX-XISC/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000216207', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'PREMIER ETF SMINFRA18', 'XISI', 'IDX', 'IDX:XISI', 'https://www.tradingview.com/symbols/IDX-XISI/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000174000', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Premier ETF SRI-KEHATI', 'XISR', 'IDX', 'IDX:XISR', 'https://www.tradingview.com/symbols/IDX-XISR/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000186400', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah KIM Gold ETF Sharia Exchange Traded Fund Units', 'XKGS', 'IDX', 'IDX:XKGS', 'https://www.tradingview.com/symbols/IDX-XKGS/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000598802', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks KISI IDX30 ETF Units', 'XKID', 'IDX', 'IDX:XKID', 'https://www.tradingview.com/symbols/IDX-XKID/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000520103', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Kisi IDX Value30 ETF', 'XKIV', 'IDX', 'IDX:XKIV', 'https://www.tradingview.com/symbols/IDX-XKIV/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000416609', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks KISI MSCI Indonesia ETF Units', 'XKMS', 'IDX', 'IDX:XKMS', 'https://www.tradingview.com/symbols/IDX-XKMS/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000448206', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Mandiri ETF Emas Exchange Traded Fund Units', 'XMES', 'IDX', 'IDX:XMES', 'https://www.tradingview.com/symbols/IDX-XMES/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000597309', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Majoris Government Bonds ETF Indonesia Units', 'XMGB', 'IDX', 'IDX:XMGB', 'https://www.tradingview.com/symbols/IDX-XMGB/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000509502', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Majoris Pefindo I-Grade ETF Indonesia Units', 'XMIG', 'IDX', 'IDX:XMIG', 'https://www.tradingview.com/symbols/IDX-XMIG/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000397106', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Mandiri ETF LQ45 Units', 'XMLF', 'IDX', 'IDX:XMLF', 'https://www.tradingview.com/symbols/IDX-XMLF/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000501004', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Mandiri ETF Sri-Kehati', 'XMSK', 'IDX', 'IDX:XMSK', 'https://www.tradingview.com/symbols/IDX-XMSK/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000537404', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Pinnacle Core High Dividend ETF Units', 'XPDV', 'IDX', 'IDX:XPDV', 'https://www.tradingview.com/symbols/IDX-XPDV/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000289808', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Pinnacle FTSE Indonesia ETF', 'XPFT', 'IDX', 'IDX:XPFT', 'https://www.tradingview.com/symbols/IDX-XPFT/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000356201', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'REKSA DANA INDEKS BAHANA ETF PEFINDO I-GRADE Units', 'XPIN', 'IDX', 'IDX:XPIN', 'https://www.tradingview.com/symbols/IDX-XPIN/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000555802', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Pinnacle Enhanced Liquid ETF', 'XPLQ', 'IDX', 'IDX:XPLQ', 'https://www.tradingview.com/symbols/IDX-XPLQ/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000249109', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Pinnacle Indonesia ESG ETF', 'XPSG', 'IDX', 'IDX:XPSG', 'https://www.tradingview.com/symbols/IDX-XPSG/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000324803', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Panin ETF IDX30 Dinamis Units', 'XPTD', 'IDX', 'IDX:XPTD', 'https://www.tradingview.com/symbols/IDX-XPTD/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000391208', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indo ETF RDN Kas Bertumbuh Units', 'XRDN', 'IDX', 'IDX:XRDN', 'https://www.tradingview.com/symbols/IDX-XRDN/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000579703', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Simas ETF IDX30', 'XSBC', 'IDX', 'IDX:XSBC', 'https://www.tradingview.com/symbols/IDX-XSBC/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000358108', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Syailendra ETF Sharia Gold Exchange Traded Fund Units', 'XSGO', 'IDX', 'IDX:XSGO', 'https://www.tradingview.com/symbols/IDX-XSGO/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000597002', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Indeks Simas ETF JII', 'XSSI', 'IDX', 'IDX:XSSI', 'https://www.tradingview.com/symbols/IDX-XSSI/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000408200', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Indeks Sam Etf Sri-Kehati Units', 'XSSK', 'IDX', 'IDX:XSSK', 'https://www.tradingview.com/symbols/IDX-XSSK/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000437001', 'Undefined', 'Undefined'),
('Asia', 'Indonesia', 'Reksa Dana Syariah Trimegah Syariah ETF EMAS Exchange Traded Fund Units', 'XTRA', 'IDX', 'IDX:XTRA', 'https://www.tradingview.com/symbols/IDX-XTRA/', 'fund', 'etf', 'No', 'Indonesia', 'IDR', 'IDR', 'IDN000597101', 'Undefined', 'Undefined');

INSERT INTO public."Universe_Equity_Description" ("Region", "Market", "Country", "Exchange", "Ticker", "Company_Name",
    "TV_Sector", "TV_Industry", "ISIN", "Sector", "Industry") VALUES
('Asia', 'Emerging', 'Indonesia', 'IDX', 'AKKU', 'PT Anugerah Kagum Karya Utama Tbk', 'Consumer Services', 'Hotels/Resorts/Cruise lines', 'ID1000099609', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'ALTO', 'PT Tri Banyan Tirta Tbk', 'Consumer Non-Durables', 'Beverages: Non-Alcoholic', 'ID1000123805', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'BEBS', 'PT Berkah Beton Sadaya Tbk', 'Consumer Durables', 'Homebuilding', 'ID1000159601', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'BHAT', 'PT Bhakti Multi Artha Tbk', 'Commercial Services', 'Miscellaneous Commercial Services', 'ID1000155807', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'CRAB', 'PT Toba Surimi Industries Tbk', 'Consumer Non-Durables', 'Food: Meat/Fish/Dairy', 'ID1000171408', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'EDGE', 'PT Indointernet Tbk', 'Technology Services', 'Information Technology Services', 'ID1000159403', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'GAMA', 'PT Aksara Global Development Tbk', 'Finance', 'Real Estate Development', 'ID1000123201', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'GTBO', 'PT Garda Tujuh Buana Tbk', 'Energy Minerals', 'Coal', 'ID1000113004', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'HILL', 'PT Hillcon Tbk', 'Non-Energy Minerals', 'Precious Metals', 'ID1000186901', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'IBST', 'PT Inti Bangun Sejahtera Tbk', 'Industrial Services', 'Engineering & Construction', 'ID1000124506', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'INDX', 'PT Tanah Laut Tbk', 'Technology Services', 'Internet Software/Services', 'ID1000102007', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'PLIN', 'PT Plaza Indonesia Realty Tbk', 'Finance', 'Real Estate Development', 'ID1000105406', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'PMMP', 'PT Panca Mitra Multiperdana Tbk', 'Consumer Non-Durables', 'Food: Meat/Fish/Dairy', 'ID1000158306', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'RAFI', 'PT Sari Kreasi Boga Tbk', 'Consumer Services', 'Restaurants', 'ID1000170509', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'SUPR', 'PT Solusi Tunas Pratama Tbk', 'Industrial Services', 'Engineering & Construction', 'ID1000120702', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'TAYS', 'PT Jaya Swarasa Agung Tbk', 'Consumer Non-Durables', 'Food: Specialty/Candy', 'ID1000164601', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'TRUE', 'PT Triniti Dinamik Tbk', 'Finance', 'Real Estate Development', 'ID1000160807', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'UNSP', 'PT Bakrie Sumatera Plantations Tbk', 'Distribution Services', 'Wholesale Distributors', 'ID1000099708', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XBGS', 'Reksa Dana Syariah Batavia Gold Sharia ETF Exchange Traded Fund Units', 'Undefined', 'Undefined', 'IDN000598604', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XBID', 'Batavia IDX30 ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000381100', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XBIN', 'Reksa Dana Indeks Bahana ETF Bisnis-27', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000412004', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XBLQ', 'Reksa Dana Batavia Smart Liquid ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000333903', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XBSK', 'Reksa Dana Indeks Batavia SRI-KEHATI ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000384500', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XCEG', 'Reksa Dana Indeks Capital ETF IDX ESG Leaders', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000483708', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XCLQ', 'Reksa Dana Indeks Cipta ETF Indek LQ45', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000418902', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XDES', 'Reksa Dana Syariah Bri Mi Gold ETF Syariah Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000597408', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XDIF', 'BRI ETF Indonesia Top 40', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000335908', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XGLD', 'Premier ETF Gold Sharia Indonesia Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000597200', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIFE', 'Reksa Dana Indeks Premier ETF FTSE Indonesia ESG', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000456902', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIHD', 'Reksa Dana Indeks Premier ETF IDX High Dividend 20', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000372604', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIID', 'Reksa Dana Indeks Premier ETF Index IDX30', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000441508', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIIF', 'PREMIER ETF INDONESIA FINANCIAL Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000189701', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIIT', 'Reksa Dana Premier ETF IDX30', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000145307', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIJI', 'Reksa Dana Syariah Premier ETF JII', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000154606', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XILV', 'Reksa Dana Indeks Insight ETF FTSE Indonesia Low Volatility Factor Index', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000440104', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIML', 'Premier ETF MSCI Indonesia Large Cap', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000430006', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIPB', 'Reksa Dana Indeks Premier ETF IDX-Pefindo Prime Bank Units', 'Undefined', 'Undefined', 'IDN000555505', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XIPI', 'Premier ETF Pefindo I-Grade', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000374105', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XISB', 'REKSA DANA PREMIER ETF INDONESIA SOVEREIGN BONDS Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000276706', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XISC', 'PREMIER ETF INDONESIA STATE-OWNED COMPANIES', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000216207', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XISI', 'PREMIER ETF SMINFRA18', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000174000', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XISR', 'Premier ETF SRI-KEHATI', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000186400', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XKGS', 'Reksa Dana Syariah KIM Gold ETF Sharia Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000598802', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XKID', 'Reksa Dana Indeks KISI IDX30 ETF Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000520103', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XKIV', 'Reksa Dana Indeks Kisi IDX Value30 ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000416609', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XKMS', 'Reksa Dana Indeks KISI MSCI Indonesia ETF Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000448206', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XMES', 'Reksa Dana Syariah Mandiri ETF Emas Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000597309', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XMGB', 'Reksa Dana Majoris Government Bonds ETF Indonesia Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000509502', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XMIG', 'Reksa Dana Indeks Majoris Pefindo I-Grade ETF Indonesia Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000397106', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XMLF', 'Reksa Dana Indeks Mandiri ETF LQ45 Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000501004', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XMSK', 'Reksa Dana Indeks Mandiri ETF Sri-Kehati', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000537404', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPDV', 'Reksa Dana Pinnacle Core High Dividend ETF Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000289808', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPFT', 'Reksa Dana Indeks Pinnacle FTSE Indonesia ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000356201', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPIN', 'REKSA DANA INDEKS BAHANA ETF PEFINDO I-GRADE Units', 'Undefined', 'Undefined', 'IDN000555802', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPLQ', 'Reksa Dana Pinnacle Enhanced Liquid ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000249109', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPSG', 'Reksa Dana Pinnacle Indonesia ESG ETF', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000324803', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XPTD', 'Reksa Dana Indeks Panin ETF IDX30 Dinamis Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000391208', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XRDN', 'Reksa Dana Indo ETF RDN Kas Bertumbuh Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000579703', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XSBC', 'Reksa Dana Indeks Simas ETF IDX30', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000358108', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XSGO', 'Reksa Dana Syariah Syailendra ETF Sharia Gold Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000597002', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XSSI', 'Reksa Dana Syariah Indeks Simas ETF JII', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000408200', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XSSK', 'Reksa Dana Indeks Sam Etf Sri-Kehati Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000437001', 'Undefined', 'Undefined'),
('Asia', 'Emerging', 'Indonesia', 'IDX', 'XTRA', 'Reksa Dana Syariah Trimegah Syariah ETF EMAS Exchange Traded Fund Units', 'Miscellaneous', 'Investment Trusts/Mutual Funds', 'IDN000597101', 'Undefined', 'Undefined');

UPDATE public."Column_Catalog"
SET definition = 'Broad security classification, TradingView''s type: stock, fund (an exchange-traded fund; Type Specs etf, from 2026-11-05, EXEC-UNIVERSE-BROKER S1) or index (IHSG).'
WHERE table_schema = 'public' AND table_name = 'IDX_Stock_Universe' AND column_name = 'Security Type';

DO $post$
DECLARE n int; f int; h int; e int;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE "Security Type" = 'fund') INTO n, f
    FROM public."IDX_Stock_Universe" WHERE "Ticker" IN ('AKKU', 'ALTO', 'BEBS', 'BHAT', 'CRAB', 'EDGE', 'GAMA', 'GTBO', 'HILL', 'IBST', 'INDX', 'PLIN', 'PMMP', 'RAFI', 'SUPR', 'TAYS', 'TRUE', 'UNSP', 'XBGS', 'XBID', 'XBIN', 'XBLQ', 'XBSK', 'XCEG', 'XCLQ', 'XDES', 'XDIF', 'XGLD', 'XIFE', 'XIHD', 'XIID', 'XIIF', 'XIIT', 'XIJI', 'XILV', 'XIML', 'XIPB', 'XIPI', 'XISB', 'XISC', 'XISI', 'XISR', 'XKGS', 'XKID', 'XKIV', 'XKMS', 'XMES', 'XMGB', 'XMIG', 'XMLF', 'XMSK', 'XPDV', 'XPFT', 'XPIN', 'XPLQ', 'XPSG', 'XPTD', 'XRDN', 'XSBC', 'XSGO', 'XSSI', 'XSSK', 'XTRA');
    SELECT count(*) INTO h FROM public."IDX_Stock_Universe_History" WHERE "Ticker" IN ('AKKU', 'ALTO', 'BEBS', 'BHAT', 'CRAB', 'EDGE', 'GAMA', 'GTBO', 'HILL', 'IBST', 'INDX', 'PLIN', 'PMMP', 'RAFI', 'SUPR', 'TAYS', 'TRUE', 'UNSP', 'XBGS', 'XBID', 'XBIN', 'XBLQ', 'XBSK', 'XCEG', 'XCLQ', 'XDES', 'XDIF', 'XGLD', 'XIFE', 'XIHD', 'XIID', 'XIIF', 'XIIT', 'XIJI', 'XILV', 'XIML', 'XIPB', 'XIPI', 'XISB', 'XISC', 'XISI', 'XISR', 'XKGS', 'XKID', 'XKIV', 'XKMS', 'XMES', 'XMGB', 'XMIG', 'XMLF', 'XMSK', 'XPDV', 'XPFT', 'XPIN', 'XPLQ', 'XPSG', 'XPTD', 'XRDN', 'XSBC', 'XSGO', 'XSSI', 'XSSK', 'XTRA') AND valid_to IS NULL;
    SELECT count(*) INTO e FROM public."Universe_Equity_Description" WHERE "Ticker" IN ('AKKU', 'ALTO', 'BEBS', 'BHAT', 'CRAB', 'EDGE', 'GAMA', 'GTBO', 'HILL', 'IBST', 'INDX', 'PLIN', 'PMMP', 'RAFI', 'SUPR', 'TAYS', 'TRUE', 'UNSP', 'XBGS', 'XBID', 'XBIN', 'XBLQ', 'XBSK', 'XCEG', 'XCLQ', 'XDES', 'XDIF', 'XGLD', 'XIFE', 'XIHD', 'XIID', 'XIIF', 'XIIT', 'XIJI', 'XILV', 'XIML', 'XIPB', 'XIPI', 'XISB', 'XISC', 'XISI', 'XISR', 'XKGS', 'XKID', 'XKIV', 'XKMS', 'XMES', 'XMGB', 'XMIG', 'XMLF', 'XMSK', 'XPDV', 'XPFT', 'XPIN', 'XPLQ', 'XPSG', 'XPTD', 'XRDN', 'XSBC', 'XSGO', 'XSSI', 'XSSK', 'XTRA');
    IF n <> 63 OR f <> 45 OR h <> 63 OR e <> 63 THEN
        RAISE EXCEPTION 'postcheck: universe %, funds %, open history %, descriptions %', n, f, h, e;
    END IF;
END
$post$;

COMMIT;
