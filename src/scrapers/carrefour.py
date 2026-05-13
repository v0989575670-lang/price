from __future__ import annotations

import logging
import re
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):
    SEARCH_BASE = "https://online.carrefour.com.tw/zh/search/?q="

    REQUIRED = ["光泉", "保久", "200"]

    EXCLUDE = [
        "蘋果", "珍穀", "堅果", "巧克力", "麥芽", "調味",
        "乳飲品", "飲品", "豆漿", "燕麥", "芝麻", "糙米",
        "薏仁", "高鈣", "低脂", "多口味"
    ]

    PACK_KEYWORDS = ["24入", "24 入", "24瓶", "24罐", "24人", "箱"]

    def search(self, query: str) -> list[ProductCandidate]:
        search_query = "光泉 保久乳 200ml"
        url = self.SEARCH_BASE + quote(search_query)

        page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        )

        try:
            logger.info("carrefour search url=%s", url)

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(1000)

            links = page.locator("a[href*='.html']")
            count = links.count()
            logger.info("carrefour product links count=%s", count)

            results: list[ProductCandidate] = []

            for i in range(count):
                try:
                    a = links.nth(i)
                    href = a.get_attribute("href") or ""

                    if not href:
                        continue

                    if href.startswith("/"):
                        href = "https://online.carrefour.com.tw" + href

                    if "online.carrefour.com.tw" not in href:
                        continue

                    card_text = a.evaluate(
                        """
                        el => {
                            let p = el;
                            for (let i = 0; i < 7 && p; i++) {
                                const text = (p.innerText || '').trim();
                                if (
                                    text.includes('光泉') &&
                                    (text.includes('$') || text.includes('24') || text.includes('加入購物車'))
                                ) {
                                    return text;
                                }
                                p = p.parentElement;
                            }
                            return el.innerText || '';
                        }
                        """
                    )

                    text = re.sub(r"\s+", " ", card_text or "").strip()

                    if not text:
                        continue

                    logger.info("carrefour card text=%s", text[:200])

                    if not all(k in text for k in self.REQUIRED):
                        continue

                    if any(k in text for k in self.EXCLUDE):
                        continue

                    if not any(k in text for k in self.PACK_KEYWORDS):
                        logger.info("carrefour skip no pack keyword: %s", text[:120])
                        continue

                    prices = re.findall(r"(?:NT\$|\$)\s*([0-9,]+)", text)
                    valid_prices = []

                    for p in prices:
                        try:
                            v = int(p.replace(",", ""))
                            if v >= 300:
                                valid_prices.append(v)
                        except Exception:
                            pass

                    if not valid_prices:
                        logger.info("carrefour skip no valid price: %s", text[:120])
                        continue

                    price = min(valid_prices)
                    title = self._extract_title(text)

                    logger.info("carrefour matched title=%s price=%s", title, price)

                    results.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=href,
                            promo_tags=[],
                            raw={"text": text},
                        )
                    )

                except Exception as e:
                    logger.debug("carrefour parse item failed: %s", e)
                    continue

            logger.info("carrefour final results=%s", len(results))
            return results

        except Exception as e:
            logger.exception("carrefour scraper failed: %s", e)
            return []

        finally:
            page.close()

    def _extract_title(self, text: str) -> str:
        parts = re.split(r"\$|NT\$|加入購物車|查看", text)
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if "光泉" in p and ("保久" in p or "牛乳" in p) and "200" in p:
                return p[:120]
        return text[:120]
