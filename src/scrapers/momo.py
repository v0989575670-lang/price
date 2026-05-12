"""
MOMO 購物網 爬蟲
=================
使用 Playwright 瀏覽搜尋結果頁，解析商品名稱與價格。

備註：MOMO 頁面 HTML 結構偶有變動，若 selector 失效會回傳空清單。
"""

from __future__ import annotations

import logging

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, clean_text, new_context, parse_price

logger = logging.getLogger(__name__)


class MomoScraper(BaseScraper):
    name = "momo"
    label = "MOMO"

    def search(self, query: str) -> list[ProductCandidate]:
        url = self.build_url(query)
        logger.info("MOMO 搜尋：%s", url)

        candidates: list[ProductCandidate] = []
        context = new_context(self.browser)
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等候商品卡片渲染
            try:
                page.wait_for_selector("li.goodsItemLi, ul.prdListArea li, [data-prdurl]", timeout=15000)
            except Exception:
                logger.warning("MOMO 等候商品列表超時，可能無結果或結構變動")
                return []

            # 嘗試多種 selector，相容新舊版面
            items = page.query_selector_all("li.goodsItemLi")
            if not items:
                items = page.query_selector_all("ul.prdListArea > li")
            if not items:
                items = page.query_selector_all("[data-prdurl]")

            logger.info("MOMO 找到 %d 個商品卡片", len(items))

            for it in items[:30]:  # 只看前 30 筆
                try:
                    # 商品名稱
                    title_el = (
                        it.query_selector(".prdName")
                        or it.query_selector(".goodsName")
                        or it.query_selector("h3.prdName")
                        or it.query_selector("p.prdName")
                    )
                    title = clean_text(title_el.inner_text()) if title_el else ""

                    # 價格
                    price_el = (
                        it.query_selector(".price b")
                        or it.query_selector(".priceTxt b")
                        or it.query_selector(".money")
                        or it.query_selector(".price")
                    )
                    price_text = clean_text(price_el.inner_text()) if price_el else ""
                    price = parse_price(price_text)

                    # 商品連結
                    link_el = it.query_selector("a")
                    href = link_el.get_attribute("href") if link_el else None
                    if href and href.startswith("/"):
                        href = "https://www.momoshop.com.tw" + href
                    elif href and href.startswith("//"):
                        href = "https:" + href

                    # 促銷標籤
                    promo_tags: list[str] = []
                    for tag_el in it.query_selector_all(".sloganTitle, .iconArea, .promotion, .promoTag"):
                        t = clean_text(tag_el.inner_text())
                        if t:
                            promo_tags.append(t)

                    if not title and not price:
                        continue

                    candidates.append(
                        ProductCandidate(
                            title=title,
                            price=price,
                            list_price=price,  # MOMO 卡片通常只顯示活動價
                            url=href or "",
                            promo_tags=promo_tags,
                        )
                    )
                except Exception as e:
                    logger.debug("解析 MOMO 商品時錯誤：%s", e)
                    continue

        finally:
            context.close()

        return candidates
