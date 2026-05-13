"""
家樂福線購爬蟲
==============
search URL: https://online.carrefour.com.tw/zh/search/?text=...

優先：JSON-LD（家樂福用 Hybris 平台，通常有完整 schema.org Product）
備援：CSS selector (.product-tile / .product-card / 等)
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


class CarrefourScraper(BaseScraper):
    name = "carrefour"
    label = "家樂福"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        return common_search_flow(
            self.browser,
            url,
            query,
            self.name,
            fallback_parser=self._css_fallback,
            extra_wait_sec=2.0,
        )

    def _css_fallback(self, page) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []
        possible_card_selectors = [
            "[data-pid]",
            ".product-tile",
            ".product-card",
            "li.product",
            "article.product",
            ".product-item",
        ]
        items = []
        for sel in possible_card_selectors:
            items = page.query_selector_all(sel)
            if items:
                logger.info("carrefour 用 %s 找到 %d 個元素", sel, len(items))
                break
        if not items:
            return []

        for it in items[:40]:
            try:
                title = ""
                for ts in [".product-tile-name", ".product-name", ".pdp-title", "h3", ".name", "a.link"]:
                    el = it.query_selector(ts)
                    if el:
                        title = clean_text(el.inner_text())
                        if title:
                            break
                if not title:
                    a = it.query_selector("a[href]")
                    if a:
                        title = clean_text(a.get_attribute("title") or a.inner_text())

                price_text = ""
                for ps in [".price", ".product-price", "[class*='price']", "span.value"]:
                    el = it.query_selector(ps)
                    if el:
                        price_text = clean_text(el.inner_text())
                        if price_text:
                            break
                price = parse_price(price_text)

                link_el = it.query_selector("a[href]")
                href = link_el.get_attribute("href") if link_el else None
                if href and href.startswith("/"):
                    href = "https://online.carrefour.com.tw" + href

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
                logger.debug("carrefour 解析錯誤：%s", e)
                continue
        return candidates
