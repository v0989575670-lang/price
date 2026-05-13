from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CoupangScraper(BaseScraper):
    name = "coupang"
    label = "酷澎"

    SEARCH_BASE = "https://tw.coupang.com/np/search?q="

    REQUIRED = ["光泉", "200"]

    MUST_ANY = ["成份無調整", "成分無調整", "全脂", "保久"]

    EXCLUDE = [
        "蘋果", "巧克力", "堅果", "珍穀", "麥芽", "燕麥",
        "豆漿", "飲品", "調味", "高鈣", "低脂"
    ]

PACK_KEYWORDS = [
    "24入",
    "24 入",
    "24瓶",
    "24罐",
    "24",

    # 酷澎常見寫法
    "6入x4",
    "6入 x4",
    "6入×4",
    "6入*4",

    "200mlx6入",
    "200ml x6入",

    "x4組",
    "4組",
]

    def search(self, query: str) -> list[ProductCandidate]:
        search_query = "光泉 無調整保久乳"
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
            logger.info("coupang url=%s", url)

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)

            for _ in range(8):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(1000)

            body_text = page.locator("body").inner_text(timeout=5000)
            logger.info("coupang body preview=%s", re.sub(r"\s+", " ", body_text)[:800])

            elements = page.locator("li, div, a")
            count = elements.count()
            logger.info("coupang elements count=%s", count)

            results: list[ProductCandidate] = []
            seen = set()

            for i in range(min(count, 1800)):
                try:
                    el = elements.nth(i)
                    text = el.inner_text(timeout=800)
                    text = re.sub(r"\s+", " ", text or "").strip()

                    if not text:
                        continue

                    if "光泉" not in text:
                        continue
                        if "200" not in text:
    continue

                    logger.info("coupang card text=%s", text[:220])

                    if not all(k in text for k in self.REQUIRED):
                        continue

                    if not any(k in text for k in self.MUST_ANY):
                        continue

                    if any(k in text for k in self.EXCLUDE):
                        continue

                    if not any(k in text for k in self.PACK_KEYWORDS):
                logger.warning(
    "coupang skip no pack keyword: %s",
    text[:300]
)
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
                        logger.info("coupang skip no valid price: %s", text[:160])
                        continue

                    # 酷澎常有首購折扣價，例如 $467-$280
                    # 不採信首購低價，所以取最高價
                    price = max(valid_prices)

                    promo_tags = []
                    if len(valid_prices) >= 2:
                        normal_price = max(valid_prices)
                        promo_price = min(valid_prices)
                        if promo_price < normal_price:
                            promo_tags.append(f"首購/折扣價${promo_price}不採信")

                    title = self._extract_title(text)

                    key = f"{title}-{price}"
                    if key in seen:
                        continue
                    seen.add(key)

                    href = url
                    try:
                        link = el.locator("a[href]").first
                        if link.count() > 0:
                            href2 = link.get_attribute("href") or ""
                            if href2:
                                href = href2
                    except Exception:
                        pass

                    if href.startswith("/"):
                        href = "https://tw.coupang.com" + href

                    results.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=href,
                            promo_tags=promo_tags,
                            raw={"text": text},
                        )
                    )

                    logger.info("coupang matched title=%s price=%s", title, price)

                except Exception:
                    continue

            logger.info("coupang final results=%s", len(results))

            if not results:
                self._save_debug(page, "no_results")

            return results

        except Exception as e:
            logger.exception("coupang scraper failed: %s", e)
            try:
                self._save_debug(page, "exception")
            except Exception:
                pass
            return []

        finally:
            page.close()

    def _extract_title(self, text: str) -> str:
        parts = re.split(r"\$|首購|折扣|火箭速配|明天|評分|免運|優惠券", text)
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if "光泉" in p and "200" in p:
                return p[:120]
        return text[:120]

    def _save_debug(self, page, reason: str) -> None:
        try:
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            ts = int(time.time())
            page.screenshot(path=str(debug_dir / f"coupang_{ts}_{reason}.png"), full_page=True)
            (debug_dir / f"coupang_{ts}_{reason}.html").write_text(page.content(), encoding="utf-8")
            logger.info("coupang debug saved reason=%s", reason)
        except Exception as e:
            logger.warning("coupang debug save failed: %s", e)
