#!/usr/bin/env python3
"""Run the fixed ten-question DeepSeek A/B suite through the durable Railway queue."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row


QUESTIONS = [
    ("S1", "Screen seluruh saham pada tanggal data harga terbaru. Tampilkan 10 ticker dengan return 20 hari tertinggi; sertakan return 5 dan 60 hari, volume_ratio_20d, volatility_20d_ann_pct, drawdown_60d_pct, sector, dan industry. Jelaskan pola yang terlihat, risikonya, dan caveat data yang material."),
    ("S2", "Pada tanggal data harga terbaru, screen saham yang return 5 hari dan 20 harinya positif, volume_ratio_20d minimal 1.5, serta drawdown_60d_pct tidak lebih buruk dari -10%. Rank 10 terbaik berdasarkan return_20d_pct, lalu jelaskan apakah momentumnya cukup didukung aktivitas volume dan bagaimana hasil itu dibandingkan dengan konteks pasar yang relevan."),
    ("S3", "Screen pemenang multi-periode pada tanggal data harga terbaru: return 5, 20, dan 60 hari semuanya harus positif. Rank 10 ticker berdasarkan return 60 hari. Untuk masing-masing tampilkan volume_ratio_20d dan volatility_20d_change_pct, lalu kelompokkan mana yang momentumnya relatif sehat dan mana yang perlu kewaspadaan karena volatilitas meningkat atau volume kurang mendukung."),
    ("S4", "Pada tanggal terbaru data broker saham, khusus market board Regular, screen 10 ticker dengan institutional_net_value paling tinggi. Sertakan foreign_net_value, retail_net_value, net_buy_broker_ratio, broker_concentration_hhi, top_buyer, dan top_seller. Jelaskan mana akumulasi yang tampak luas dan mana yang terkonsentrasi, tanpa menyamakan broker classification dengan investor type."),
    ("S5", "Gunakan tanggal bersama terbaru yang aman untuk Feature harga dan Feature broker saham. Cari kandidat Regular board yang termasuk kelompok return_20d_pct harga tertinggi dan pada hari yang sama memiliki institutional_net_value positif. Tampilkan kandidat terbaik dengan bukti return, volume_ratio_20d, institutional flow, net-buy broker breadth, dan concentration HHI. Bedakan sinyal yang didukung breadth dari yang hanya terkonsentrasi pada sedikit broker."),
    ("F1", "Jelaskan secara presisi apa arti Feature_01_Stock_Daily.volume_ratio_20d, formula dan unitnya, kapan nilainya NULL, bagaimana cara menginterpretasikan angka 2.0, serta dua penyalahgunaan analitis yang harus dihindari. Gunakan definisi katalog yang terverifikasi; tidak perlu mengambil data pasar bila definisinya sudah cukup."),
    ("F2", "Bandingkan BBCA, BBRI, BMRI, dan BBNI pada tanggal data harga bersama terbaru. Gunakan return 5, 20, dan 60 hari, volatility 20 hari, volume ratio 20 hari, dan drawdown 60 hari. Siapa yang paling kuat secara deskriptif saat itu, siapa paling berisiko, dan bukti apa yang mendasari kesimpulan? Jangan membuat klaim prediktif."),
    ("F3", "Sejak 1 Januari 2020 sampai tanggal data terbaru, cari episode ketika BBCA mencatat return harian negatif sedikitnya 5 observasi perdagangan berturut-turut. Laporkan episode terpanjang dan episode paling baru beserta tanggal dan panjang streak. Untuk episode yang menentukan kesimpulan, periksa konteks return dan volume di sekitar episode secara efisien; jangan scan quality seluruh periode kecuali ada indikasi masalah nyata."),
    ("F4", "Pada tanggal terbaru Feature broker rolling, untuk BBCA di Regular board, siapa 5 broker dan Investor Type dengan net_value_20d tertinggi? Sertakan investor_type, broker_classification, buy_day_ratio_20d, buy_share_active_days_20d, net_value_zscore_20d, dan largest_buy_day_share_20d. Nilai apakah akumulasinya persisten atau didominasi satu hari, dan jangan samakan Investor Type dengan domisili broker."),
    ("F5", "Pada tanggal data harga terbaru, identifikasi 5 observasi saham yang paling layak disebut anomali berdasarkan kombinasi return_1d_pct dan volume_zscore_20d. Investigasi apakah ekstrem itu source-valid, warning, atau invalid dengan quality check yang hanya dibatasi pada observasi relevan. Jelaskan mengapa anomali valid tidak boleh otomatis dibuang dan apa yang belum dapat disimpulkan darinya."),
]


def use_public_proxy(app_url: str, proxy_url: str) -> str:
    app = urlsplit(app_url)
    proxy = urlsplit(proxy_url)
    if not app.username or app.password is None or not proxy.hostname or proxy.port is None:
        raise RuntimeError("Application or proxy database URL is incomplete")
    return urlunsplit((
        app.scheme,
        f"{app.username}:{app.password}@{proxy.hostname}:{proxy.port}",
        app.path,
        app.query,
        app.fragment,
    ))


def result_row(connection: psycopg.Connection, request_id: str) -> dict:
    row = connection.execute(
        '''SELECT r.request_id,r.status,r.current_stage,r.analysis_ready_date,r.answer,
                  r.error_message,r.input_tokens,r.output_tokens,r.total_tokens,
                  r.tool_result_tokens,r.tool_call_count,r.tool_iteration_count,
                  r.context_compaction_count,r.peak_context_tokens,r.created_at,
                  r.started_at,r.completed_at,r.version_snapshot,
                  (SELECT count(*) FROM public."Analysis_Evidence" e
                   WHERE e.request_id=r.request_id) AS evidence_count,
                  (SELECT count(DISTINCT s.query_hash) FROM public."Analysis_Step_Log" s
                   WHERE s.request_id=r.request_id AND s.query_hash IS NOT NULL
                     AND s.tool_name=ANY(%s) AND s.status IN ('SUCCESS','COMPACTED'))
                      AS distinct_data_query_hashes,
                  (SELECT count(*) FROM public."Analysis_Step_Log" s
                   WHERE s.request_id=r.request_id AND s.tool_name='complete_analysis'
                     AND s.status IN ('SUCCESS','COMPACTED')) AS completion_success_count,
                  (SELECT count(*) FROM public."Analysis_Step_Log" s
                   WHERE s.request_id=r.request_id AND s.step_number>=1000000
                     AND s.status='FAILED') AS final_rejection_count,
                  (SELECT count(*) FROM public."Analysis_Model_Call" m
                   WHERE m.request_id=r.request_id) AS model_call_count
           FROM public."Analysis_Request" r WHERE r.request_id=%s''',
        ([
            "query_features", "get_timeseries", "compare_periods", "screen_features",
            "rank_features", "aggregate_features", "compare_groups", "find_condition_runs",
        ], request_id),
    ).fetchone()
    item = dict(row)
    for key in ("request_id",):
        item[key] = str(item[key])
    for key in ("analysis_ready_date", "created_at", "started_at", "completed_at"):
        if item.get(key) is not None:
            item[key] = item[key].isoformat()
    if row["started_at"] and row["completed_at"]:
        item["latency_seconds"] = round(
            (row["completed_at"] - row["started_at"]).total_seconds(), 3
        )
    else:
        item["latency_seconds"] = None
    cited = set((item.get("answer") or {}).get("evidence_ids") or [])
    if cited:
        matched = connection.execute(
            '''SELECT count(*) FROM public."Analysis_Evidence"
               WHERE request_id=%s AND evidence_id::text=ANY(%s)''',
            (request_id, sorted(cited)),
        ).fetchone()["count"]
    else:
        matched = 0
    item["cited_evidence_count"] = matched
    item["all_cited_evidence_persisted"] = bool(cited) and matched == len(cited)
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode-label", required=True)
    parser.add_argument("--wait-seconds", type=int, default=7200)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    app_url = os.environ.get("APP_DATABASE_URL", "")
    proxy_url = os.environ.get("POSTGRES_PUBLIC_URL", "")
    if not app_url or not proxy_url:
        raise RuntimeError("APP_DATABASE_URL and POSTGRES_PUBLIC_URL are required")
    url = use_public_proxy(app_url, proxy_url)
    started = datetime.now(timezone.utc)
    reference = f"stress-ab-{args.mode_label}-{started.strftime('%Y%m%dT%H%M%SZ')}"

    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as connection:
        requests: dict[str, str] = {}
        for label, question in QUESTIONS:
            request_id = connection.execute(
                '''INSERT INTO public."Analysis_Request" (question,user_reference)
                   VALUES (%s,%s) RETURNING request_id''',
                (question, f"{reference}-{label}"),
            ).fetchone()["request_id"]
            requests[label] = str(request_id)
        print(json.dumps({"event": "submitted", "mode": args.mode_label, "requests": requests}), flush=True)

        deadline = time.monotonic() + args.wait_seconds
        pending = set(requests)
        while pending and time.monotonic() < deadline:
            for label in sorted(pending):
                row = connection.execute(
                    'SELECT status FROM public."Analysis_Request" WHERE request_id=%s',
                    (requests[label],),
                ).fetchone()
                if row["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                    pending.remove(label)
                    print(json.dumps({"event": "terminal", "mode": args.mode_label, "label": label, "status": row["status"]}), flush=True)
            if pending:
                time.sleep(5)

        results = []
        for label, question in QUESTIONS:
            item = result_row(connection, requests[label])
            item["label"] = label
            item["question"] = question
            results.append(item)
        report = {
            "mode": args.mode_label,
            "reference": reference,
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "timed_out_labels": sorted(pending),
            "results": results,
        }
        encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({
            "event": "complete",
            "mode": args.mode_label,
            "success": sum(item["status"] == "SUCCESS" for item in results),
            "failed": sum(item["status"] == "FAILED" for item in results),
            "total_input_tokens": sum(item["input_tokens"] or 0 for item in results),
            "total_output_tokens": sum(item["output_tokens"] or 0 for item in results),
            "total_latency_seconds": round(sum(item["latency_seconds"] or 0 for item in results), 3),
            "output": str(args.output) if args.output else None,
        }), flush=True)
        if pending:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
