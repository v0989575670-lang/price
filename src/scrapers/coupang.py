from __future__ import annotations

import logging
import re
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CoupangScraper(BaseScraper):

    SEARCH_BASE = "https://tw.coupang.com/np/search?q="

    REQUIRED = [
        "光泉",
        "成份無調整",
    ]

    EXCLUDE = [
        "蘋果",
        "巧克力",
        "堅果",
        "珍穀",
        "麥芽",
        "燕麥",
        "豆漿",
        "飲品",
    ]

    def search(self, query: str) -> list[ProductCandidate]:

        search_query = "光泉 成份無調整牛乳"

        url = self.SEARCH_BASE + quote(search_query)

        logger.info("coupang url=%s", url)

        page = self.browser.new_page()

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            # 往下滾動
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)

            cards = page.locator("li")

            count = cards.count()

            logger.info("coupang cards=%s", count)

            results = []

            for i in range(count):

                try:

                    el = cards.nth(i)

                    text = el.inner_text(timeout=1000)

                    if not text:
                        continue

                    text = re.sub(r"\s+", " ", text)

                    logger.info("coupang card=%s", text[:200])

                    if not all(k in text for k in self.REQUIRED):
                        continue

                    if any(k in text for k in self.EXCLUDE):
                        continue

                    if "24入" not in text and "24" not in text:
                        continue

                    # 關鍵：
                    # 只抓第一個價格
                    m = re.search(r"\$([0-9]{3,5})", text)

                    if not m:
                        continue

                    price = int(m.group(1))

                    # 避免抓首購優惠價
                    if price < 300:
                        continue

                    href = el.locator("a").first.get_attribute("href")

                    if not href:
                        continue

                    if href.startswith("/"):
                        href = "https://tw.coupang.com" + href

                    logger.info(
                        "coupang matched title=%s price=%s",
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
                "coupang final results=%s",
                len(results),
            )

            return results

        except Exception as e:

            logger.exception(
                "coupang scraper failed: %s",
                e,
            )

            return []

        finally:

            page.close()
