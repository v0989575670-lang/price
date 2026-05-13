from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class PxmartScraper(BaseScraper):
    name = "pxmart"
    label = "全聯"

    SEARCH_BASE = "https://pxbox.es.pxmart.com.tw/search/result?keyword="

    REQUIRED = ["光泉", "保久", "200"]

    EXCLUDE = [
        "蘋果", "珍穀", "堅果", "巧克力", "麥芽", "調味",
        "乳飲品", "飲品", "豆漿", "燕麥", "芝麻", "糙米",
        "薏仁", "高鈣", "低脂", "多口味", "萬丹", "福樂",
        "台東初鹿", "東海大學"
    ]

    PACK_KEYWORDS = [
        "24入", "24 入", "24瓶", "24罐", "24瓶/箱", "24",
        "6入)x4", "6入x4", "6入 x4", "6入)x4組",
        "x4組", "×4組", "200mlx6入"
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.SEARCH_BASE + quote("保久乳")

        page = self.browser.new_page(
            viewport={"width": 390, "height": 900},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )

        try:
            logger.info("pxmart direct search url=%s", url)

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)

            for _ in range(8):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(800)

            body_text = page.locator("body").inner_text(timeout=5000)
            logger.info("pxmart body preview=%s", re.sub(r"\s+", " ", body_text)[:800])

            elements = page.locator("div, a, li")
            count = elements.count()
            logger.info("pxmart elements count=%s", count)

            results: list[ProductCandidate] = []
            seen = set()

            for i in range(min(count, 1500)):
                try:
                    el = elements.nth(i)
                    text = el.inner_text(timeout=800)
                    text = re.sub(r"\s+", " ", text or "").strip()

                    if not text or "光泉" not in text:
                        continue

                    logger.info("pxmart card text=%s", text[:220])

                    if not all(k in text for k in self.REQUIRED):
                        continue

                    if any(k in text for k in self.EXCLUDE):
                        continue

                    if not any(k in text for k in self.PACK_KEYWORDS):
                        logger.info("pxmart skip no pack keyword: %s", text[:160])
                        continue

                    prices = re.findall(r"\$\s*([0-9,]+)", text)
                    valid_prices = []

                    for p in prices:
                        try:
                            v = int(p.replace(",", ""))
                            if v >= 300:
                                valid_prices.append(v)
                        except Exception:
                            pass

                    if not valid_prices:
                        logger.info("pxmart skip no valid price: %s", text[:160])
                        continue

                    price = min(valid_prices)
                    title = self._extract_title(text)

                    key = f"{title}-{price}"
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=url,
                            promo_tags=[],
                            raw={"text": text},
                        )
                    )

                    logger.info("pxmart matched title=%s price=%s", title, price)

                except Exception:
                    continue

            logger.info("pxmart final results=%s", len(results))

            if not results:
                self._save_debug(page, "no_results")

            return results

        except Exception as e:
            logger.exception("pxmart scraper failed: %s", e)
            try:
                self._save_debug(page, "exception")
            except Exception:
                pass
            return []

        finally:
            page.close()

    def _extract_title(self, text: str) -> str:
        parts = re.split(r"\$|首購價|贈品|補貨|購物車|加入|收藏", text)
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if "光泉" in p and "保久" in p and "200" in p:
                return p[:120]
        return text[:120]

    def _save_debug(self, page, reason: str) -> None:
        try:
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            ts = int(time.time())
            page.screenshot(path=str(debug_dir / f"pxmart_{ts}_{reason}.png"), full_page=True)
            (debug_dir / f"pxmart_{ts}_{reason}.html").write_text(page.content(), encoding="utf-8")
            logger.info("pxmart debug saved reason=%s", reason)
        except Exception as e:
            logger.warning("pxmart debug save failed: %s", e)
