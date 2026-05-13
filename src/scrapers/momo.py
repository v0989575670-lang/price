"""
MOMO 購物網 爬蟲（含偵錯模式）
==============================
若所有 selector 都找不到結果，會把當下的頁面截圖 + HTML 存到 data/debug/
GitHub Actions 會把這個資料夾上傳為 artifact，可下載查看。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, clean_text, new_context, parse_price

logger = logging.getLogger(__name__)

DEBUG_DIR = Path("data/debug")


class MomoScraper(BaseScraper):
    name = "momo"
    label = "MOMO"

    POSSIBLE_ITEM_SELECTORS = [
        "li.goodsItemLi",
        "ul.prdListArea > li",
        "[data-prdurl]",
        ".swiper-slide.goodsItemLi",
        ".prdListItem",
        "article.product",
    ]

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        logger.info("MOMO 搜尋：%s", url)

        candidates: list[ProductCandidate] = []
        context = new_context(self.browser)
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # 多等一下讓 JS 渲染完
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                logger.info("MOMO networkidle 超時，仍嘗試解析")

            # 額外緩衝 2 秒
            time.sleep(2)

            # 嘗試多個 selector
            items = []
            used_selector = None
            for sel in self.POSSIBLE_ITEM_SELECTORS:
                els = page.query_selector_all(sel)
                if els:
                    items = els
                    used_selector = sel
                    break

            if not items:
                logger.warning("MOMO 所有 selector 都沒找到商品，存 debug 檔")
                self._save_debug(page, query)
                return []

            logger.info("MOMO 用 selector '%s' 抓到 %d 個元素", used_selector, len(items))

            for it in items[:30]:
                try:
                    # 商品名稱：嘗試多種 selector
                    title = ""
                    for ts in [".prdName", ".goodsName", "h3.prdName", "p.prdName", "h3", ".title", ".name"]:
                        el = it.query_selector(ts)
                        if el:
                            title = clean_text(el.inner_text())
                            if title:
                                break

                    # 價格
                    price_text = ""
                    for ps in [".price b", ".priceTxt b", ".money", ".price", "[class*='price']"]:
                        el = it.query_selector(ps)
                        if el:
                            price_text = clean_text(el.inner_text())
                            if price_text:
                                break
                    price = parse_price(price_text)

                    # 連結
                    link_el = it.query_selector("a")
                    href = link_el.get_attribute("href") if link_el else None
                    if href and href.startswith("/"):
                        href = "https://www.momoshop.com.tw" + href
                    elif href and href.startswith("//"):
                        href = "https:" + href

                    # 促銷標籤
                    promo_tags: list[str] = []
                    for tag_el in it.query_selector_all(".sloganTitle, .iconArea, .promotion, .promoTag, .tag"):
                        t = clean_text(tag_el.inner_text())
                        if t:
                            promo_tags.append(t)

                    if not title and not price:
                        continue

                    candidates.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,
                            url=href or "",
                            promo_tags=promo_tags,
                        )
                    )
                except Exception as e:
                    logger.debug("解析 MOMO 商品時錯誤：%s", e)
                    continue

            logger.info("MOMO 共解析出 %d 筆候選", len(candidates))

            # 若有 selector 命中、但解析後 0 筆，也存 debug
            if not candidates:
                logger.warning("MOMO selector 有命中但解析不到價格，存 debug 檔")
                self._save_debug(page, query, suffix="parsed_empty")

        except Exception as e:
            logger.error("MOMO 爬蟲例外：%s", e)
            try:
                page = context.pages[0] if context.pages else None
                if page:
                    self._save_debug(page, query, suffix="exception")
            except Exception:
                pass
            raise
        finally:
            context.close()

        return candidates

    def _save_debug(self, page, query: str, suffix: str = "no_items"):
        """把當下頁面截圖與 HTML 存到 data/debug/"""
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            safe_q = "".join(c if c.isalnum() else "_" for c in query)[:30]
            stem = f"momo_{ts}_{safe_q}_{suffix}"
            screenshot = DEBUG_DIR / f"{stem}.png"
            html_file = DEBUG_DIR / f"{stem}.html"
            page.screenshot(path=str(screenshot), full_page=True, timeout=10000)
            html_file.write_text(page.content(), encoding="utf-8")
            logger.info("MOMO debug 已存：%s, %s", screenshot, html_file)
        except Exception as e:
            logger.error("存 MOMO debug 失敗：%s", e)
