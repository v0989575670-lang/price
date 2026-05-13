"""
爬蟲基底類別與共用工具
======================
所有通路爬蟲繼承 BaseScraper，實作 search()。
提供 JSON-LD 解析、debug 存檔等共用工具。
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from playwright.sync_api import Browser

from src.filter import ProductCandidate

logger = logging.getLogger(__name__)

DEBUG_DIR = Path("data/debug")

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)


class BaseScraper(ABC):
    """爬蟲基底類別。子類別實作 search()"""
    name: str = ""       # e.g. "momo"
    label: str = ""      # e.g. "MOMO"

    def __init__(self, browser: "Browser", search_url_template: str):
        self.browser = browser
        self.search_url_template = search_url_template

    def build_url(self, query: str) -> str:
        return self.search_url_template.format(query=quote_plus(query))

    @abstractmethod
    def search(self, query: str) -> list[ProductCandidate]:
        ...


# ------------------------------------------------------------------
# 共用解析工具
# ------------------------------------------------------------------

_PRICE_REGEX = re.compile(r"([\d,]+(?:\.\d+)?)")


def parse_price(text: str) -> float | None:
    if not text:
        return None
    text = text.replace("\xa0", " ")
    m = _PRICE_REGEX.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def new_context(browser: "Browser"):
    return browser.new_context(
        user_agent=DEFAULT_UA,
        viewport={"width": 1280, "height": 900},
        locale="zh-TW",
        timezone_id="Asia/Taipei",
    )


# ------------------------------------------------------------------
# JSON-LD 解析（schema.org Product）
# ------------------------------------------------------------------

def parse_jsonld_products(html: str) -> list[ProductCandidate]:
    """
    從頁面 HTML 抽出所有 <script type="application/ld+json"> 內的 schema.org Product。
    這比 CSS selector 穩定，因為各大電商都需要這個資料供 Google SEO。
    """
    candidates: list[ProductCandidate] = []
    seen: set[str] = set()

    def collect(node):
        if not isinstance(node, dict):
            return
        if node.get("@type") == "Product":
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
                key = url or name
                if key not in seen:
                    seen.add(key)
                    candidates.append(
                        ProductCandidate(
                            title=name,
                            price=price,
                            list_price=price,
                            url=url,
                            promo_tags=[],
                        )
                    )

        for k in ("@graph", "itemListElement", "mainEntity", "hasPart"):
            sub = node.get(k)
            if isinstance(sub, list):
                for it in sub:
                    if isinstance(it, dict):
                        inner = it.get("item")
                        if inner:
                            collect(inner)
                        collect(it)
            elif isinstance(sub, dict):
                collect(sub)

    for m in LD_JSON_RE.finditer(html):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blocks = data if isinstance(data, list) else [data]
        for b in blocks:
            collect(b)

    return candidates


# ------------------------------------------------------------------
# Debug 存檔工具
# ------------------------------------------------------------------

def save_debug(page, query: str, scraper_name: str, suffix: str = "no_items"):
    """把當下頁面截圖 + HTML 存到 data/debug/，供 GitHub Actions 上傳成 artifact"""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        safe_q = "".join(c if c.isalnum() else "_" for c in query)[:30]
        stem = f"{scraper_name}_{ts}_{safe_q}_{suffix}"
        page.screenshot(path=str(DEBUG_DIR / f"{stem}.png"), full_page=True, timeout=10000)
        (DEBUG_DIR / f"{stem}.html").write_text(page.content(), encoding="utf-8")
        logger.info("%s debug 已存：%s", scraper_name, stem)
    except Exception as e:
        logger.error("存 %s debug 失敗：%s", scraper_name, e)


def common_search_flow(browser, url: str, query: str, scraper_name: str,
                       fallback_parser=None, extra_wait_sec: float = 2.0) -> list[ProductCandidate]:
    """
    通用搜尋流程：
      1. 開新 context、新 page
      2. goto + 等 networkidle
      3. 從 HTML 抽 JSON-LD Product
      4. 沒抓到→呼叫 fallback_parser(page) 試 CSS selector
      5. 還是沒有→存 debug
    """
    logger.info("[%s] 搜尋：%s", scraper_name, url)
    candidates: list[ProductCandidate] = []
    context = new_context(browser)
    try:
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            logger.warning("[%s] goto 失敗：%s", scraper_name, e)
            save_debug(page, query, scraper_name, suffix="goto_fail")
            return []

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            logger.info("[%s] networkidle 超時，繼續嘗試解析", scraper_name)

        if extra_wait_sec > 0:
            time.sleep(extra_wait_sec)

        # 1. JSON-LD
        html = page.content()
        candidates = parse_jsonld_products(html)
        if candidates:
            logger.info("[%s] 從 JSON-LD 解析出 %d 筆", scraper_name, len(candidates))

        # 2. CSS Fallback
        if not candidates and fallback_parser:
            try:
                candidates = fallback_parser(page) or []
                if candidates:
                    logger.info("[%s] 從 CSS fallback 解析出 %d 筆", scraper_name, len(candidates))
            except Exception as e:
                logger.error("[%s] fallback parser 錯誤：%s", scraper_name, e)

        if not candidates:
            logger.warning("[%s] 完全找不到商品，存 debug 檔", scraper_name)
            save_debug(page, query, scraper_name)

    finally:
        context.close()

    return candidates
