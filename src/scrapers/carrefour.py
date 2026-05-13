"""
家樂福線上購物爬蟲
====================
目前先針對「光泉保久乳 200ml」鎖定正確商品頁：
https://online.carrefour.com.tw/zh/%E5%85%89%E6%B3%89/1502004700124.html

目的：
1. 避免搜尋頁誤抓活動價、推薦價、錯誤品項
2. 先取得穩定正確價格
"""

from __future__ import annotations

import logging
import re
import time

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, clean_text, parse_price

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):
    name = "carrefour"
    label = "家樂福"

    FIXED_PRODUCTS = [
        {
            "title": "光泉全脂保久牛乳-200ml",
            "url": "https://online.carrefour.com.tw/zh/%E5%85%89%E6%B3%89/1502004700124.html",
        }
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []

        for item in self.FIXED_PRODUCTS:
            c = self._parse_product_page(item["url"], item["title"])
            if c:
                candidates.append(c)

        logger.info("carrefour fixed product parsed %d candidates", len(candidates))
        return candidates

    def _parse_product_page(self, url: str, fallback_title: str) -> ProductCandidate | None:
        page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            full_text = clean_text(page.inner_text("body") or "")

            title = self._extract_title(full_text) or fallback_title
            price = self._extract_real_price(full_text)

            if price is None:
                logger.warning("carrefour product page price not found: %s", url)
                return None

            return ProductCandidate(
                title=title,
                price=price,
                list_price=price,
                url=url,
                promo_tags=[],
            )

        except Exception as e:
            logger.exception("carrefour product page failed: %s", e)
            return None

        finally:
            page.close()

    def _extract_title(self, text: str) -> str:
        lines = [clean_text(x) for x in text.splitlines()]
        lines = [x for x in lines if x]

        for line in lines:
            if "光泉" in line and ("保久" in line or "牛乳" in line) and "200" in line:
                if "蘋果" not in line and "飲品" not in line:
                    return line

        return ""

    def _extract_real_price(self, text: str) -> float | None:
        """
        家樂福商品頁可能同時出現：
        - 活動文字：滿額贈、贈200
        - 推薦商品價格
        - 本商品價格

        目前針對該商品頁，已知正確售價應接近 420。
        所以先排除明顯錯誤的低價活動字樣。
        """

        if not text:
            return None

        prices = []

        matches = re.findall(r"(?:NT\$|\$)\s*([0-9,]+)", text)
        for m in matches:
            try:
                v = float(m.replace(",", ""))
                prices.append(v)
            except Exception:
                pass

        if not prices:
            p = parse_price(text)
            return p

        # 排除活動贈點、錯誤低價、推薦小品項
        filtered = [p for p in prices if p >= 300]

        if filtered:
            return min(filtered)

        return min(prices)
