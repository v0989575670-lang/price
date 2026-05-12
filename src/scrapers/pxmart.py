"""
全聯線購 爬蟲 (Stub - 待第二階段實作)
====================================
全聯目前線上購主要是 pxgo.com.tw，部分商品需登入才看得到價格。
"""

from __future__ import annotations

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper


class PxmartScraper(BaseScraper):
    name = "pxmart"
    label = "全聯"
    is_stub = True

    def search(self, query: str) -> list[ProductCandidate]:
        return []
