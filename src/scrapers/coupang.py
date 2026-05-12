"""
酷澎 (Coupang Taiwan) 爬蟲 (Stub - 待第二階段實作)
=================================================
"""

from __future__ import annotations

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper


class CoupangScraper(BaseScraper):
    name = "coupang"
    label = "酷澎"
    is_stub = True

    def search(self, query: str) -> list[ProductCandidate]:
        return []
