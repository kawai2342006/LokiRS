# OpenRS — 美股相對強弱觀測站

可直接部署在 **GitHub Pages** 的獨立靜態網站。沒有 ChatGPT 網站、登入、付費 API、伺服器或 npm 套件依賴。附真實免費行情快照，以及 Python 抓價與 GitHub Actions 更新流程。

以 [RS Terminal 的美股公開頁](https://lazyrs.trade/?tab=stocks) 的欄位為參考，從 Yahoo Finance、FRED 等公開來源獨立抓取計算。不是 Lazybeanz／RS Terminal 官方產品。

**必須區分：價格與各時段回報可以由行情重算；原站完整 LazyRS 權重、長線公式及封存排名沒有公開核實。本站用自己的 OpenRS 開放公式近似替代，因此排名及衍生指標不保證與原站相同。** 網站內「計算方法」及 [欄位對照](docs/REFERENCE_MAP.md) 有完整說明。

## 先部署到 GitHub

1. 將壓縮檔解壓；以 `open-rs` 目錄內的內容作為 GitHub repository 根目錄。根目錄應看到 `index.html`、`assets/`、`data/`、`scripts/`、`config/` 和 `.github/`。
2. 建立一個新的 GitHub repository，將整個專案上傳到 `main` 或 `master`。**必須包含 `.github/workflows/pages.yml`**。使用 Git 時會自動包含此目錄：

   ```bash
   cd open-rs
   git init
   git add .
   git commit -m "Add OpenRS dashboard"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
   git push -u origin main
   ```

3. GitHub repository → **Settings → Pages → Build and deployment → Source → GitHub Actions**。
4. 打開 **Actions → Update data and deploy Pages**，按 **Run workflow**。首次可取消 `refresh_data`，先用附帶的行情快照部署；保留勾選則會先抓價。
5. 成功後，在 **Settings → Pages → Visit site** 或工作流程的 deployment 連結開啟網站。

網站所有路徑均為相對路徑，因此可用於 `https://USERNAME.github.io/REPOSITORY/`，也適用於自訂網域。根目錄 `.nojekyll` 已包含。

GitHub Free 的 Pages 方案通常使用 public repository。Pages 的可用性、Actions 額度及權限依帳戶方案與組織設定而定。以 GitHub 官方 [Pages 設定文件](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) 為準。

## 更新數據

預設於 **星期一至五 22:17 UTC（香港翌日 06:17）** 執行，避開美國夏令／冬令收市時差。美國假期也會執行，但行情仍顯示最近的有效交易日。GitHub 排程不保證準時。

- 手動更新：Actions → Run workflow，勾選 `refresh_data`。
- 本機更新：Python 3.11 或以上，無第三方套件依賴。

  ```bash
  python scripts/update_data.py
  # 明確忽略快取；必要時才使用：
  python scripts/update_data.py --refresh
  # 下載較快／較慢可自行選擇 1–8 個並行請求：
  python scripts/update_data.py --workers 4
  ```

- 網頁右上「檢查更新」**只重讀已發布 JSON**，不會讓 GitHub Pages 自己抓取行情。
- 預設每日一次，**不是即時報價**。小時線欄位代表快照計算時最近完整的常規交易時段。
- 更新後的 `data/latest.json` 會由 Actions 提交並在同一次工作流程部署，因此不依賴另一個 push 工作流程觸發。
- 不要使用很密集的免費端點排程。限速、拒絕存取或資料介面變更都會影響覆蓋率。

如果預設分支不是 `main`／`master`，修改工作流程的 `push.branches`。如果 repository 使用分支保護，須允許該更新機制提交，或刪除「Retain the calculated snapshot」步驟；後者仍會在當次部署使用新快照，但不保留到 Git 歷史。沒有必要建立個人存取權杖。

## 本機預覽

先安裝 Python 3.11+，在專案目錄執行：

```bash
python scripts/serve.py
```

開啟 `http://localhost:5173`。不要直接雙擊 `index.html`：瀏覽器對 `file://` 的 JavaScript modules／JSON 讀取有限制。

亦可使用 Node 22+ 執行 `npm run dev`，無需 `npm install`。網站本身不需要 Node。

## 功能

- 589 隻美股、37 個板塊 ETF 對照；股票池為 2026-11-01 的公開名單快照。
- 相對最強／最弱 Top 10、可排序完整表格、代號／名稱／板塊搜尋、數值條件篩選。
- 價格、1H／4H／1D／一週／一個月相對 SPY 的超額回報。
- OpenRS 分數、名次變動、前 20% 持續日數、長線 RS 百分位、板塊名次、vs 板塊、vs 板塊 1D、21 日 RS 線。
- 市場寬度、FRED 流動性與金融狀況。CNN 恐懼貪婪與 Binance 合約名單是可失敗的可選來源。
- 裝置本機自選清單、最多 10 隻走勢比較、SVG 圖表與目前篩選結果 CSV 匯出。
- 深／淺色外觀、鍵盤操作、手機版、缺值及資料日期提示。

原站會員專用時段、會員趨勢篩選、σ 調整、排名歷史、其他市場與投資人追蹤均不在本專案範圍。

## 計算規則

所有日線均以最近完成交易日計。日線回報、均線、分數與比較圖使用 Yahoo 的 `Adj Close`（股息及拆股調整）；顯示價格及小時線使用 `Close`。這個口徑經公開數值交叉核對，比未計股息的收市價更接近原頁。只用資產與基準同日／同時間戳的數據，缺數據不前向填補。

```text
超額回報（百分點） = 100 × [(個股結束價 / 起始價 − 1) − (SPY 結束價 / 起始價 − 1)]
OpenRS = 0.5 × 超額 1D + 0.3 × 超額 5D + 0.2 × 超額 20D
長線值 = 0.4 × 超額 63D + 0.2 × 超額 126D + 0.2 × 超額 189D + 0.2 × 超額 252D
vs 板塊 = 個股 OpenRS − ETF OpenRS
vs 板塊（1D） = 個股 1D 回報 − ETF 1D 回報
RS 線 = 個股 Adj Close / SPY Adj Close，首點重新定為 100
```

`D` 為 SPY 交易日。一週為 7 個曆日；一個月為前一個曆月同日（月末截至有效日期）。休市時取目標日或之前的最近基準交易日，兩資產仍須在該日均有價格。

1H／4H 參照原頁以小時 K 線的格數計算，用 Yahoo 30 分鐘線重建常規 1H K 線。標準交易日小時 K 線在 10:30、11:30……15:30、16:00 ET 結束；末根只有 30 分鐘，因此收市時 1／4 格實際為 0.5／3.5 小時，跨夜也按交易格計。此口徑與原頁更接近，但 30 分鐘聚合及原來源的小時線仍可有差異。個股詳情及 JSON 另保留精確 1／4 個時鐘小時回報，沒有精確起點時留空。交易所提早收市的當日日線只在標準 16:00 ET 過後納入，這是保守延遲；預設排程已在此之後。

長線百分位在有效樣本間換算到 0–100，同值取平均名次；少於 253 個交易日的股票留空。持續日數由同一固定股票池的歷史價格重算，最多 65+ 日，不是原站封存紀錄，也不是點時成分股回測。股票池變動會影響歷史排名及持續日數。

FRED 淨流動性採 WALCL 週觀測日，扣除當日或之前的 WTREGEN（百萬美元）與 RRPONTSYD（十億美元，先乘 1,000），最後轉為兆美元；分項不能落後超過 8 天。WTREGEN 為每週平均而非週三單日餘額，故與其他淨流動性口徑可有差異。各列顯示自己的觀測日期，估算不可當作即時資金流。詳見網頁「計算方法」。

可在 `config/settings.json` 更改短／長線權重、最低覆蓋率和保存的走勢長度；改後重新抓價。網頁方法說明會讀取快照內實際採用的權重。

## 資料品質與來源限制

- Yahoo chart 是非正式公開端點，無服務保證、無 API key，不等於有即時報價授權。
- CNN 及 Binance 在製作時分別回覆 HTTP 418／451；因此快照內保留缺值／停用合約篩選，沒有以虛構值替代、使用代理或繞過限制。
- FRED 混合頻率下載可能回傳 ZIP。程式會解開各 CSV、處理空值、保留觀測日期及正確單位。
- 有效日線分數覆蓋率低於 80% 時，更新會失敗且不取代 `latest.json`。可選來源失敗不阻擋核心排名；宏觀失敗保留舊值並標記 `stale`。
- 日線不能對齊最近 SPY 交易日的股票不參與當期排名；1H／4H 不能對齊最新基準 bar 則留空。
- `meta.errors` 記錄獨立日線／小時線請求的失敗，`meta.currentCount` 與 `meta.intradayCount` 顯示覆蓋。
- 固定股票池不會自動追蹤新上市、退市或指數換股；在 `config/universe.json` 編輯。分類只採用原公開頁的名稱及 ETF 對照，價格／分數不來自原站。

免費可存取不代表取得再分發授權。Yahoo Finance／其數據供應商的數據以個人研究用途為主；公開展示及其他使用須按來源條款另行確認。程式碼 MIT 授權不涵蓋行情內容、第三方商標或來源內容。

## 驗證及檔案

```bash
python -m unittest discover -s tests -v
node --test tests/charts.test.js
node --check assets/app.js
python scripts/build.py
```

計算測試涵蓋超額百分點、月底／閏年／假期錨點、缺失交易日、同值百分位、小時 K 線短末根、精確時鐘小時跨度、未完成 bar、FRED ZIP 與流動性單位，及圖表共同日期重設。當次抓價的實際驗證結果見 `docs/VALIDATION.md`。

```text
index.html                  網站入口
assets/                     原生 JavaScript、CSS、SVG；無 CDN
config/universe.json        589 股及 37 ETF 對照，可自行修改
config/settings.json        公開公式與更新參數
data/latest.json            可直接展示的真實行情快照
scripts/providers.py        免費資料適配器
scripts/engine.py           計算邏輯
scripts/update_data.py      抓價、資料品質門檻、原子寫入
scripts/build.py            複製公開檔案到 _site
scripts/serve.py            本機預覽
tests/                      金融計算與圖表驗證
.github/workflows/pages.yml GitHub 更新與部署
docs/REFERENCE_MAP.md        原頁功能與本專案的對照
```

官方參考：[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)、[FRED](https://fred.stlouisfed.org/)、[Yahoo Finance](https://finance.yahoo.com/)、[yfinance 對 Yahoo 資料使用的說明](https://ranaroussi.github.io/yfinance/)（本專案並未依賴 yfinance）。
