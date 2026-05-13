from __future__ import annotations

import logging
import re

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):

    PRODUCT_URL = (
        "https://online.carrefour.com.tw/zh/%E5%85%89%E6%B3%89/1502004700124.html"
    )

    def search(self, query: str) -> list[ProductCandidate]:

        page = self.browser.new_page()

        try:
            logger.info("carrefour open product page")

            page.goto(
                self.PRODUCT_URL,
                wait_until="networkidle",
                timeout=60000,
            )

            html = page.content()

            # 找價格
            price_patterns = [
                r'"price":\s*([0-9]+)',
                r'"salePrice":\s*([0-9]+)',
                r'NT\$([0-9]+)',
            ]

            found_price = None

            for pattern in price_patterns:
                m = re.search(pattern, html)

                if m:
                    found_price = int(m.group(1))

                    # 避免抓到 200ml
                    if found_price >= 300:
                        break

            if not found_price:
                logger.warning("carrefour no valid price found")
                return []

            logger.info("carrefour matched price=%s", found_price)

            candidate = ProductCandidate(
                title="光泉全脂保久牛乳-200ml",
                price=found_price,
                list_price=found_price,
                url=self.PRODUCT_URL,
                promo_tags=[],
                raw={"html": "matched"},
            )

            return [candidate]

        except Exception as e:
            logger.exception("carrefour scraper failed: %s", e)
            return []

        finally:
            page.close()
