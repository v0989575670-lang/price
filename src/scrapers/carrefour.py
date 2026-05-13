from __future__ import annotations

import logging
import re
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):

    SEARCH_BASE = "https://online.carrefour.com.tw/zh/search/?q="

    REQUIRED_KEYWORDS = [
        "光泉",
        "保久",
        "200",
    ]

    PREFER_KEYWORDS = [
        "24",
        "24入",
        "24 入",
        "24瓶",
        "24罐",
        "箱",
    ]

    EXCLUDE_KEYWORDS = [
        "蘋果",
        "珍穀",
        "堅果",
        "巧克力",
        "麥芽",
        "調味",
        "乳飲品",
        "飲品",
        "豆漿",
        "燕麥",
    ]

    def search(self, query: str) -> list[ProductCandidate]:

        page = self.browser.new_page()

        try:

            search_query = "光泉 保久乳 200ml"

            url = self.SEARCH_BASE + quote(search_query)

            logger.info("carrefour search: %s", url)

            page.goto(
                url,
                wait_until="networkidle",
                timeout=60000,
            )

            page.mouse.wheel(0, 3000)

            html = page.content()

            # 抓商品區塊
            cards = re.findall(
                r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                re.S,
            )

            candidates: list[ProductCandidate] = []

            for href, block in cards:

                text = re.sub(r"<[^>]+>", " ", block)
                text = re.sub(r"\s+", " ", text).strip()

                if not text:
                    continue

                # 必要關鍵字
                if not all(k in text for k in self.REQUIRED_KEYWORDS):
                    continue

                # 排除關鍵字
                if any(k in text for k in self.EXCLUDE_KEYWORDS):
                    continue

                # 必須有 24 入相關
                if not any(k in text for k in self.PREFER_KEYWORDS):
                    continue

                # 抓價格
                prices = re.findall(r"\$([0-9]+)", text)

                valid_prices = []

                for p in prices:
                    try:
                        v = int(p)

                        # 避免抓到 200ml
                        if v >= 300:
                            valid_prices.append(v)

                    except:
                        pass

                if not valid_prices:
                    continue

                price = min(valid_prices)

                # 完整網址
                if href.startswith("/"):
                    product_url = "https://online.carrefour.com.tw" + href
                else:
                    product_url = href

                logger.info(
                    "carrefour matched title=%s price=%s",
                    text[:100],
                    price,
                )

                candidates.append(
                    ProductCandidate(
                        title=text[:200],
                        price=price,
                        list_price=price,
                        url=product_url,
                        promo_tags=[],
                        raw={"text": text},
                    )
                )

            logger.info(
                "carrefour final candidates=%d",
                len(candidates),
            )

            return candidates

        except Exception as e:
            logger.exception("carrefour scraper failed: %s", e)
            return []

        finally:
            page.close()
