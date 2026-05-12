"""
歷史價格儲存模組
================
把每次抓到的價格存到 data/price_history.csv
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

CSV_PATH = Path("data/price_history.csv")
CSV_HEADERS = [
    "timestamp",
    "date",
    "time",
    "product",
    "channel",
    "matched_title",
    "list_price",
    "display_price",
    "is_first_purchase",
    "is_abnormal",
    "url",
    "note",
]


def ensure_csv():
    """確保 data 目錄與 CSV 檔存在"""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()


def append_records(records: Iterable[dict]):
    """附加多筆紀錄到 CSV"""
    ensure_csv()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        for r in records:
            # 補齊缺漏欄位
            row = {k: r.get(k, "") for k in CSV_HEADERS}
            writer.writerow(row)


def load_history(
    product: str,
    channel: str,
    exclude_first_purchase: bool = True,
) -> list[float]:
    """讀出某商品 × 某通路的歷史 display_price 數列（用於異常價判斷）"""
    if not CSV_PATH.exists():
        return []

    prices: list[float] = []
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("product") != product:
                continue
            if row.get("channel") != channel:
                continue
            if exclude_first_purchase and row.get("is_first_purchase") == "True":
                continue
            try:
                price = float(row.get("display_price") or 0)
                if price > 0:
                    prices.append(price)
            except (TypeError, ValueError):
                continue
    return prices


def get_last_price(product: str, channel: str) -> float | None:
    """取最近一筆價格（用來算「較上次」)"""
    if not CSV_PATH.exists():
        return None
    last: float | None = None
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("product") == product and row.get("channel") == channel:
                try:
                    last = float(row.get("display_price") or 0) or last
                except (TypeError, ValueError):
                    continue
    return last


def make_record(
    product: str,
    channel: str,
    matched_title: str = "",
    list_price: float | None = None,
    display_price: float | None = None,
    is_first_purchase: bool = False,
    is_abnormal: bool = False,
    url: str = "",
    note: str = "",
) -> dict:
    now = datetime.now()
    return {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "product": product,
        "channel": channel,
        "matched_title": matched_title or "",
        "list_price": list_price if list_price is not None else "",
        "display_price": display_price if display_price is not None else "",
        "is_first_purchase": str(is_first_purchase),
        "is_abnormal": str(is_abnormal),
        "url": url or "",
        "note": note or "",
    }
