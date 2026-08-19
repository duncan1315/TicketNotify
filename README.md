# Flight price tracker

追蹤 trip.com 上特定航線的票價，低於預算時發 Discord 或 Telegram 通知。前端是 GitHub Pages 上的靜態儀表板，實際爬蟲跟排程都跑在 GitHub Actions。

## 架構

- `index.html` / `assets/` — GitHub Pages 儀表板，讀 `data/index.json` 畫出每條路線的卡片
- `.github/ISSUE_TEMPLATE/track-route.yml` — 新增追蹤路線用的 Issue Form
- `.github/workflows/parse-route-issue.yml` — 開 issue 後把表單內容轉成 `routes/*.json`
- `.github/workflows/scrape-scheduled.yml` — 排程執行 `scraper/scrape.py`，更新 `data/`
- `.github/workflows/manual-query.yml` — 手動查詢，支援 Actions 頁面觸發或在 issue 留言 `/check`
- `scraper/` — Python 爬蟲本體（Playwright）與通知邏輯

## 設定步驟

1. **設定前端連結**：把 `assets/app.js` 最上面的 `REPO` 改成你自己的 `使用者名稱/repo名稱`。
2. **開啟 GitHub Pages**：Settings → Pages → Source 選 `Deploy from a branch`，Branch 選 `main` / `/(root)`。
3. **開啟 Discord 通知**：在你的 Discord 頻道建立一個 Incoming Webhook，複製網址後到 Settings → Secrets and variables → Actions，新增 secret `DISCORD_WEBHOOK_URL`。若想改用 Telegram，改建立 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID` 兩個 secret，並在追蹤表單選 telegram。
4. **新增第一條追蹤路線**：到 Issues 頁籤，用 "Track a new flight route" 範本開一個 issue，`parse-route-issue.yml` 會自動把它轉成 `routes/route-{issue編號}.json`。
5. **等排程執行，或手動觸發**：`scrape-scheduled.yml` 預設每 30 分鐘跑一次，也可以到 Actions 頁籤手動 Run workflow。跑完會更新 `data/`，儀表板重新整理就看得到。
6. **手動查詢單一航班**：到 Actions 頁籤選 "Manual query" 手動輸入條件，或在任一個 issue 底下留言，例如：

   ```
   /check TPE NRT 2026-09-15 6000 300
   ```

   格式是 `/check 出發地 目的地 日期 [預算] [最大飛行分鐘數]`，後兩個可省略。

## 目前已知的限制

- **trip.com 的選取器是起點，不是保證**：`scraper/scrape.py` 裡 `extract_flights()` 用的 CSS selector（`data-testid="flight-item"` 等）是根據一般 SPA 常見寫法先放上去的預估值，我沒辦法在這個環境裡實際渲染 trip.com 的頁面驗證，你第一次跑起來大概率需要打開瀏覽器開發者工具重新對照實際 DOM 調整。
- **一次只查 `earliest_date`**：目前爬蟲只用追蹤設定裡最早的日期去查，還沒有把 `earliest_date` 到 `latest_date` 整段日期都掃過一輪，這是可以之後加的功能（迴圈呼叫 `build_search_url` 換不同日期即可）。
- **服務條款與穩定性**：trip.com 的使用條款通常不允許自動化存取，站方也可能有速率限制或機器人偵測，爬蟲被擋掉、或改版後選取器失效都算預期內。如果你比較在意長期穩定性，可以考慮換成有官方 API 的資料源，例如 Kiwi.com 的 Tequila API 或 Amadeus Self-Service API，一樣能查即時票價又不用擔心站方隨時改版或封鎖。
- **Actions 分鐘數額度**：免費方案的私有 repo 每月有 Actions 執行分鐘數上限，Playwright 安裝瀏覽器本身就要花一些時間，如果覺得太耗額度可以把 cron 間隔拉長（例如改成每小時一次）。
- **幣別參數是盡力而為**：`curr` 這個查詢參數是照你填的 `currency` 直接帶入 trip.com 的網址，不同地區站台支援的幣別代碼可能不完全一樣，需要的話可以在 `TRIP_DOMAIN` / `TRIP_LOCALE` 環境變數調整成你所在地區對應的網域。

## 之後可以做的事

- 在儀表板加入價格歷史折線圖（`data/{route-id}/history.jsonl` 已經有原始資料）
- 掃描整段日期區間，抓最低價出現在哪一天
- 針對爬蟲失敗加上重試機制，並把連續失敗的狀況也回報到 Discord
