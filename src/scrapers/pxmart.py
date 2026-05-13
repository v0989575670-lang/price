from __future__ import annotations

import logging
import re

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class PxmartScraper(BaseScraper):
    name = "pxmart"
    label = "全聯"

    SEARCH_URL = "https://pxbox.es.pxmart.com.tw/"

    REQUIRED = ["光泉", "保久", "200"]

    EXCLUDE = [
        "蘋果", "珍穀", "堅果", "巧克力", "麥芽", "調味",
        "乳飲品", "飲品", "豆漿", "燕麥", "芝麻", "糙米",
        "薏仁", "高鈣", "低脂", "多口味", "萬丹", "福樂",
        "台東初鹿", "東海大學"
    ]

    PACK_KEYWORDS = ["24入", "24 入", "24瓶", "24罐", "24瓶/箱", "24"]

    def search(self, query: str) -> list[ProductCandidate]:
        page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        )

        try:
            logger.info("pxmart open homepage")
            page.goto(self.SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            # 找搜尋框
            search_inputs = [
                "input[type='search']",
                "input[placeholder*='搜尋']",
                "input[placeholder*='請輸入']",
                "input",
            ]

            filled = False
            for sel in search_inputs:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        el.click(timeout=3000)
                        el.fill("保久乳")
                        el.press("Enter")
                        filled = True
                        logger.info("pxmart search input used: %s", sel)
                        break
                except Exception:
                    continue

            if not filled:
                logger.warning("pxmart search input not found")
                return []

            page.wait_for_timeout(8000)

            for _ in range(5):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(1000)

            # 用所有可能的商品卡片區塊掃描
            elements = page.locator("div, a, li")
            count = elements.count()
            logger.info("pxmart elements count=%s", count)

            results: list[ProductCandidate] = []
            seen = set()

            for i in range(min(count, 800)):
                try:
                    el = elements.nth(i)
                    text = el.inner_text(timeout=1000)
                    text = re.sub(r"\s+", " ", text or "").strip()

                    if not text:
                        continue

                    if "光泉" not in text:
                        continue

                    logger.info("pxmart card text=%s", text[:200])

                    if not all(k in text for k in self.REQUIRED):
                        continue

                    if any(k in text for k in self.EXCLUDE):
                        continue

                    if not any(k in text for k in self.PACK_KEYWORDS):
                        logger.info("pxmart skip no pack keyword: %s", text[:120])
                        continue

                    prices = re.findall(r"\$+\s*([0-9,]+)", text)
                    valid_prices = []

                    for p in prices:
                        try:
                            v = int(p.replace(",", ""))
                            if v >= 300:
                                valid_prices.append(v)
                        except Exception:
                            pass

                    if not valid_prices:
                        logger.info("pxmart skip no valid price: %s", text[:120])
                        continue

                    price = min(valid_prices)
                    title = self._extract_title(text)

                    if not title:
                        continue

                    key = f"{title}-{price}"
                    if key in seen:
                        continue
                    seen.add(key)

                    href = ""
                    try:
                        link = el.locator("a[href]").first
                        if link.count() > 0:
                            href = link.get_attribute("href") or ""
                    except Exception:
                        pass

                    if href.startswith("/"):
                        href = "https://pxbox.es.pxmart.com.tw" + href

                    results.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=href or self.SEARCH_URL,
                            promo_tags=[],
                            raw={"text": text},
                        )
                    )

                    logger.info("pxmart matched title=%s price=%s", title, price)

                except Exception:
                    continue

            logger.info("pxmart final results=%s", len(results))
            return results

        except Exception as e:
            logger.exception("pxmart scraper failed: %s", e)
            return []

        finally:
            page.close()

    def _extract_title(self, text: str) -> str:
        parts = re.split(r"\$|首購價|贈品|補貨|購物車|加入", text)
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if "光泉" in p and "保久" in p and "200" in p:
                return p[:120]
        return text[:120]
