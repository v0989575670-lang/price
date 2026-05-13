from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, save_debug

logger = logging.getLogger(__name__)


class CoupangScraper(BaseScraper):
    name = "coupang"
    label = "酷澎"

    SEARCH_BASE = "https://tw.coupang.com/np/search?q="

    REQUIRED = ["光泉"]

    MUST_ANY = [
        "成份無調整",
        "成分無調整",
        "全脂",
        "保久",
    ]

    EXCLUDE = [
        "蘋果",
        "巧克力",
        "堅果",
        "珍穀",
        "麥芽",
        "燕麥",
        "豆漿",
        "調味",
        "高鈣",
        "低脂",
    ]

    PACK_KEYWORDS = [
        "24入", "24 入", "24瓶", "24罐", "24盒",
        "24件", "x24", "X24", "×24", "*24",
        "6入x4", "6入 x4", "6入×4", "6入*4", "6入X4",
        "6盒x4", "6罐x4",
        "200mlx6入", "200ml x6入", "200mlx24",
        "x4組", "×4組", "4組", "一箱", "整箱",
        "箱購", "箱裝",
    ]

    CARD_SELECTORS = [
        "[class*='ProductCard']",
        "[class*='product-card']",
        "[class*='SearchProduct']",
        "[class*='search-product']",
        "[class*='ItemCard']",
        "li[class*='search']",
        "div[data-item-id]",
        "div[data-product-id]",
        "li[data-product-id]",
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        search_query = "光泉 無調整保久乳 24入"
        url = self.SEARCH_BASE + quote(search_query)

        # ★ 酷澎專用 context：不設 locale，避免被重導向到 www.tw.coupang.com
        context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            # 不設 locale / timezone_id，讓酷澎用預設判斷地區
        )
        page = context.new_page()

        try:
            logger.info("coupang url=%s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            # 確認有沒有被重導向
            current_url = page.url
            logger.info("coupang current_url=%s", current_url)
            if "Access Denied" in page.title() or "access" in current_url.lower() and "denied" in page.content().lower():
                logger.error("coupang Access Denied，存 debug")
                save_debug(page, search_query, "coupang", "access_denied")
                return []

            for _ in range(6):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(800)

            results = self._try_extract_from_js(page, url)
            if results:
                logger.info("coupang js-state extracted count=%s", len(results))
                save_debug(page, search_query, "coupang", f"results_{len(results)}")
                return results

            results = self._try_card_selectors(page, url)
            if results:
                logger.info("coupang card-selector extracted count=%s", len(results))
                save_debug(page, search_query, "coupang", f"results_{len(results)}")
                return results

            results = self._try_broad_locator(page, url)
            logger.info("coupang broad-locator extracted count=%s", len(results))

            save_debug(page, search_query, "coupang", f"results_{len(results)}")

            return results

        except Exception as e:
            logger.exception("coupang scraper failed: %s", e)
            try:
                save_debug(page, search_query, "coupang", "exception")
            except Exception:
                pass
            return []

        finally:
            context.close()

    def _try_extract_from_js(self, page, base_url: str) -> list[ProductCandidate]:
        results: list[ProductCandidate] = []

        try:
            raw = page.evaluate(
                "() => {"
                "  const s = window.__INITIAL_STATE__ || window.__PRELOADED_STATE__;"
                "  return s ? JSON.stringify(s) : null;"
                "}"
            )
            if raw:
                state = json.loads(raw)
                items = self._walk_for_products(state)
                logger.info("coupang __INITIAL_STATE__ candidates=%s", len(items))
                for item in items:
                    c = self._candidate_from_dict(item, base_url)
                    if c:
                        results.append(c)
                if results:
                    return results
        except Exception as e:
            logger.debug("coupang js-state failed: %s", e)

        try:
            scripts = page.locator("script[type='application/ld+json']")
            for i in range(scripts.count()):
                try:
                    text = scripts.nth(i).inner_text(timeout=1000)
                    data = json.loads(text)
                    items_ld = data if isinstance(data, list) else [data]
                    for item in items_ld:
                        if item.get("@type") in ("Product", "ItemList"):
                            c = self._candidate_from_jsonld(item, base_url)
                            if c:
                                results.append(c)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("coupang json-ld failed: %s", e)

        return results

    def _walk_for_products(self, obj, depth=0):
        if depth > 8:
            return []
        results = []
        if isinstance(obj, dict):
            name_key = next(
                (k for k in obj if k in (
                    "productName", "itemName", "name", "title",
                    "productTitle", "displayName",
                )),
                None,
            )
            price_key = next(
                (k for k in obj if k in (
                    "salePrice", "price", "offerPrice",
                    "basePrice", "originalPrice",
                )),
                None,
            )
            if name_key and price_key:
                results.append(obj)
            else:
                for v in obj.values():
                    results.extend(self._walk_for_products(v, depth + 1))
        elif isinstance(obj, list):
            for v in obj:
                results.extend(self._walk_for_products(v, depth + 1))
        return results

    def _candidate_from_dict(self, d: dict, base_url: str):
        name_key = next(
            (k for k in d if k in (
                "productName", "itemName", "name", "title", "productTitle",
            )),
            None,
        )
        price_key = next(
            (k for k in d if k in (
                "salePrice", "price", "offerPrice", "basePrice",
            )),
            None,
        )
        if not name_key or not price_key:
            return None

        title = str(d[name_key])
        try:
            price = int(float(str(d[price_key]).replace(",", "")))
        except Exception:
            return None

        if not self._passes_filter(title):
            return None

        url = d.get("productUrl") or d.get("url") or base_url
        if isinstance(url, str) and url.startswith("/"):
            url = "https://tw.coupang.com" + url

        return ProductCandidate(
            title=title[:120],
            price=price,
            list_price=price,
            url=url,
            promo_tags=[],
            raw={"source": "js_state"},
        )

    def _candidate_from_jsonld(self, d: dict, base_url: str):
        title = d.get("name", "")
        try:
            offers = d.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0]
            price = int(float(str(offers.get("price", 0))))
        except Exception:
            return None
        if not price or not self._passes_filter(title):
            return None
        return ProductCandidate(
            title=title[:120],
            price=price,
            list_price=price,
            url=d.get("url") or base_url,
            promo_tags=[],
            raw={"source": "json_ld"},
        )

    def _try_card_selectors(self, page, base_url: str) -> list[ProductCandidate]:
        for selector in self.CARD_SELECTORS:
            try:
                els = page.locator(selector)
                count = els.count()
                if count == 0:
                    continue

                logger.info("coupang selector=%s count=%s", selector, count)
                results: list[ProductCandidate] = []
                seen: set[str] = set()

                for i in range(min(count, 200)):
                    try:
                        el = els.nth(i)
                        text = re.sub(
                            r"\s+", " ", el.inner_text(timeout=1000) or ""
                        ).strip()
                        if not text:
                            continue
                        c = self._parse_card_text(text, el, base_url, seen)
                        if c:
                            results.append(c)
                    except Exception:
                        continue

                if results:
                    return results

            except Exception as e:
                logger.debug("coupang selector %s failed: %s", selector, e)

        return []

    def _try_broad_locator(self, page, base_url: str) -> list[ProductCandidate]:
        elements = page.locator("li, div, a")
        count = elements.count()
        logger.info("coupang broad locator count=%s", count)

        results: list[ProductCandidate] = []
        seen: set[str] = set()

        for i in range(min(count, 2000)):
            try:
                el = elements.nth(i)
                text = re.sub(
                    r"\s+", " ", el.inner_text(timeout=800) or ""
                ).strip()
                if not text or len(text) < 10:
                    continue
                c = self._parse_card_text(text, el, base_url, seen)
                if c:
                    results.append(c)
            except Exception:
                continue

        return results

    def _parse_card_text(self, text: str, el, base_url: str, seen: set):
        if not self._passes_filter(text):
            return None

        prices = self._extract_prices(text)
        if not prices:
            logger.info("coupang skip no valid price: %s", text[:160])
            return None

        price = max(prices)
        promo_tags = []
        if len(prices) >= 2:
            promo_price = min(prices)
            if promo_price < price:
                promo_tags.append(f"首購/折扣價${promo_price}不採信")

        title = self._extract_title(text)
        key = f"{title}-{price}"
        if key in seen:
            return None
        seen.add(key)

        href = base_url
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

        return ProductCandidate(
            title=title,
            price=price,
            list_price=price,
            url=href,
            promo_tags=promo_tags,
            raw={"text": text},
        )

    def _passes_filter(self, text: str) -> bool:
        if not all(k in text for k in self.REQUIRED):
            return False
        if not any(k in text for k in self.MUST_ANY):
            return False
        if any(k in text for k in self.EXCLUDE):
            return False

        if any(k in text for k in self.PACK_KEYWORDS):
            return True

        m = re.search(r"(\d+)\s*[入盒瓶罐件]", text)
        if m and int(m.group(1)) >= 12:
            return True

        logger.warning("coupang skip no pack keyword: %s", text[:300])
        return False

    def _extract_prices(self, text: str) -> list[int]:
        prices = []
        for p in re.findall(r"(?:NT)?\$\s*([0-9,]+)", text):
            try:
                v = int(p.replace(",", ""))
                if v >= 200:
                    prices.append(v)
            except Exception:
                pass
        for p in re.findall(r"([0-9,]+)\s*元", text):
            try:
                v = int(p.replace(",", ""))
                if v >= 200:
                    prices.append(v)
            except Exception:
                pass
        return list(set(prices))

    def _extract_title(self, text: str) -> str:
        parts = re.split(
            r"\$|首購|折扣|火箭速配|明天|評分|免運|優惠券|NT\$|加入購物車",
            text,
        )
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if "光泉" in p and len(p) > 5:
                return p[:120]
        return text[:120]
