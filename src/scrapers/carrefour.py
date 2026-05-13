"""
家樂福線上購物爬蟲
====================
固定抓取指定商品頁，並監聽 Tagtoo 商品資料 API：
https://db-api.tagtoo.com.tw/products

目前目標：
光泉全脂保久牛乳-200ml
https://online.carrefour.com.tw/zh/%E5%85%89%E6%B3%89/1502004700124.html
"""

from __future__ import annotations

import logging
import time

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):
    name = "carrefour"
    label = "家樂福"

    FIXED_PRODUCTS = [
        {
            "key": "1502004700124",
            "title": "光泉全脂保久牛乳-200ml",
            "url": "https://online.carrefour.com.tw/zh/%E5%85%89%E6%B3%89/1502004700124.html",
        }
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []

        for item in self.FIXED_PRODUCTS:
            c = self._capture_product_api(item)
            if c:
                candidates.append(c)

        logger.info("carrefour parsed %d candidates", len(candidates))
        return candidates

    def _capture_product_api(self, item: dict) -> ProductCandidate | None:
        target_key = item["key"]
        fallback_title = item["title"]
        product_url = item["url"]

        captured: list[dict] = []

        page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        def handle_response(response):
            try:
                url = response.url
                if "db-api.tagtoo.com.tw/products" not in url:
                    return

                data = response.json()

                if isinstance(data, dict):
                    if str(data.get("key", "")) == target_key:
                        captured.append(data)

                elif isinstance(data, list):
                    for x in data:
                        if isinstance(x, dict) and str(x.get("key", "")) == target_key:
                            captured.append(x)

            except Exception as e:
                logger.debug("carrefour api response parse failed: %s", e)

        page.on("response", handle_response)

        try:
            logger.info("carrefour open fixed product: %s", product_url)
            page.goto(product_url, wait_until="domcontentloaded", timeout=45000)

            # 等待 API 回來
            for _ in range(10):
                if captured:
                    break
                time.sleep(1)

            # 滾動一下，避免 API 延遲載入
            if not captured:
                page.mouse.wheel(0, 1000)
                time.sleep(3)

            if not captured:
                logger.warning("carrefour api product not captured: %s", target_key)
                return None

            data = captured[0]

            title = (
                data.get("title")
                or data.get("name")
                or fallback_title
            )

            price = data.get("sale_price")
            if price is None:
                price = data.get("price")

            if price is None:
                logger.warning("carrefour api price missing: %s", data)
                return None

            try:
                price = float(price)
            except Exception:
                logger.warning("carrefour api price invalid: %s", price)
                return None

            link = data.get("link") or product_url

            logger.info("carrefour matched: %s / %s", title, price)

            return ProductCandidate(
                title=title,
                price=price,
                list_price=price,
                url=link,
                promo_tags=[],
                raw=data,
            )

        except Exception as e:
            logger.exception("carrefour fixed product failed: %s", e)
            return None

        finally:
            page.close()
