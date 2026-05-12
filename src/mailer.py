"""
Email 寄送模組（使用 Gmail SMTP）
================================
組裝 HTML 表格並透過 Gmail SMTP（587 + STARTTLS）寄出。
帳號密碼從環境變數 GMAIL_USER / GMAIL_APP_PASSWORD 讀取。
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def fmt_price(p) -> str:
    if p is None or p == "":
        return "-"
    try:
        return f"${float(p):,.0f}"
    except (TypeError, ValueError):
        return str(p)


def render_html(
    rows: list[dict],
    product_short: str,
    run_time: datetime,
) -> str:
    """
    rows 每筆：
      channel, channel_label, matched_title, list_price, display_price,
      is_first_purchase, is_abnormal, url, note, last_price
    """
    style = """
    <style>
      body { font-family: -apple-system, "Segoe UI", "Microsoft JhengHei", sans-serif; color:#222; }
      .summary { padding:12px 16px; background:#f4f7fb; border-left:4px solid #2c6cf6;
                 margin-bottom:16px; font-size:14px; }
      table { border-collapse:collapse; width:100%; font-size:13px; }
      th, td { border:1px solid #ddd; padding:8px 10px; vertical-align:top; }
      th { background:#f0f3f7; text-align:left; }
      tr:nth-child(even) td { background:#fafafa; }
      .first-purchase { color:#c0392b; font-weight:bold; }
      .abnormal { background:#fff3cd !important; }
      .not-found td { color:#888; font-style:italic; }
      .price { text-align:right; font-variant-numeric:tabular-nums; }
      .delta-up { color:#c0392b; }
      .delta-down { color:#27ae60; }
      a { color:#2c6cf6; text-decoration:none; }
      .footer { color:#888; font-size:11px; margin-top:20px; }
    </style>
    """

    # 摘要：最低價是誰
    valid_rows = [r for r in rows if r.get("display_price") not in (None, "", 0)]
    if valid_rows:
        min_row = min(valid_rows, key=lambda r: float(r["display_price"]))
        summary = (
            f"今日最低價：<b>{min_row['channel_label']} {fmt_price(min_row['display_price'])}</b>"
            f"（{min_row['matched_title'][:40]}）"
        )
    else:
        summary = "今日沒有抓到任何有效價格，請檢查 GitHub Actions log。"

    header_html = f"""
    <p>價格監控報告 - {product_short}</p>
    <div class="summary">⏰ 抓取時間：{run_time.strftime("%Y-%m-%d %H:%M")}（台北）<br>📊 {summary}</div>
    """

    table_rows = []
    table_rows.append(
        "<tr>"
        "<th>通路</th><th>抓到的商品名稱</th>"
        "<th class='price'>標價</th><th class='price'>顯示價</th>"
        "<th class='price'>較上次</th>"
        "<th>狀態</th><th>連結</th>"
        "</tr>"
    )

    for r in rows:
        title = r.get("matched_title") or ""
        list_price = r.get("list_price")
        display_price = r.get("display_price")
        url = r.get("url") or ""
        is_fp = r.get("is_first_purchase")
        is_abnormal = r.get("is_abnormal")
        note = r.get("note") or ""
        last_price = r.get("last_price")

        # 狀態文字
        status_parts = []
        if is_fp:
            status_parts.append('<span class="first-purchase">首購/新客優惠</span>')
        if is_abnormal:
            status_parts.append('<span class="first-purchase">異常低價</span>')
        if note:
            status_parts.append(f"<span style='color:#666'>{note}</span>")
        status = "<br>".join(status_parts) if status_parts else "<span style='color:#27ae60'>正常</span>"

        # 較上次
        delta_html = "-"
        if display_price not in (None, "", 0) and last_price not in (None, "", 0):
            try:
                diff = float(display_price) - float(last_price)
                if diff > 0:
                    delta_html = f"<span class='delta-up'>▲ +${abs(diff):,.0f}</span>"
                elif diff < 0:
                    delta_html = f"<span class='delta-down'>▼ -${abs(diff):,.0f}</span>"
                else:
                    delta_html = "持平"
            except (TypeError, ValueError):
                delta_html = "-"

        # row class
        tr_class = ""
        if is_abnormal:
            tr_class = "abnormal"
        if not title and display_price in (None, "", 0):
            tr_class = "not-found"

        title_html = title if title else "<i>未找到</i>"
        url_html = f"<a href='{url}' target='_blank'>查看</a>" if url else "-"

        table_rows.append(
            f"<tr class='{tr_class}'>"
            f"<td><b>{r.get('channel_label')}</b></td>"
            f"<td>{title_html}</td>"
            f"<td class='price'>{fmt_price(list_price)}</td>"
            f"<td class='price'>{fmt_price(display_price)}</td>"
            f"<td class='price'>{delta_html}</td>"
            f"<td>{status}</td>"
            f"<td>{url_html}</td>"
            f"</tr>"
        )

    table_html = "<table>" + "".join(table_rows) + "</table>"

    footer = """
    <p class="footer">
      此信由 GitHub Actions 自動寄送 ・ 黃色背景 = 異常低價需確認 ・ 紅字 = 首購優惠不採信<br>
      若連續 3 日未收到信，請至 GitHub 的 Actions 分頁檢查執行紀錄。
    </p>
    """

    return f"<html><head>{style}</head><body>{header_html}{table_html}{footer}</body></html>"


def send_report(
    recipients: list[str],
    rows: list[dict],
    product_short: str,
    run_time: datetime | None = None,
):
    run_time = run_time or datetime.now()

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        raise RuntimeError("缺少 GMAIL_USER / GMAIL_APP_PASSWORD 環境變數（請設 GitHub Secrets）")

    # 去除 App Password 可能的空格
    gmail_pw = gmail_pw.replace(" ", "")

    subject = (
        f"[價格監控] {run_time.strftime('%Y/%m/%d %H:%M')} "
        f"{product_short}（{len([r for r in rows if r.get('display_price')])}/{len(rows)} 通路）"
    )

    html = render_html(rows, product_short, run_time)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Price Monitor", gmail_user))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(gmail_user, gmail_pw)
        server.sendmail(gmail_user, recipients, msg.as_string())

    return subject
