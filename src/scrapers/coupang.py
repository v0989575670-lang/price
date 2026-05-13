"""
酷澎 (Coupang Taiwan) 爬蟲
=========================
search URL: https://www.tw.coupang.com/np/search?q=...

注意：酷澎反爬也很嚴。先試簡單路線，失敗時看 debug 截圖再決定方向。
"""

from __future__ import annotations

import logging
import time

from src.filter import ProductCandidate
from src.scrapers.base import (
    BaseScraper,
    clean_text,
    common_search_flow,
    parse_price,
)

logger = logging.getLogger(__name__)


class CoupangScraper(BaseScraper):
    name = "coupang"
    label = "酷澎"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        return common_search_flow(
            self.browser,
            url,
            query,
            self.name,
            fallback_parser=self._css_fallback,
            extra_wait_sec=4.0,
        )

    def _css_fallback(self, page) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []

        # 捲一下觸發 lazy load
        try:
            for _ in range(2):
                page.mouse.wheel(0, 1500)
                time.sleep(0.5)
        except Exception:
            pass

        possible_card_selectors = [
            "[class*='SearchProduct']",
            "li.search-product",
            "[data-product-id]",
            ".product",
            "li.product-item",
            "article",
        ]
        items = []
        for sel in possible_card_selectors:
            items = page.query_selector_all(sel)
            if items:
                logger.info("coupang 用 %s 找到 %d 個元素", sel, len(items))
                break
        if not items:
            return []

        for it in items[:40]:
            try:
                title = ""
                for ts in [
                    ".name",
                    ".product-name",
                    "[class*='title']",
                    "[class*='name']",
                    "a[title]",
                    "h3",
                ]:
                    el = it.query_selector(ts)
                    if el:
                        title = clean_text(el.get_attribute("title") or el.inner_text())
                        if title:
                            break

                price_text = ""
                for ps in [
                    ".price-value",
                    "[class*='price']",
                    "[class*='Price']",
                    "strong.price",
                ]:
                    el = it.query_selector(ps)
                    if el:
                        price_text = clean_text(el.inner_text())
                        if price_text:
                            break
                price = parse_price(price_text)

                link_el = it.query_selector("a[href]")
                href = link_el.get_attribute("href") if link_el else None
                if href and href.startswith("/"):
                    href = "https://www.tw.coupang.com" + href

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
                logger.debug("coupang 解析錯誤：%s", e)
                continue
        return candidates
