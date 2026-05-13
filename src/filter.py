"""
商品過濾與首購偵測模組
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ProductCandidate:
    title: str
    price: float | None
    list_price: float | None
    url: str
    promo_tags: list[str]
    raw: dict | None = None


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in keywords)


def contains_all(text: str, keywords: Iterable[str]) -> bool:
    text = text.lower()
    return all(k.lower() in text for k in keywords)


def merge_channel_rules(product_config: dict, channel_name: str) -> dict:
    """
    合併共用規則 + 通路專屬規則
    """

    result = {
        "must_include": list(product_config.get("must_include", [])),
        "must_include_any": list(product_config.get("must_include_any", [])),
        "must_exclude": list(product_config.get("must_exclude", [])),
        "pack_keywords": list(product_config.get("pack_keywords", [])),
    }

    channel_rules = product_config.get("channel_rules", {})
    rule = channel_rules.get(channel_name, {})

    for k in result.keys():
        if k in rule:
            result[k] = rule[k]

    return result


def pick_best_match(
    candidates: list[ProductCandidate],
    product_config: dict,
    channel_name: str = "",
) -> ProductCandidate | None:

    rules = merge_channel_rules(product_config, channel_name)

    must_include = rules.get("must_include", [])
    must_include_any = rules.get("must_include_any", [])
    must_exclude = rules.get("must_exclude", [])
    pack_keywords = rules.get("pack_keywords", [])

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

    def sort_key(c: ProductCandidate):
        has_pack = 1 if (
            pack_keywords and contains_any(c.title, pack_keywords)
        ) else 0

        price = c.price if c.price is not None else float("inf")

        return (-has_pack, price)

    filtered.sort(key=sort_key)

    return filtered[0]


def detect_first_purchase(
    candidate: ProductCandidate,
    first_purchase_keywords: list[str],
) -> bool:

    text_to_check = " ".join(
        [candidate.title or ""] + (candidate.promo_tags or [])
    )

    return contains_any(text_to_check, first_purchase_keywords)


def is_abnormal_price(
    current_price: float,
    history_prices: list[float],
    ratio: float = 0.7,
    min_samples: int = 3,
) -> bool:

    if not history_prices or len(history_prices) < min_samples:
        return False

    median = statistics.median(history_prices)

    if median <= 0:
        return False

    return current_price < median * ratio
