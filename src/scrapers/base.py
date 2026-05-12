"""
爬蟲基底類別與共用工具
======================
所有通路爬蟲繼承 BaseScraper，實作 search()。
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from playwright.sync_api import Browser

from src.filter import ProductCandidate

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """爬蟲基底類別。

    子類別必須實作 search()，吃 query 字串、回傳候選 ProductCandidate 列表。
    """
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
    """從字串裡抽出第一個數字當價格。e.g. 'NT$ 1,290 元' -> 1290.0"""
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
    """建立一個有合理 UA 與 viewport 的 context"""
    return browser.new_context(
        user_agent=DEFAULT_UA,
        viewport={"width": 1280, "height": 900},
        locale="zh-TW",
        timezone_id="Asia/Taipei",
    )
