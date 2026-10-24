#!/usr/bin/env python3
"""Build reviewed Indonesian presentation entries from an exported active semantic inventory.

Templates below are tied to the inspected canonical Feature implementations, not inferred from
arbitrary SQL column names. Unknown fields fail rather than receiving a generic guessed meaning.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

SEMANTIC_FIELDS=('feature_table','feature_column','version','grain','definition','calculation','unit',
 'null_rule','lookback_window','minimum_history','source_tables','source_columns',
 'analytical_interpretation','misuse_warning','recommended_use','historical_metadata_warning','point_in_time_safe')
TABLES={1:'Feature_01_Stock_Daily',2:'Feature_02_Broker_Rolling',3:'Feature_03_Stock_Broker_Daily',
 5:'Feature_05_Foreign_Domestic_Broker_Detail',6:'Feature_06_Foreign_Domestic'}
SOURCES=[t+s for t in TABLES.values() for s in ('','_INDEX')]

def semantic_hash(row):
    values={c:row.get(c) for c in SEMANTIC_FIELDS}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def explain_formula(formula,feature,scope):
    if feature!=6:return formula
    detail=TABLES[5]+('_INDEX' if scope=='index' else '')
    aliases={'FB':'foreign_buy_1d','FS':'foreign_sell_1d','DB':'domestic_buy_1d','DS':'domestic_sell_1d',
     'F':'foreign_net_1d (beli asing−jual asing)','D':'domestic_net_1d (beli domestik−jual domestik)',
     'T':'foreign_buy_1d+domestic_buy_1d (turnover)',
     'R':'foreign_net_1d/(foreign_buy_1d+domestic_buy_1d), turnover>0',
     'BF':'foreign_buy_freq_1d','SF':'foreign_sell_freq_1d','DBF':'domestic_buy_freq_1d','DSF':'domestic_sell_freq_1d',
     'FBL':f'SUM({detail}.buy_lots) untuk Foreign','FSL':f'SUM({detail}.sell_lots) untuk Foreign',
     'DBL':f'SUM({detail}.buy_lots) untuk Domestic','DSL':f'SUM({detail}.sell_lots) untuk Domestic'}
    used=[f'{a}={meaning}' for a,meaning in aliases.items() if re.search(r'\b'+a+r'\b',formula) and not re.search(r'\b'+a+r'\s*=',formula)]
    return formula+(' | '+ '; '.join(used) if used else '')

DIMENSIONS={
 'date':('Trade Date','Tanggal observasi perdagangan dari sumber.','Menghubungkan hasil dengan sesi transaksi yang tepat.'),
 'trade_date':('Trade Date','Tanggal sesi transaksi yang menjadi acuan nilai fitur.','Menghubungkan hasil dengan sesi transaksi yang tepat.'),
 'ticker':('Ticker','Kode instrumen yang menjadi identitas baris fitur.','Menentukan instrumen yang sedang dibaca; bukan kode broker.'),
 'broker':('Broker','Kode broker pelaksana transaksi sesuai sumber.','Memisahkan aktivitas masing-masing broker tanpa menebak identitas nasabahnya.'),
 'investor_type':('Investor Type','Jenis investor Domestic atau Foreign dari transaksi sumber.','Membedakan investor asing dan domestik; tidak ditentukan dari domisili broker.'),
 'market_board':('Market Board','Papan transaksi Regular, Nego, atau Tunai.','Membedakan pasar transaksi; angka antarpapan tidak dicampur otomatis.'),
 'broker_classification':('Broker Classification','Klasifikasi penggunaan broker dari profil broker yang berlaku saat kalkulasi.','Mengelompokkan broker menurut profil penggunaan; bukan bukti jenis investor atau profil historis.'),
 'sector':('Sector','Sektor dari data universe yang berlaku saat kalkulasi.','Mengelompokkan instrumen menurut klasifikasi terkini, bukan otomatis klasifikasi pada tanggal historis.'),
 'industry':('Industry','Industri dari data universe yang berlaku saat kalkulasi.','Memberi kelompok industri terkini untuk analisis dengan batasan metadata historis.'),
}
F1_FIXED={
 'close':('Close Price','Harga penutupan aktual dari candle sumber.','Menunjukkan level harga penutupan; untuk INDEX satuannya poin indeks.'),
 'volume':('Trading Volume','Volume transaksi dari sumber, tanpa pengisian sintetis.','Menunjukkan partisipasi transaksi. Volume IHSG yang tidak disediakan sumber tetap NULL.'),
 'abs_return_1d_pct':('Absolute Return 1D','Nilai absolut persentase perubahan penutupan satu sesi.','Mengukur besar pergerakan harian tanpa membedakan kenaikan dan penurunan.'),
 'volume_avg_20d':('Average Volume 20D','Rata-rata volume pada 20 observasi terakhir, termasuk hari ini.','Menjadi pembanding aktivitas volume terkini; membutuhkan 20 volume yang tersedia.'),
 'volume_std_20d':('Volume Standard Deviation 20D','Simpangan baku sampel volume 20 observasi terakhir.','Mengukur sebaran volume terhadap rata-ratanya, bukan arah harga.'),
 'volume_ratio_20d':('Volume Ratio 20D','Volume hari ini dibagi rata-rata volume 20 observasi.','Menunjukkan kelipatan aktivitas volume terhadap rata-rata; 1 berarti sama dengan rata-rata.'),
 'volume_zscore_20d':('Volume Z-Score 20D','Selisih volume hari ini dari rata-rata 20 observasi dibagi simpangan baku sampelnya.','Menunjukkan seberapa tidak biasa volume relatif terhadap sebaran 20 observasi; bukan probabilitas.'),
}
F3_FIXED={
 'total_buy_value':('Total Buy Value','Jumlah nilai beli bruto seluruh broker pada tanggal, instrumen, dan papan yang sama.','Menunjukkan nilai transaksi dari sisi pembeli; jangan dijumlahkan lagi dengan total jual sebagai turnover.'),
 'total_sell_value':('Total Sell Value','Jumlah nilai jual bruto seluruh broker pada tanggal, instrumen, dan papan yang sama.','Menunjukkan sisi penjual dari transaksi; selisih dengan total beli perlu pemeriksaan kualitas sumber.'),
 'active_broker_count':('Active Broker Count','Jumlah broker dengan nilai atau lot bruto beli/jual tidak nol, setelah kedua jenis investor digabung per broker.','Mengukur luas partisipasi broker; broker aktif dengan net nol tetap dihitung.'),
 'net_buy_broker_count':('Net Buy Broker Count','Jumlah broker yang nilai beli dikurangi nilai jualnya positif setelah penggabungan jenis investor.','Menunjukkan banyaknya broker pembeli bersih, bukan besarnya pembelian mereka.'),
 'net_sell_broker_count':('Net Sell Broker Count','Jumlah broker dengan nilai net negatif setelah penggabungan jenis investor.','Menunjukkan banyaknya broker penjual bersih; tidak menghitung net nol.'),
 'net_buy_broker_ratio':('Net Buy Broker Ratio','Jumlah broker net buy dibagi jumlah broker aktif.','Menunjukkan bagian broker aktif yang menjadi pembeli bersih; fraksi 0,6 berarti 60%.'),
 'foreign_net_value':('Foreign Net Value','Nilai beli dikurangi nilai jual untuk transaksi berjenis investor Foreign.','Menunjukkan arus bersih investor asing, bukan arus broker berdomisili asing.'),
 'domestic_net_value':('Domestic Net Value','Nilai beli dikurangi nilai jual untuk transaksi berjenis investor Domestic.','Menunjukkan arus bersih investor domestik secara terpisah dari asing.'),
 'top_buyer':('Top Buyer Broker','Kode broker dengan net value positif terbesar; nilai seri diurutkan menurut kode broker naik.','Mengidentifikasi broker pembeli bersih terbesar setelah seluruh transaksi dalam lingkupnya dinetting.'),
 'top_buyer_net_value':('Top Buyer Net Value','Nilai net positif milik broker pembeli bersih terbesar.','Menunjukkan besarnya pembelian bersih broker teratas, bukan nilai beli brutonya.'),
 'top_seller':('Top Seller Broker','Kode broker dengan net value paling negatif; nilai seri diurutkan menurut kode broker naik.','Mengidentifikasi broker penjual bersih terbesar dalam lingkup yang sama.'),
 'top_seller_net_value':('Top Seller Net Value','Nilai net paling negatif milik broker penjual bersih terbesar.','Menunjukkan besarnya penjualan bersih dalam angka bertanda negatif.'),
 'top3_buyer_net_value':('Top 3 Buyer Net Value','Jumlah net value positif tiga broker pembeli bersih terbesar, atau semua pembeli jika kurang dari tiga.','Menunjukkan jumlah pembelian bersih yang terkumpul pada tiga broker teratas.'),
 'positive_net_value_total':('Total Positive Net Value','Jumlah net value semua broker yang positif, sesudah transaksi dinetting per broker.','Menjadi dasar pembanding konsentrasi pembelian bersih; bukan total nilai beli bruto.'),
 'top3_buyer_share':('Top 3 Buyer Share','Jumlah net positif tiga broker teratas dibagi jumlah net positif seluruh broker.','Mengukur porsi pembelian bersih positif pada tiga broker teratas; 0,6 berarti 60%.'),
 'broker_concentration_hhi':('Broker Concentration HHI','Jumlah kuadrat porsi absolut net value setiap broker terhadap total absolut net seluruh broker.','Mengukur konsentrasi distribusi net broker. Pada INDEX kolom ini sengaja NULL sesuai keputusan pengguna.'),
}

def describe(feature,c):
    if c in DIMENSIONS:return (*DIMENSIONS[c],'dimension')
    if c=='calculated_at':return ('Calculated At','Waktu hasil fitur dihitung oleh script.','Membedakan waktu kalkulasi dari tanggal perdagangan; bukan indikator pasar.','metadata')
    if c=='source_balance_gap':return ('Source Balance Gap','Penanda ketidakseimbangan nilai beli dan jual pada data sumber dalam lingkup terkait.','Memperingatkan keterbatasan sumber. Pada INDEX, satu simbol yang bermasalah tetap ditandai meskipun gap simbol lain saling menghapus.','quality')
    if c in ('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows'):
        labels={'frequency_source_rows':'Frequency Source Rows','buy_freq_known_rows':'Known Buy Frequency Rows','sell_freq_known_rows':'Known Sell Frequency Rows','buy_freq_missing_rows':'Missing Buy Frequency Rows','sell_freq_missing_rows':'Missing Sell Frequency Rows'}
        meaning={'frequency_source_rows':'Jumlah baris sumber penyumbang agregasi frekuensi.','buy_freq_known_rows':'Jumlah baris sumber dengan frekuensi beli yang diketahui.','sell_freq_known_rows':'Jumlah baris sumber dengan frekuensi jual yang diketahui.','buy_freq_missing_rows':'Jumlah baris sumber dengan frekuensi beli yang tidak diketahui.','sell_freq_missing_rows':'Jumlah baris sumber dengan frekuensi jual yang tidak diketahui.'}
        return labels[c],meaning[c],'Mengukur kelengkapan input, bukan jumlah transaksi, broker, atau konstituen indeks.','quality'
    if feature==1:
        if c in F1_FIXED:return (*F1_FIXED[c],'metric')
        if m:=re.fullmatch(r'close_(\d+)d_ago',c):
            n=m[1];return f'Close {n}D Ago',f'Harga penutupan {n} observasi perdagangan sebelum tanggal ini.','Menjadi harga pembanding return; hari kalender tanpa observasi tidak dihitung.','metric'
        if m:=re.fullmatch(r'return_(\d+)d_pct',c):
            n=m[1];return f'Return {n}D (%)',f'Persentase perubahan harga penutupan terhadap penutupan {n} observasi sebelumnya.','Positif berarti harga naik dan negatif berarti turun selama rentang tersebut; bukan rata-rata return harian.','metric'
        if m:=re.fullmatch(r'volatility_(\d+)d_(ann|change)_pct',c):
            n,kind=m.groups()
            if kind=='ann':return f'Annualized Volatility {n}D (%)',f'Simpangan baku sampel return harian selama {n} observasi, disetahunkan dengan akar 252 lalu dikali 100.','Mengukur besar variasi return, bukan arah harga; angka tahunan merupakan skala pembanding, bukan prediksi.','metric'
            return f'Volatility Change {n}D (%)',f'Persentase perubahan volatilitas jendela {n} observasi dibanding nilai volatilitas yang sama {n} observasi sebelumnya.','Positif berarti volatilitas meningkat terhadap pembanding; bukan kenaikan harga.','metric'
        if m:=re.fullmatch(r'high_(\d+)d',c):
            n=m[1];return f'Highest Close {n}D',f'Penutupan tertinggi pada {n} observasi terakhir, termasuk hari ini.','Memberi acuan posisi harga terhadap penutupan tertinggi; bukan intraday high.','metric'
        if m:=re.fullmatch(r'drawdown_(\d+)d_pct',c):
            n=m[1];return f'Drawdown from Highest Close {n}D (%)',f'Persentase selisih penutupan kini terhadap penutupan tertinggi pada {n} observasi terakhir.','Nol berarti berada di penutupan tertinggi jendela; negatif berarti berada di bawahnya.','metric'
    if feature==2:
        if m:=re.fullmatch(r'(buy|sell|net)_(value|lots)_(\d+)d',c):
            side,measure,n=m.groups();noun='nilai' if measure=='value' else 'lot';direction={'buy':'beli','sell':'jual','net':'beli dikurangi jual'}[side]
            return f'{side.title()} {measure.title()} {n}D',f'Jumlah {noun} {direction} broker untuk jenis investor dan papan yang sama selama {n} sesi.','Mengukur aktivitas bruto untuk buy/sell atau arah dan besarnya aktivitas bersih untuk net; sesi tanpa aktivitas broker menyumbang nol.','metric'
        if m:=re.fullmatch(r'(buy_days|sell_days|active_days|stock_trading_days|buy_day_ratio|buy_share_active_days)_(\d+)d',c):
            kind,n=m.groups();v={
             'buy_days':('Net Buy Days',f'Jumlah sesi dengan net value broker positif dalam {n} sesi.','Mengukur persistensi pembelian bersih, bukan jumlah order.'),
             'sell_days':('Net Sell Days',f'Jumlah sesi dengan net value broker negatif dalam {n} sesi.','Mengukur persistensi penjualan bersih; net nol tidak dihitung.'),
             'active_days':('Active Days',f'Jumlah sesi dengan nilai atau lot bruto broker tidak nol dalam {n} sesi.','Menunjukkan seberapa sering broker berpartisipasi; net nol dapat tetap aktif.'),
             'stock_trading_days':('Trading Sessions',f'Jumlah sesi pembentuk jendela penuh: {n}; NULL sebelum jendela lengkap.','Menunjukkan panjang kalender observasi; pada INDEX memakai sesi pasar agregat.'),
             'buy_day_ratio':('Net Buy Day Ratio',f'Jumlah sesi net buy dibagi {n} sesi penuh.','Mengukur frekuensi pembelian bersih terhadap seluruh sesi jendela; satuannya fraksi.'),
             'buy_share_active_days':('Net Buy Share of Active Days',f'Jumlah sesi net buy dibagi jumlah sesi aktif pada jendela {n} sesi.','Mengukur kecenderungan membeli bersih ketika broker aktif; berbeda dari rasio terhadap semua sesi.')}
            label,definition,meaning=v[kind];return f'{label} {n}D',definition,meaning,'metric'
        if m:=re.fullmatch(r'net_value_(zscore|percentile)_(\d+)d',c):
            kind,n=m.groups()
            if kind=='zscore':return f'Net Value Z-Score {n}D',f'Net value {n} sesi dibanding rata-rata 252 nilai rolling sebelumnya, dibagi simpangan baku sampelnya.','Mengukur keanehan arus broker relatif terhadap riwayatnya sendiri; hari ini tidak masuk baseline.','metric'
            return f'Net Value Percentile {n}D',f'Persentil midrank net value {n} sesi terhadap 252 nilai rolling sebelumnya.','Menunjukkan posisi relatif arus broker dalam riwayatnya sendiri, bukan peringkat antarbroker.','metric'
        if c=='positive_net_value_20d':return 'Positive Net Value 20D','Jumlah net value harian yang positif dalam 20 sesi; hari negatif tidak menguranginya.','Menunjukkan total pembelian bersih pada hari positif, berbeda dari net total 20 sesi.','metric'
        if c=='largest_buy_day_20d':return 'Largest Net Buy Day 20D','Net value positif harian terbesar pada 20 sesi terakhir.','Menunjukkan besarnya hari pembelian bersih paling dominan; NULL jika tidak ada hari positif.','metric'
        if c=='largest_buy_day_share_20d':return 'Largest Net Buy Day Share 20D','Net positif harian terbesar dibagi jumlah seluruh net positif pada 20 sesi.','Mengukur ketergantungan pembelian bersih pada satu hari; satuannya fraksi.','metric'
    if feature==3:
        if c in F3_FIXED:return (*F3_FIXED[c],'metric')
        if m:=re.fullmatch(r'(institutional|retail|mixed|niche)_net_value',c):
            kind=m[1];return f'{kind.title()} Broker Net Value',f'Jumlah net value broker dengan klasifikasi profil penggunaan {kind}.','Menunjukkan arus kelompok broker berdasarkan profil terkini; tidak membuktikan identitas investor pada transaksi.','metric'
    if feature==5:
        if m:=re.fullmatch(r'(buy|sell|net)_(value|lots|freq)',c):
            side,measure=m.groups();noun={'value':'nilai transaksi','lots':'lot transaksi','freq':'frekuensi transaksi'}[measure];direction={'buy':'beli','sell':'jual','net':'beli dikurangi jual'}[side]
            meaning='Menunjukkan banyaknya transaksi yang diketahui, bukan jumlah investor. Input tidak diketahui tidak diubah menjadi nol.' if measure=='freq' else 'Menunjukkan aktivitas bruto untuk beli/jual atau posisi bersih untuk net pada broker, jenis investor, dan papan yang sama.'
            return f'{side.title()} '+{'value':'Value','lots':'Lots','freq':'Frequency'}[measure],f'Jumlah {noun} {direction} pada tanggal perdagangan tersebut.',meaning,'metric'
    if feature==6:
        if m:=re.fullmatch(r'(foreign|domestic)_(buy|sell|net)_1d',c):
            who,side=m.groups();party='asing' if who=='foreign' else 'domestik';direction={'buy':'beli bruto','sell':'jual bruto','net':'beli dikurangi jual'}[side]
            return f'{who.title()} {side.title()} Value 1D',f'Jumlah nilai {direction} investor {party} pada satu sesi dan papan.','Menunjukkan arus investor dari jenis investor sumber; broker pelaksana tidak menentukan investor asing/domestik.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_cumulative_net',c):
            who=m[1];party='asing' if who=='foreign' else 'domestik'
            return f'{who.title()} Cumulative Net',f'Akumulasi nilai beli dikurangi jual investor {party} sejak awal histori sumber yang tersedia.','Menunjukkan saldo arus historis, termasuk saldo lama simbol yang tidak bertransaksi pada tanggal terbaru. Perbandingan perlu baseline yang sama.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_net_(\d+)d',c):
            who,n=m.groups();party='asing' if who=='foreign' else 'domestik';return f'{who.title()} Net Value {n}D',f'Jumlah net value investor {party} selama {n} sesi terakhir.','Menunjukkan arah dan besarnya arus bersih dalam jendela penuh, bukan cumulative sejak awal histori.','metric'
        if m:=re.fullmatch(r'foreign_net_turnover_ratio_(\d+)d',c):
            n=m[1];return f'Foreign Net / Turnover {n}D (%)',f'100 dikali jumlah net value asing dibagi jumlah turnover pada {n} sesi; turnover adalah total nilai beli asing dan domestik.','Mengukur intensitas arus bersih asing relatif terhadap nilai transaksi pasar; memakai rasio jumlah, bukan rata-rata atau jumlah persentase per simbol.','metric'
        if m:=re.fullmatch(r'foreign_(buy|sell)_share_1d',c):
            side=m[1];return f'Foreign {side.title()} Value Share 1D (%)',f'Persentase nilai {"beli" if side=="buy" else "jual"} asing terhadap turnover satu sesi.','Menunjukkan porsi nilai sisi asing terhadap turnover; ketidakseimbangan sumber perlu dibaca bersama source_balance_gap.','metric'
        if m:=re.fullmatch(r'foreign_(buy|sell)_days_(\d+)d',c):
            side,n=m.groups();return f'Foreign Net {side.title()} Days {n}D',f'Jumlah sesi dengan net asing {"positif" if side=="buy" else "negatif"} dalam {n} sesi; net nol tidak dihitung.','Mengukur konsistensi arah arus asing, bukan frekuensi transaksi atau besarnya nilai.','metric'
        if m:=re.fullmatch(r'foreign_net_(zscore|percentile)_(\d+)d_base(\d+)d',c):
            kind,n,base=m.groups();label='Z-Score' if kind=='zscore' else 'Percentile'
            return f'Foreign Net {label} {n}D / {base}D Baseline',f'Net asing {n} sesi dibanding {base} nilai rolling sebelumnya, memakai {"selisih dari rata-rata dibagi simpangan baku sampel" if kind=="zscore" else "persentil midrank"}; hari ini dikecualikan.','Menunjukkan posisi arus asing relatif terhadap riwayat sendiri; bukan peringkat antar saham dan bukan probabilitas naik.','metric'
        if m:=re.fullmatch(r'foreign_flow_vs_prev_(\d+)d',c):
            n=m[1];return f'Foreign Flow Change vs Previous {n}D',f'Net asing {n} sesi terakhir dikurangi net asing {n} sesi sebelumnya yang tidak bertumpang tindih.','Positif berarti arus bersih meningkat dibanding periode sebelumnya; satuannya IDR, bukan persen.','metric'
        if m:=re.fullmatch(r'foreign_strength_(\d+)d',c):
            n=m[1];return f'Foreign Strength {n}D',f'Skor arah arus asing: 100 × jumlah rasio net asing/turnover dibagi jumlah nilai absolut rasio tersebut selama {n} sesi.','Mendekati +100 berarti rasio arus cenderung searah net buy; mendekati −100 berarti net sell. Tidak mengukur keuntungan harga atau memprediksi return.','metric'
        if c=='foreign_strength_momentum_5d':return 'Foreign Strength Momentum 5D','Foreign Strength 20D saat ini dikurangi nilainya lima sesi sebelumnya.','Mengukur perubahan skor konsistensi arah arus dalam poin skor, bukan persentase return.','metric'
        if c=='foreign_value_freq_sign_mismatch_1d':return 'Foreign Value / Frequency Direction Mismatch 1D','Penanda bahwa tanda net value asing berbeda dengan tanda frekuensi beli dikurangi frekuensi jual asing.','True berarti arah nilai dan jumlah transaksi berbeda; dapat mencerminkan perbedaan ukuran transaksi. NULL jika tanda nol atau frekuensi tidak tersedia.','quality'
        if m:=re.fullmatch(r'(foreign|domestic)_(buy|sell)_freq_1d',c):
            who,side=m.groups();return f'{who.title()} {side.title()} Frequency 1D',f'Jumlah frekuensi {"beli" if side=="buy" else "jual"} investor {"asing" if who=="foreign" else "domestik"} satu sesi.','Menunjukkan transaksi yang diketahui. Untuk INDEX, jumlah parsial tetap tersedia dan dibaca bersama kolom kelengkapan input.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_freq_imbalance_(\d+)d',c):
            who,n=m.groups();return f'{who.title()} Frequency Imbalance {n}D (%)',f'100 × (frekuensi beli − jual)/(frekuensi beli + jual) investor {"asing" if who=="foreign" else "domestik"} selama {n} sesi.','Mengukur dominasi jumlah transaksi beli atau jual, bukan dominasi nilainya; NULL jika input frekuensi tidak lengkap.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_(buy|sell)_freq_share_1d',c):
            who,side=m.groups();return f'{who.title()} {side.title()} Frequency Share 1D (%)',f'Persentase frekuensi {"beli" if side=="buy" else "jual"} kelompok investor terhadap seluruh frekuensi pada sisi yang sama.','Menunjukkan kontribusi jumlah transaksi suatu kelompok investor; berbeda dari porsi nilai transaksi.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_avg_(buy|sell)_(value|lots)_per_freq_1d',c):
            who,side,measure=m.groups();noun='nilai' if measure=='value' else 'lot'
            return f'{who.title()} Average {side.title()} {measure.title()} per Transaction 1D',f'Jumlah {noun} {"beli" if side=="buy" else "jual"} dibagi frekuensi pada sisi dan kelompok investor yang sama.','Mengukur rata-rata ukuran transaksi; tidak membuktikan jumlah investor atau kepemilikan institusi.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_buy_sell_ticket_ratio_1d',c):
            who=m[1];return f'{who.title()} Buy / Sell Ticket Ratio 1D','Rata-rata nilai per transaksi beli dibagi rata-rata nilai per transaksi jual pada kelompok investor yang sama.','Di atas 1 berarti ukuran rata-rata transaksi beli lebih besar daripada jual; tidak otomatis berarti net buy.','metric'
        if m:=re.fullmatch(r'(foreign|domestic)_(buy|sell)_(freq_share|value_per_freq)_change_5d_vs_prev20d',c):
            who,side,measure=m.groups();label='Frequency Share' if measure=='freq_share' else 'Value per Transaction'
            definition='Porsi frekuensi lima sesi terakhir dikurangi porsi frekuensi 20 sesi tepat sebelumnya, dari jumlah tiap jendela.' if measure=='freq_share' else 'Persentase perubahan rata-rata nilai per transaksi lima sesi terakhir terhadap 20 sesi tepat sebelumnya, dari jumlah tiap jendela.'
            meaning='Mengukur perubahan porsi aktivitas dalam poin persentase; bukan persen pertumbuhan.' if measure=='freq_share' else 'Mengukur perubahan ukuran transaksi rata-rata dalam persen, bukan perubahan nilai total.'
            return f'{who.title()} {side.title()} {label} Change 5D vs Previous 20D',definition,meaning,'metric'
    raise ValueError(f'No reviewed vocabulary template for Feature{feature:02d}.{c}')

def build(row):
    table=row.get('feature_table',row.get('table_name'));c=row.get('feature_column',row.get('column_name'))
    f=int(table.split('_')[1]);scope='index' if table.endswith('_INDEX') else 'stock'
    label,definition,meaning,kind=describe(f,c)
    if scope=='index' and f in (2,3,5,6) and kind=='metric':definition+=' Lingkup INDEX menggabungkan seluruh simbol transaksi sumber, bukan hanya saham atau konstituen resmi IHSG.'
    if scope=='index' and c=='broker_concentration_hhi':definition='Sengaja NULL pada agregat INDEX sesuai keputusan pengguna; formula HHI saham tidak diterapkan.'
    if scope=='index' and c=='ticker':definition='Kode indeks yang tervalidasi pada IDX_Stock_Universe dengan Security Type=index.'
    if scope=='stock' and f==6 and c.endswith('cumulative_net'):meaning='Menunjukkan saldo arus sejak observasi pertama instrumen dan papan terkait; panjang histori antar instrumen dapat berbeda.'
    unit=row['unit']
    unit={'percent':'Persen (%)','percentage points':'Poin persentase','fraction':'Fraksi (0–1)',
     'shares':'Lembar saham','lots':'Lot','transactions':'Transaksi','source rows':'Baris sumber',
     'date':'Tanggal','days':'Sesi','sessions':'Sesi','flag':'Boolean','timestamp':'Timestamp',
     'standard deviations':'Simpangan baku','idr per transaction':'IDR per transaksi',
     'lots per transaction':'Lot per transaksi'}.get(unit.lower(),unit)
    if f==1 and (c=='close' or c.startswith('close_') or c in ('high_20d','high_60d')):unit='Poin indeks' if scope=='index' else 'IDR per saham'
    if f==1 and scope=='index' and c in ('volume','volume_avg_20d','volume_std_20d'):unit='Volume sumber; IHSG NULL'
    if c.startswith('foreign_strength_') and c!='foreign_strength_momentum_5d':unit='Skor −100 sampai +100'
    if c=='foreign_strength_momentum_5d':unit='Poin skor'
    formula=row['calculation']
    if c in ('ticker','date','trade_date','broker','investor_type','market_board','broker_classification','sector','industry'):formula='Salin identitas/metadata sumber sesuai grain; ticker INDEX ditentukan dari universe.' if scope=='index' else 'Salin identitas/metadata sumber sesuai grain.'
    if c.startswith('foreign_strength_') and c!='foreign_strength_momentum_5d':
        n=re.search(r'(\d+)d$',c)[1];formula=f'100 × Σ{n}(R) / Σ{n}(|R|); R=(foreign buy value−foreign sell value)/(foreign buy value+domestic buy value), turnover>0.'
    if scope=='index' and c=='broker_concentration_hhi':formula='NULL (kebijakan INDEX)'
    formula=explain_formula(formula,f,scope)
    caveat=row['misuse_warning']
    if scope=='stock' and f in (2,3,5,6):caveat+=' Scope stock menandai tabel non-INDEX, bukan jaminan setiap simbol adalah saham biasa. Sumber juga dapat memuat waran, right, dan instrumen lain; filter universe diperlukan untuk lingkup saham saja.'
    if scope=='index' and f in (2,3,5,6):caveat+=' Agregat seluruh simbol sumber, termasuk instrumen non-saham; bukan riwayat konstituen resmi IHSG. Sesi rolling memakai kalender pasar agregat.'
    if f in (2,6):caveat+=' D adalah sesi observasi, bukan hari kalender. Baseline statistik mengecualikan hari ini.'
    if scope=='index' and f==6 and ('freq' in c or 'ticket' in c) and kind=='metric':caveat+=' Jumlah frekuensi harian memakai input yang diketahui; rasio/ticket/rolling berbasis frekuensi tetap NULL bila jendela input tidak lengkap.'
    grain='ticker × date' if f==1 else 'ticker × broker × investor_type × market_board × date' if f in (2,5) else 'ticker × market_board × date'
    source=dict(row,feature_table=table,feature_column=c)
    return dict(source_schema='public',source_table=table,column_name=c,language_code='id-ID',feature_number=f,scope=scope,
     column_name_proper=label,formula=formula,unit=unit,definition=definition,what_it_tells_us=meaning,grain=grain,
     null_rule=row['null_rule'],lookback_window=row['lookback_window'],minimum_history=row['minimum_history'],caveat=caveat,
     column_kind=kind,display_order=row['ordinal_position'],source_feature_version=row['version'],source_semantic_hash=semantic_hash(source),
     review_status='VERIFIED',validation_evidence=['scripts/build_feature_vocabulary_seed.py','verification/ihsg_feature_aggregation/bulk/','FEATURE_VOCABULARY.md'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--catalog-json',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('database/feature_vocabulary_seed.json'));a=p.parse_args()
    data=json.loads(a.catalog_json.read_text());rows=data['columns'] if isinstance(data,dict) else data
    result=[build(r) for r in rows if r.get('feature_table',r.get('table_name')) in SOURCES]
    identities={(r['source_table'],r['column_name']) for r in result}
    if len(identities)!=len(result) or len(result)!=391:raise RuntimeError(f'Expected 391 unique reviewed entries, got {len(result)}/{len(identities)}')
    result.sort(key=lambda r:(r['feature_number'],r['scope'],r['display_order']))
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'entries':len(result),'output':str(a.output)}))

if __name__=='__main__':main()
