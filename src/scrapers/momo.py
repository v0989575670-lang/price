"""
MOMO 購物網 爬蟲（JSON-LD 結構化資料解析版）
"""

from __future__ import annotations

import logging

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, common_search_flow

logger = logging.getLogger(__name__)


class MomoScraper(BaseScraper):
    name = "momo"
    label = "MOMO"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        return common_search_flow(
            self.browser,
            url,
            query,
            self.name,
            fallback_parser=None,
            extra_wait_sec=1.0,
        )
