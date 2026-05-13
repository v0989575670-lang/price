"""
蝦皮 (Shopee) 爬蟲
==================
search URL: https://shopee.tw/search?keyword=...

注意：蝦皮反爬嚴格，headless Chromium 常被 Cloudflare 擋。
策略：
  1. 拉長等待時間（Shopee 商品 lazy load）
  2. 嘗試 JSON-LD（有時 Shopee 嵌 schema.org）
  3. 嘗試 CSS selector（'[data-sqe="item"]'）
  4. 都失敗存 debug，下一輪可考慮：
     - 用 mobile UA 換到行動版
     - 走 internal API `/api/v4/search/search_items`
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


class ShopeeScraper(BaseScraper):
    name = "shopee"
    label = "蝦皮"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        return common_search_flow(
            self.browser,
            url,
            query,
            self.name,
            fallback_parser=self._css_fallback,
            extra_wait_sec=5.0,  # Shopee lazy load 需要久一點
        )

    def _css_fallback(self, page) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []

        # 嘗試把 search results 區捲到底，觸發 lazy load
        try:
            for _ in range(3):
                page.mouse.wheel(0, 1500)
                time.sleep(0.5)
        except Exception:
            pass

        possible_card_selectors = [
            "[data-sqe='item']",
            ".shopee-search-item-result__item",
            ".col-xs-2-4",
            "[class*='SearchItem']",
            "li.shopee-search-item-result__item",
        ]
        items = []
        for sel in possible_card_selectors:
            items = page.query_selector_all(sel)
            if items:
                logger.info("shopee 用 %s 找到 %d 個元素", sel, len(items))
                break
        if not items:
            return []

        for it in items[:40]:
            try:
                title = ""
                for ts in [
                    "[data-sqe='name']",
                    ".shopee-search-item-result__item__name",
                    "[class*='item-name']",
                    "div.line-clamp-2",
                    "a[title]",
                ]:
                    el = it.query_selector(ts)
                    if el:
                        title = clean_text(el.get_attribute("title") or el.inner_text())
                        if title:
                            break

                price_text = ""
                for ps in [
                    ".shopee-price",
                    "[class*='price']",
                    "[class*='Price']",
                    "span.font-medium",
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
                    href = "https://shopee.tw" + href

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
                logger.debug("shopee 解析錯誤：%s", e)
                continue
        return candidates
