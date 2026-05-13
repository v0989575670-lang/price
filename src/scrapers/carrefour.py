from __future__ import annotations

import logging
import re
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):

    SEARCH_BASE = "https://online.carrefour.com.tw/zh/search/?q="

    REQUIRED = [
        "光泉",
        "保久",
    ]

    EXCLUDE = [
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

    PREFER_24 = [
        "24",
        "24入",
        "24 入",
        "箱",
    ]

    def search(self, query: str) -> list[ProductCandidate]:

        search_query = "光泉 保久乳"

        url = self.SEARCH_BASE + quote(search_query)

        logger.info("carrefour url=%s", url)

        page = self.browser.new_page()

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            page.mouse.wheel(0, 4000)

            page.wait_for_timeout(3000)

            cards = page.locator("a")

            count = cards.count()

            logger.info("carrefour locator count=%s", count)

            results = []

            for i in range(count):

                try:

                    el = cards.nth(i)

                    text = el.inner_text(timeout=1000)

                    if not text:
                        continue

                    text = re.sub(r"\s+", " ", text)

                    logger.info("carrefour card=%s", text[:120])

                    # 必要字
                    if not all(k in text for k in self.REQUIRED):
                        continue

                    # 排除字
                    if any(k in text for k in self.EXCLUDE):
                        continue

                    # 必須有24入概念
                    if not any(k in text for k in self.PREFER_24):
                        continue

                    # 抓價格
                    prices = re.findall(r"\$?\s*([0-9]{3,5})", text)

                    valid_prices = []

                    for p in prices:

                        try:
                            v = int(p)

                            # 避免抓200ml
                            if v >= 300:
                                valid_prices.append(v)

                        except:
                            pass

                    if not valid_prices:
                        continue

                    price = min(valid_prices)

                    href = el.get_attribute("href")

                    if not href:
                        continue

                    if href.startswith("/"):
                        href = "https://online.carrefour.com.tw" + href

                    logger.info(
                        "carrefour matched title=%s price=%s",
                        text[:120],
                        price,
                    )

                    results.append(
                        ProductCandidate(
                            title=text[:200],
                            price=price,
                            list_price=price,
                            url=href,
                            promo_tags=[],
                            raw={"text": text},
                        )
                    )

                except Exception:
                    pass

            logger.info(
                "carrefour final results=%s",
                len(results),
            )

            return results

        except Exception as e:

            logger.exception(
                "carrefour scraper failed: %s",
                e,
            )

            return []

        finally:

            page.close()
