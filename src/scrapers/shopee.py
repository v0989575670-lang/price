"""
蝦皮購物 爬蟲 (Stub - 待第二階段實作)
====================================
蝦皮有 Cloudflare 與帳號登入限制，需要單獨設計反爬策略。
目前先回傳空清單，並在 email 標記「尚未實作」。
"""

from __future__ import annotations

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper


class ShopeeScraper(BaseScraper):
    name = "shopee"
    label = "蝦皮"
    is_stub = True

    def search(self, query: str) -> list[ProductCandidate]:
        return []
