"""
家樂福線上購物爬蟲
====================
search URL:
https://online.carrefour.com.tw/zh/search/?q=...

本版重點：
1. 不再依賴單一 CSS selector
2. 直接從頁面中所有商品連結與商品區塊掃描
3. 可抓取家樂福搜尋頁已渲染出的商品名稱、價格、連結
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote_plus

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, clean_text, parse_price

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):
    name = "carrefour"
    label = "家樂福"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        logger.info("carrefour search url: %s", url)

        page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        candidates: list[ProductCandidate] = []

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            # 捲動幾次，讓商品 lazy load 出來
            for _ in range(4):
                page.mouse.wheel(0, 1200)
                time.sleep(1)

            # 先從所有商品連結找
            candidates.extend(self._parse_product_links(page))

            # 若還是沒有，再用卡片區塊備援
            if not candidates:
                candidates.extend(self._parse_product_cards(page))

            # 去重
            dedup: dict[str, ProductCandidate] = {}
            for c in candidates:
                key = c.url or c.title
                if key and key not in dedup:
                    dedup[key] = c

            results = list(dedup.values())
            logger.info("carrefour parsed %d candidates", len(results))
            return results

        except Exception as e:
            logger.exception("carrefour search failed: %s", e)
            return []

        finally:
            page.close()

    def _parse_product_links(self, page) -> list[ProductCandidate]:
        """
        從所有商品頁連結中反推商品名稱、價格。
        家樂福商品頁連結通常含 /zh/品牌/商品代碼.html
        """
        candidates: list[ProductCandidate] = []

        links = page.query_selector_all("a[href*='.html']")
        logger.info("carrefour found %d html links", len(links))

        for a in links[:120]:
            try:
                href = a.get_attribute("href") or ""
                if not href:
                    continue

                if href.startswith("/"):
                    href = "https://online.carrefour.com.tw" + href

                if "online.carrefour.com.tw" not in href and not href.startswith("https://online.carrefour.com.tw"):
                    continue

                text = clean_text(a.inner_text() or "")
                title = text

                # 商品名稱有時不在 a 文字，而在 title / aria-label
                if not title:
                    title = clean_text(a.get_attribute("title") or a.get_attribute("aria-label") or "")

                # 往上找商品卡片容器
                card_text = ""
                try:
                    handle = a.evaluate_handle(
                        """el => el.closest('li, article, .product, .product-item, .product-card, .product-tile, div')"""
                    )
                    if handle:
                        card_text = clean_text(handle.as_element().inner_text())
                except Exception:
                    card_text = ""

                if not title and card_text:
                    title = self._guess_title_from_text(card_text)

                if not title:
                    continue

                price = self._extract_price(card_text or text)

                if price is None:
                    # 從連結附近再往外層找一次
                    try:
                        outer_text = a.evaluate(
                            """el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 5 && p; i++) {
                                    const t = p.innerText || '';
                                    if (t.includes('$') || t.includes('NT')) return t;
                                    p = p.parentElement;
                                }
                                return '';
                            }"""
                        )
                        price = self._extract_price(clean_text(outer_text or ""))
                    except Exception:
                        price = None

                if price is None:
                    continue

                candidates.append(
                    ProductCandidate(
                        title=title,
                        price=price,
                        list_price=price,
                        url=href,
                        promo_tags=[],
                    )
                )

            except Exception as e:
                logger.debug("carrefour parse link error: %s", e)
                continue

        return candidates

    def _parse_product_cards(self, page) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []

        selectors = [
            ".product-tile",
            ".product-card",
            ".product-item",
            ".product",
            "[class*='product']",
            "[class*='Product']",
            "li",
            "article",
        ]

        items = []
        for sel in selectors:
            try:
                items = page.query_selector_all(sel)
                if items:
                    logger.info("carrefour selector %s found %d items", sel, len(items))
                    break
            except Exception:
                continue

        for it in items[:120]:
            try:
                full_text = clean_text(it.inner_text() or "")
                if not full_text:
                    continue

                price = self._extract_price(full_text)
                if price is None:
                    continue

                title = self._guess_title_from_text(full_text)
                if not title:
                    continue

                href = ""
                link_el = it.query_selector("a[href]")
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://online.carrefour.com.tw" + href

                candidates.append(
                    ProductCandidate(
                        title=title,
                        price=price,
                        list_price=price,
                        url=href,
                        promo_tags=[],
                    )
                )

            except Exception as e:
                logger.debug("carrefour parse card error: %s", e)
                continue

        return candidates

    def _extract_price(self, text: str) -> float | None:
        """
        從文字中抓價格。
        優先抓紅字/活動價常見格式，如 $258。
        """
        if not text:
            return None

        # 例如 $258、$ 420、NT$420
        matches = re.findall(r"(?:NT\$|\$)\s*([0-9,]+)", text)
        prices = []
        for m in matches:
            try:
                prices.append(float(m.replace(",", "")))
            except Exception:
                pass

        if prices:
            # 通常同一卡片會有原價與促銷價，取最低價當顯示價
            return min(prices)

        # 備援
        return parse_price(text)

    def _guess_title_from_text(self, text: str) -> str:
        """
        從商品卡片文字猜商品名稱。
        """
        if not text:
            return ""

        lines = [clean_text(x) for x in text.splitlines()]
        lines = [x for x in lines if x]

        bad_words = [
            "加入購物車",
            "已加入",
            "查看",
            "登入",
            "促銷",
            "折扣",
            "贈",
            "宅配",
            "到店取貨",
            "熱銷",
        ]

        for line in lines:
            if "$" in line or "NT" in line:
                continue
            if any(b in line for b in bad_words):
                continue
            if len(line) < 4:
                continue
            if "光泉" in line or "保久" in line or "牛乳" in line:
                return line

        # 沒命中關鍵字時，取第一個較像商品名的長句
        for line in lines:
            if "$" in line or "NT" in line:
                continue
            if any(b in line for b in bad_words):
                continue
            if len(line) >= 6:
                return line

        return ""
