"""
商品過濾與首購偵測模組
======================
1. 從爬蟲回傳的商品候選中，挑出最符合規格的那一筆
2. 偵測商品標題 / 促銷標籤是否有「首購、新客」等字眼
3. 與歷史價格比較，判斷是否為異常低價
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ProductCandidate:
    """單一爬蟲回傳的候選商品"""
    title: str               # 商品名稱
    price: float | None      # 顯示價（None 表示沒抓到）
    list_price: float | None # 標價 / 原價（沒有就跟 price 一樣）
    url: str                 # 商品頁連結
    promo_tags: list[str]    # 促銷標籤文字（首購、限時等）
    raw: dict | None = None  # 原始資料供 debug


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in keywords)


def contains_all(text: str, keywords: Iterable[str]) -> bool:
    text = text.lower()
    return all(k.lower() in text for k in keywords)


def pick_best_match(
    candidates: list[ProductCandidate],
    product_config: dict,
) -> ProductCandidate | None:
    """
    從一堆候選商品中，挑出最符合條件的那一個。

    篩選順序：
    1. 名稱必須包含 must_include 裡的所有字
    2. 名稱必須包含 must_include_any 裡至少一個字
    3. 名稱不能包含 must_exclude 裡任何字
    4. 含 pack_keywords 的優先（例如「24入」）
    5. 同條件下，price 較低的優先（通常代表整箱單瓶單價）
    """
    must_include = product_config.get("must_include", [])
    must_include_any = product_config.get("must_include_any", [])
    must_exclude = product_config.get("must_exclude", [])
    pack_keywords = product_config.get("pack_keywords", [])

    filtered: list[ProductCandidate] = []
    for c in candidates:
        title = c.title or ""
        if must_include and not contains_all(title, must_include):
            continue
        if must_include_any and not contains_any(title, must_include_any):
            continue
        if must_exclude and contains_any(title, must_exclude):
            continue
        filtered.append(c)

    if not filtered:
        return None

    # 排序：先看有沒有 pack_keywords，再看價格
    def sort_key(c: ProductCandidate):
        has_pack = 1 if (pack_keywords and contains_any(c.title, pack_keywords)) else 0
        price = c.price if c.price is not None else float("inf")
        return (-has_pack, price)

    filtered.sort(key=sort_key)
    return filtered[0]


def detect_first_purchase(
    candidate: ProductCandidate,
    first_purchase_keywords: list[str],
) -> bool:
    """偵測商品是否為首購 / 新客優惠"""
    text_to_check = " ".join([candidate.title or ""] + (candidate.promo_tags or []))
    return contains_any(text_to_check, first_purchase_keywords)


def is_abnormal_price(
    current_price: float,
    history_prices: list[float],
    ratio: float = 0.7,
    min_samples: int = 3,
) -> bool:
    """
    判斷是否為異常低價。
    若歷史樣本不足，不判斷異常。
    """
    if not history_prices or len(history_prices) < min_samples:
        return False
    median = statistics.median(history_prices)
    if median <= 0:
        return False
    return current_price < median * ratio
