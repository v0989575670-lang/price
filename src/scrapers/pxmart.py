"""
全聯線購（pxgo）爬蟲
====================
search URL: https://www.pxgo.com.tw/search?query=...

優先：JSON-LD
備援：CSS selector
"""

from __future__ import annotations

import logging

from src.filter import ProductCandidate
from src.scrapers.base import (
    BaseScraper,
    clean_text,
    common_search_flow,
    parse_price,
)

logger = logging.getLogger(__name__)


class PxmartScraper(BaseScraper):
    name = "pxmart"
    label = "全聯"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        return common_search_flow(
            self.browser,
            url,
            query,
            self.name,
            fallback_parser=self._css_fallback,
            extra_wait_sec=3.0,   # pxgo 是 SPA，等久一點
        )

    def _css_fallback(self, page) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []
        possible_card_selectors = [
            ".product-card",
            ".product-item",
            "[class*='ProductCard']",
            "[class*='product-card']",
            "li.product",
            "article.product",
        ]
        items = []
        for sel in possible_card_selectors:
            items = page.query_selector_all(sel)
            if items:
                logger.info("pxmart 用 %s 找到 %d 個元素", sel, len(items))
                break
        if not items:
            return []

        for it in items[:40]:
            try:
                title = ""
                for ts in [".product-name", ".name", "h3", "[class*='title']", "[class*='name']", "a"]:
                    el = it.query_selector(ts)
                    if el:
                        title = clean_text(el.inner_text())
                        if title:
                            break

                price_text = ""
                for ps in [".price", "[class*='price']", "[class*='Price']"]:
                    el = it.query_selector(ps)
                    if el:
                        price_text = clean_text(el.inner_text())
                        if price_text:
                            break
                price = parse_price(price_text)

                link_el = it.query_selector("a[href]")
                href = link_el.get_attribute("href") if link_el else None
                if href and href.startswith("/"):
                    href = "https://www.pxgo.com.tw" + href

                if title and price:
                    candidates.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=href or "",
                            promo_tags=[],
                        )
                    )
            except Exception as e:
                logger.debug("pxmart 解析錯誤：%s", e)
                continue
        return candidates
