# 多通路價格監控系統

每日自動爬取 MOMO、蝦皮、全聯、家樂福、酷澎的商品價格，並寄送 HTML 表格 Email。

---

## 一、本系統會做什麼

每天 **08:00** 和 **16:00**（台北時間），系統會自動：

1. 到 5 個通路（MOMO、蝦皮、全聯、家樂福、酷澎）搜尋你指定的商品
2. 抓出符合規格的商品價格（會自動排除「低脂」「巧克力」等不要的版本）
3. 偵測「首購」「新客」等促銷字眼，並在報表上紅字標記
4. 寄一封 HTML 表格 Email 給你
5. 把當天結果存到 `data/price_history.csv`，供日後分析

---

## 二、首次安裝步驟（只需做一次）

### 步驟 1：把這個資料夾上傳到 GitHub

1. 開啟 https://github.com/v0989575670-lang/price
2. 點 **Add file → Upload files**
3. 把這個資料夾裡的**所有檔案和資料夾**拖進去（注意要包含 `.github` 這個隱藏資料夾）
4. 下方 commit message 填 `Initial commit`，點 **Commit changes**

> 若 `.github` 資料夾在 Windows 看不到，請打開「檔案總管 → 檢視 → 隱藏的項目」勾選。

### 步驟 2：設定 GitHub Secrets（這裡放 Gmail 密碼）

1. 進入 repo → **Settings**（最上排最右邊）
2. 左側選單 → **Secrets and variables → Actions**
3. 點 **New repository secret**，依序新增：

   | Name | Secret 內容 |
   |---|---|
   | `GMAIL_USER` | `v0989575670@gmail.com` |
   | `GMAIL_APP_PASSWORD` | 你的 16 位 App Password（**不要有空格**） |

> Gmail App Password 通常會顯示成 `abcd efgh ijkl mnop` 格式，請把空格全部去掉再貼。

### 步驟 3：給 GitHub Actions 寫入 repo 的權限

因為系統會把歷史價格寫回 repo，需要授權：

1. 進入 repo → **Settings → Actions → General**
2. 滑到底，「Workflow permissions」選 **Read and write permissions**
3. 點 **Save**

### 步驟 4：手動觸發第一次測試

1. 進入 repo → **Actions** 分頁
2. 左側選 **Daily Price Monitor**
3. 右側點 **Run workflow → Run workflow**
4. 等 3~5 分鐘，refresh 一下，應該會看到綠色勾勾
5. 檢查兩個收件信箱有沒有收到 Email

如果沒收到信，點進去那次 workflow 看 log 找原因，或把 log 截圖傳給我。

---

## 三、之後要改設定怎麼辦

### 增加 / 修改 監控商品

編輯 `config/products.yaml`，新增一筆 product 區塊即可：

```yaml
products:
  - name: "光泉 成分無調整 保久乳 200ml × 24 入"
    short_name: "光泉保久乳200ml*24"
    search_keywords: ["光泉", "保久乳", "200ml"]
    must_include: ["光泉", "保久乳"]
    must_include_any: ["200ml", "200 ml", "200ML"]
    must_exclude: ["調味", "低脂", "巧克力"]
```

存檔、commit、push 後，下次排程就會生效。

### 增加 / 修改 收件人

編輯 `config/products.yaml` 的 `recipients` 區塊。

### 改執行時間

編輯 `.github/workflows/daily-price.yml` 的 `cron`。
注意 GitHub Actions 用 **UTC 時區**，所以：

| 你想要的台北時間 | cron 寫法（UTC） |
|---|---|
| 08:00 | `0 0 * * *` |
| 16:00 | `0 8 * * *` |
| 23:00 | `0 15 * * *` |

---

## 四、檔案結構

```
.
├── .github/
│   └── workflows/
│       └── daily-price.yml    # 排程設定
├── config/
│   └── products.yaml          # 商品、收件人、通路設定
├── src/
│   ├── main.py                # 主流程
│   ├── filter.py              # 首購偵測 + 規格過濾
│   ├── storage.py             # 歷史價格儲存
│   ├── mailer.py              # Email 寄送
│   └── scrapers/              # 各通路爬蟲
│       ├── base.py
│       ├── momo.py            # ✅ 完整實作
│       ├── shopee.py          # 🚧 待實作
│       ├── pxmart.py          # 🚧 待實作
│       ├── carrefour.py       # 🚧 待實作
│       └── coupang.py         # 🚧 待實作
├── data/
│   └── price_history.csv      # 自動產生
├── requirements.txt
└── README.md
```

---

## 五、常見問題

**Q: 為什麼只有 MOMO 抓得到，其他通路顯示「未實作」？**
這是第一階段 PoC（概念驗證）。先確認整個流程跑得通、收得到信，再逐一補上其他通路爬蟲。蝦皮和酷澎反爬比較嚴，需要單獨處理。

**Q: 商品搜尋抓到錯規格怎麼辦？**
編輯 `products.yaml`，在 `must_include` / `must_exclude` 加入更精準的關鍵字。例如要排除「200ml × 6 入」就在 `must_exclude` 加 `"6入"`。

**Q: GitHub Actions 跑失敗（紅色叉叉）怎麼辦？**
點進那次執行的 log，最常見原因是：
- `GMAIL_APP_PASSWORD` 沒設或設錯（檢查有沒有空格）
- 通路網站改版，selector 失效（告訴我，我來修）
- 商品搜尋結果都被 `must_exclude` 過濾掉了

**Q: 系統會自動更新 `price_history.csv` 嗎？**
會。每次成功執行後，GitHub Actions 會自動 commit 新資料回 repo。

---

## 六、安全提醒

- Gmail App Password 只存在 GitHub Secrets 裡，加密保存
- 公開 repo 也安全，因為 Secrets 不會出現在程式碼或 log
- 萬一 password 不小心外洩，到 https://myaccount.google.com/apppasswords 撤銷重發即可
