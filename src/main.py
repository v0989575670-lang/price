"""
主程式
======
讀設定 → 啟動 Playwright → 各通路爬蟲搜尋 → 過濾 → 偵測首購/異常 →
存歷史 → 寄信。
"""

from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

from src import filter as filt
from src import mailer, storage
from src.scrapers.base import BaseScraper
from src.scrapers.carrefour import CarrefourScraper
from src.scrapers.coupang import CoupangScraper
from src.scrapers.momo import MomoScraper
from src.scrapers.pxmart import PxmartScraper
from src.scrapers.shopee import ShopeeScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "momo": MomoScraper,
    "shopee": ShopeeScraper,
    "pxmart": PxmartScraper,
    "carrefour": CarrefourScraper,
    "coupang": CoupangScraper,
}

CONFIG_PATH = Path("config/products.yaml")


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_query(product: dict) -> str:
    """組合搜尋字串：把 search_keywords 用空白串起來"""
    kws = product.get("search_keywords") or [product.get("name", "")]
    return " ".join(kws)


def process_one_product(product: dict, config: dict, browser) -> list[dict]:
    """
    對一個商品，跑過所有通路，回傳 email 用的 rows + 同時寫歷史 CSV。
    """
    product_name = product["name"]
    product_short = product.get("short_name", product_name)
    query = build_query(product)
    first_purchase_kws = config.get("first_purchase_keywords", [])
    abnormal_ratio = float(config.get("abnormal_price_ratio", 0.7))

    rows: list[dict] = []
    history_records: list[dict] = []

    for ch in config.get("channels", []):
        if not ch.get("enabled", True):
            continue

        ch_name = ch["name"]
        ch_label = ch.get("label", ch_name)
        scraper_cls = SCRAPER_REGISTRY.get(ch_name)
        if not scraper_cls:
            logger.warning("找不到 %s 的爬蟲類別，跳過", ch_name)
            continue

        row = {
            "channel": ch_name,
            "channel_label": ch_label,
            "matched_title": "",
            "list_price": None,
            "display_price": None,
            "is_first_purchase": False,
            "is_abnormal": False,
            "url": "",
            "note": "",
            "last_price": storage.get_last_price(product_name, ch_name),
        }

        try:
            scraper = scraper_cls(browser, ch["search_url"])

            if getattr(scraper_cls, "is_stub", False):
                row["note"] = "尚未實作（第二階段補上）"
                logger.info("[%s] 跳過：stub", ch_label)
            else:
                logger.info("[%s] 開始搜尋：%s", ch_label, query)
                candidates = scraper.search(query)
                logger.info("[%s] 回傳 %d 筆候選", ch_label, len(candidates))

                best=filt.pick_best_match(candidates,product,ch_name)
                if best is None:
    logger.info("[%s] pick_best_match 回傳 None，candidates=%d 筆", ch_label, len(candidates))  # ← 加這行
    row["note"] = "未找到符合規格的商品"
                    
                    row["note"] = "未找到符合規格的商品"
                else:
                    row["matched_title"] = best.title
                    row["list_price"] = best.list_price
                    row["display_price"] = best.price
                    row["url"] = best.url

                    # 首購偵測
                    is_fp = filt.detect_first_purchase(best, first_purchase_kws)
                    row["is_first_purchase"] = is_fp

                    # 異常價（排除首購樣本的歷史比較）
                    if best.price is not None:
                        history = storage.load_history(
                            product_name, ch_name, exclude_first_purchase=True
                        )
                        row["is_abnormal"] = filt.is_abnormal_price(
                            best.price, history, ratio=abnormal_ratio
                        )

        except Exception as e:
            logger.error("[%s] 爬蟲錯誤：%s", ch_label, e)
            logger.error(traceback.format_exc())
            row["note"] = f"爬蟲錯誤：{type(e).__name__}"

        rows.append(row)

    # 一次寫入
    storage.append_records(history_records)

    return rows


def main() -> int:
    run_time = datetime.now()
    logger.info("=== Price Monitor 啟動 @ %s ===", run_time.isoformat())

    try:
        config = load_config()
    except Exception as e:
        logger.error("讀取設定檔失敗：%s", e)
        return 1

    products = config.get("products", [])
    recipients = config.get("recipients", [])
    if not products:
        logger.error("沒有任何 products 設定")
        return 1
    if not recipients:
        logger.error("沒有任何 recipients 設定")
        return 1

    # 啟動 Playwright（headless）
    all_results: list[tuple[dict, list[dict]]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for product in products:
                rows = process_one_product(product, config, browser)
                all_results.append((product, rows))
        finally:
            browser.close()

    # 寄信（每個商品一封）
    overall_ok = True
    for product, rows in all_results:
        short = product.get("short_name", product["name"])
        try:
            subject = mailer.send_report(recipients, rows, short, run_time)
            logger.info("✉️  已寄出：%s", subject)
        except Exception as e:
            logger.error("寄信失敗：%s", e)
            logger.error(traceback.format_exc())
            overall_ok = False

    logger.info("=== Price Monitor 結束 ===")
    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
