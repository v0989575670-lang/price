from __future__ import annotations

import logging
import re
import time
from pathlib import Path

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

    PACK_KEYWORDS = [
        "24入", "24 入", "24瓶", "24罐", "24瓶/箱", "24",
        "6入)x4", "6入x4", "6入 x4", "6入)x4組",
        "x4組", "×4組", "200mlx6入"
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        page = self.browser.new_page(
            viewport={"width": 390, "height": 900},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )

        try:
            logger.info("pxmart open homepage")
            page.goto(self.SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            # 嘗試點搜尋框
            search_text = "光泉 保久乳"

            input_selectors = [
                "input[type='search']",
                "input[placeholder*='搜尋']",
                "input",
                "textarea",
            ]

            filled = False

            for sel in input_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        loc.click(timeout=5000)
                        loc.fill(search_text)
                        page.wait_for_timeout(1000)
                        loc.press("Enter")
                        filled = True
                        logger.info("pxmart filled search by selector=%s", sel)
                        break
                except Exception as e:
                    logger.info("pxmart input selector failed %s: %s", sel, e)

            # 如果 Enter 沒作用，改點搜尋文字
            try:
                page.get_by_text("搜尋").click(timeout=3000)
                logger.info("pxmart clicked search text button")
            except Exception:
                pass

            if not filled:
                logger.warning("pxmart search input not found")
                self._save_debug(page, "input_not_found")
                return []

            page.wait_for_timeout(10000)

            for _ in range(8):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(800)

            body_text = page.locator("body").inner_text(timeout=5000)
            logger.info("pxmart body preview=%s", re.sub(r'\s+', ' ', body_text)[:500])

            elements = page.locator("div, a, li")
            count = elements.count()
            logger.info("pxmart elements count=%s", count)

            results: list[ProductCandidate] = []
            seen = set()

            for i in range(min(count, 1200)):
                try:
                    el = elements.nth(i)
                    text = el.inner_text(timeout=800)
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
                        logger.info("pxmart skip no pack keyword: %s", text[:150])
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
                        logger.info("pxmart skip no valid price: %s", text[:150])
                        continue

                    price = min(valid_prices)
                    title = self._extract_title(text)

                    if not title:
                        continue

                    key = f"{title}-{price}"
                    if key in seen:
                        continue
                    seen.add(key)

                    href = self.SEARCH_URL
                    try:
                        link = el.locator("a[href]").first
                        if link.count() > 0:
                            href2 = link.get_attribute("href") or ""
                            if href2:
                                href = href2
                    except Exception:
                        pass

                    if href.startswith("/"):
                        href = "https://pxbox.es.pxmart.com.tw" + href

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
            png = debug_dir / f"pxmart_{ts}_{reason}.png"
            html = debug_dir / f"pxmart_{ts}_{reason}.html"
            page.screenshot(path=str(png), full_page=True)
            html.write_text(page.content(), encoding="utf-8")
            logger.info("pxmart debug saved: %s / %s", png, html)
        except Exception as e:
            logger.warning("pxmart debug save failed: %s", e)
