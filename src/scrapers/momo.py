"""
MOMO 購物網 爬蟲（JSON-LD 結構化資料解析版）
============================================
MOMO 在搜尋結果頁內嵌 <script type="application/ld+json"> 的 schema.org 商品資料，
直接 parse 這個 JSON 比抓 CSS class 穩定許多（MOMO 為了 Google SEO 不會輕易改）。

若找不到任何 Product，會把當下頁面截圖 + HTML 存到 data/debug/，
由 GitHub Actions 上傳為 artifact，方便排查。
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from src.filter import ProductCandidate
from src.scrapers.base import BaseScraper, new_context

logger = logging.getLogger(__name__)
DEBUG_DIR = Path("data/debug")

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)


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
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                logger.info("MOMO networkidle 超時，仍嘗試解析 JSON-LD")

            time.sleep(1)
            html = page.content()
            candidates = self._parse_jsonld(html)

            if not candidates:
                logger.warning("MOMO JSON-LD 內找不到 Product，存 debug 檔")
                self._save_debug(page, query)
            else:
                logger.info("MOMO 從 JSON-LD 解析出 %d 筆商品", len(candidates))
        finally:
            context.close()

        return candidates

    # ------------------------------------------------------------------
    def _parse_jsonld(self, html: str) -> list[ProductCandidate]:
        """掃所有 <script type="application/ld+json"> 找 Product"""
        candidates: list[ProductCandidate] = []
        for m in LD_JSON_RE.finditer(html):
            raw = m.group(1).strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.debug("JSON-LD 解析失敗：%s", e)
                continue
            blocks = data if isinstance(data, list) else [data]
            for b in blocks:
                self._collect_products(b, candidates)
        # 去重（同一 URL 可能出現多次）
        seen: set[str] = set()
        unique: list[ProductCandidate] = []
        for c in candidates:
            key = c.url or c.title
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        return unique

    def _collect_products(self, node, candidates: list[ProductCandidate]):
        """遞迴尋找 @type == Product 的節點"""
        if not isinstance(node, dict):
            return
        t = node.get("@type")
        if t == "Product":
            name = (node.get("name") or "").strip()
            url = (node.get("url") or "").strip()
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = None
            if isinstance(offers, dict):
                p = offers.get("price")
                try:
                    price = float(p) if p is not None else None
                except (TypeError, ValueError):
                    price = None
            if name and price:
                candidates.append(ProductCandidate(
                    title=name,
                    price=price,
                    list_price=price,
                    url=url,
                    promo_tags=[],
                ))

        # 遞迴探訪可能含 Product 的子節點
        for key in ("@graph", "itemListElement", "mainEntity", "hasPart"):
            sub = node.get(key)
            if isinstance(sub, list):
                for item in sub:
                    if isinstance(item, dict):
                        inner = item.get("item")
                        if inner:
                            self._collect_products(inner, candidates)
                        self._collect_products(item, candidates)
            elif isinstance(sub, dict):
                self._collect_products(sub, candidates)

    # ------------------------------------------------------------------
    def _save_debug(self, page, query: str):
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            safe_q = "".join(c if c.isalnum() else "_" for c in query)[:30]
            stem = f"momo_{ts}_{safe_q}_no_items"
            page.screenshot(path=str(DEBUG_DIR / f"{stem}.png"), full_page=True, timeout=10000)
            (DEBUG_DIR / f"{stem}.html").write_text(page.content(), encoding="utf-8")
            logger.info("MOMO debug 已存：%s", stem)
        except Exception as e:
            logger.error("存 MOMO debug 失敗：%s", e)
