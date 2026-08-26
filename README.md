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
4. **（選用）啟用 Gemini 轉機次數輔助判斷**：`scraper/scrape.py` 會先用固定的文字規則（`STOPS_TEXT_PATTERN`）從卡片文字判斷轉機次數，規則判斷不出來時才會呼叫 Gemini 補上判斷，Gemini 也判斷不出來時仍然維持未知，不會硬猜一個數字出來。要啟用這一步，到 [Google AI Studio](https://aistudio.google.com/apikey) 申請一組 API key，一樣到 Settings → Secrets and variables → Actions 新增 secret `GEMINI_API_KEY`。沒有設定這個 secret 完全不影響原本功能，只是轉機次數判斷不出來時會顯示「unknown」。`scraper/ai_stops.py` 裡的 `MODEL_FALLBACK_LIST` 定義了依序嘗試的模型，遇到額度超過（HTTP 429）會自動換下一個模型；清單裡的 `gemini-3.1-pro-preview` 沒有免費額度、`gemini-3-flash-preview` 已被 Google 標記為棄用，保留兩者是為了額度用盡時多一層備援，需要的話可以自行調整這份清單。
5. **新增第一條追蹤路線**：到 Issues 頁籤，用 "Track a new flight route" 範本開一個 issue，`parse-route-issue.yml` 會自動把它轉成 `routes/route-{issue編號}.json`。表單裡的 Trip type 選 One way 就不用填 Return date；選 Round trip 的話 Return date 是必填，沒填會在 parse 這步直接失敗（可以到 Actions 的 "Parse route issue" run 裡看到失敗訊息），修正後把 issue 內容編輯一次即可重新觸發解析。
6. **等排程執行，或手動觸發**：`scrape-scheduled.yml` 預設每 30 分鐘跑一次，也可以到 Actions 頁籤手動 Run workflow。跑完會更新 `data/`，儀表板重新整理就看得到。
7. **手動查詢單一航班**：到 Actions 頁籤選 "Manual query" 手動輸入條件，或在任一個 issue 底下留言，例如：

   ```
   /check TPE NRT 2026-09-15 6000
   ```

   格式是 `/check 出發地 目的地 日期 [預算]`，預算可省略。

## 頁面解析方式

Playwright 載入頁面後用 CSS selector 抓資料，selector 定義在 `scraper/scrape.py` 的 `CARD_SELECTOR` / `PRICE_SELECTOR` / `DURATION_SELECTOR` / `AIRLINE_SELECTOR`。trip.com 的票價卡片是非同步載入的（先出現 shimmer 骨架、資料到了才填進去），所以 `extract_flights()` 會先等第一筆價格出現，再多等一段時間讓已載入的卡片數量穩定下來才讀取，避免讀到還沒填值的卡片。這批 selector 是照實際 debug snapshot 核對過的，但 trip.com 改版就可能失效——如果發現抓不到航班，先看同一個 run 上傳的 debug-snapshot 附件（截圖 + HTML），對照目前的 selector 常數確認是不是哪個 `data-testid` 換了。

轉機次數（stops）沒有固定的 `data-testid` 可以選，`parse_stops()` 是改用固定的文字規則（`STOPS_TEXT_PATTERN`）掃卡片的可見文字判斷。規則判斷不出來時，`fill_unknown_stops()` 會把這幾張卡片的原始文字交給 `scraper/ai_stops.py` 的 Gemini 補判斷（見上方設定步驟第 4 點），成功的話結果會寫回同一個 flight 的 `stops` 欄位，跟規則判斷出來的結果混在一起用，不會另外標記來源；兩邊都判斷不出來就維持 `None`。這個欄位會同時影響 Discord 通知（`notify.py` 的 `format_match()`）和儀表板（`data/{route-id}/latest.json` 的 `lowest_price_stops`，只記錄最低價那班的轉機次數，不是每一班都記）。

## 目前已知的限制

- **一條路線只查一個日期**：route 只有單一 `date` 欄位，沒有日期區間。想比較不同日期就開多張 issue，各自追蹤一個日期，不會互相干擾。
- **服務條款與穩定性**：trip.com 的使用條款通常不允許自動化存取，站方也可能有速率限制或機器人偵測，爬蟲被擋掉都算預期內。如果你比較在意長期穩定性，可以考慮換成有官方 API 的資料源，例如 Kiwi.com 的 Tequila API 或 Amadeus Self-Service API，一樣能查即時票價又不用擔心站方隨時改版或封鎖。
- **Actions 分鐘數額度**：免費方案的私有 repo 每月有 Actions 執行分鐘數上限，Playwright 安裝瀏覽器本身就要花一些時間，如果覺得太耗額度可以把 cron 間隔拉長（例如改成每小時一次）。
- **幣別參數是盡力而為**：`curr` 這個查詢參數是照你填的 `currency` 直接帶入 trip.com 的網址，不同地區站台支援的幣別代碼可能不完全一樣，需要的話可以在 `TRIP_DOMAIN` / `TRIP_LOCALE` 環境變數調整成你所在地區對應的網域。
- **轉機次數判斷是盡力而為**：文字規則判斷不出來、沒設定 `GEMINI_API_KEY`，或 Gemini 也判斷不出來時，`stops` 會維持未知，Discord 與儀表板會顯示成「unknown」／「Stops unknown」，不會顯示猜錯的次數，但也不保證每次都判斷得出來。清單裡的 `gemini-3.1-pro-preview` 沒有免費額度，長時間掛著跑要留意費用。

## 疑難排解

**Actions 顯示成功，但 `data/` 沒更新、也沒收到通知**

`scraper/scrape.py` 設計成就算單一路線爬取失敗，也不會讓整個 workflow 顯示失敗（錯誤會被 catch 起來，`flights` 變空陣列後繼續跑下一條），所以「run 顯示綠色勾勾」不代表真的爬到資料。照下面順序排查：

1. 先確認 `routes/` 資料夾底下真的有 `route-*.json` 檔案。如果沒有，代表 issue 沒有被成功解析成路線設定，去檢查 "Parse route issue" 這個 workflow 有沒有跑過、有沒有失敗（常見原因：開 issue 時沒有選用 "Track a new flight route" 範本，導致沒有自動帶上 `track-route` label，workflow 的 `if: contains(...)` 條件就不會成立）。
2. 如果 `routes/*.json` 存在，打開 "Scheduled scrape" 這個 run，展開 "Run scraper" 這一步的 log。如果看到 `No active routes found`，代表讀到的路線裡沒有 `active: true` 的項目。如果看到 `Failed to scrape route-xxx: ...`，通常是 selector 等不到（trip.com 改版）或 `route` 缺少某個必要欄位，訊息裡會附上原始的例外內容；同一個 run 上傳的 debug-snapshot 附件（截圖 + HTML）可以確認當下頁面實際長怎樣，拿去對照 `scrape.py` 裡的 `CARD_SELECTOR` / `PRICE_SELECTOR` / `DURATION_SELECTOR` / `AIRLINE_SELECTOR` 是不是還對得上。
3. 就算沒解析出任何航班，`save_results()` 還是會寫入 `data/{route-id}/latest.json`（`lowest_price` 會是 `null`）。所以如果連這個檔案都沒出現，通常表示第 1 點的情況——`routes/` 底下根本沒有作用中的路線。
4. Discord 沒收到通知，先確認前面幾點都正常（有抓到航班、且低於預算），再檢查 repo 的 Settings → Secrets and variables → Actions 裡有沒有 `DISCORD_WEBHOOK_URL`，以及 webhook 網址是不是還有效（Discord 頻道設定裡可以重新查看或重建）。

**排程沒有每 30 分鐘準時執行一次**

這是 GitHub Actions 本身的已知行為，不是這個專案設定錯誤：GitHub 官方文件明講 schedule 事件在負載高的時段可能會延遲，尤其是整點與半點前後（因為全世界排在整點/半點的 workflow 特別多），实测延迟 15 到 30 分鐘以上都算常見，免費方案的 public repo 更容易碰到。已經把 cron 從 `*/30 * * * *`（整點跟半點）改成 `7,37 * * * *`（每小時的第 7 分跟第 37 分），避開尖峰時間可以降低延遲機率，但 GitHub 官方本來就不保證準時，如果你需要精確到分鐘的觸發時間，需要靠外部排程服務（例如 cron-job.org、Cronitor）呼叫 `workflow_dispatch` 來觸發，而不是完全依賴 `schedule`。

## 之後可以做的事

- 在儀表板加入價格歷史折線圖（`data/{route-id}/history.jsonl` 已經有原始資料）
- 掃描整段日期區間，抓最低價出現在哪一天
- 針對爬蟲失敗加上重試機制，並把連續失敗的狀況也回報到 Discord
