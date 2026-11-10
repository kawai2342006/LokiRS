# LokiRS v1.4.0 — 更新與分數覆核（2026-11-10）

已完成本機修正及獨立行情重算，**尚未推送或部署到現有網站**。本包的美股資料為 **2026-11-09 美國收市**。公開網站檢查時，LokiRS 仍提供 2026-11-06 快照；LazyRS 已提供 2026-11-09 資料。

## 重新讀取失效的原因

1. 頁面上的重新讀取只下載已發布的 JSON，沒有後台抓價或 GitHub workflow_dispatch 呼叫。GitHub Pages 是靜態網站，因此按鈕不能直接執行 Python。
2. 原本只有首頁每 60 秒檢查發布版本，美股／自選／比較頁沒有這個排程。
3. 公開 Actions API 最後一個股票更新是 2026-11-07 10:20 UTC 開始的成功執行（香港 18:20）；最後可見的定時股票執行為同日 06:10 UTC（香港 14:10）。檢查時未出現其後新股票執行。工作流程仍是 active，default branch 是 main；不能據此斷言是抓價失敗，也未能證實帳戶或 GitHub 排程層面的原因。
4. 本次 Yahoo 日線大量出現 11 月 9 日日期但 Close／Adj Close 為 null，完整小時線則已提供。舊版會先逐隻重試日線，才恢復可用的完整收市資料，拖長更新。
5. 股票池停在 589 股，原站目前為 596 股。已加入 DEO、GOOGM、GOOGN、MDLN、OKTA、SONY、TM、VYLR，並移除原站不再列出的 KVUE。自選資料仍留在瀏覽器儲存；不在新名單的代號不參與當期排名。

## 分數比較

以下固定使用原網站可排名的 **588 隻共同股票**；雙方都在相同股票集合內重新排名，排除新增股票造成的名次平移。

| 指標 | 檢查時已發布 LokiRS | 本包最新獨立重算 |
| --- | ---: | ---: |
| LokiRS 行情日期 | 2026-11-06 | 2026-11-09 |
| LazyRS 行情日期 | 2026-11-09 | 2026-11-09 |
| 平均分數絕對差距 | 1.145264 | 0.009366 |
| 平均名次絕對差距 | 77.844 | 0.997 |
| 前 20 名名單重疊 | 12/20 | 20/20 |
| 前 100 名名單重疊 | 64/100 | 100/100 |

左欄包含跨交易日差距，**不能當成舊公式誤差**。主要改善來自更新交易日、收市價及公司行動資料，並非重新擬合權重。

用更新後完整 **596 隻**同交易日比較：平均分數差 **0.009307**，中位數 **0.004650**，95% 的股票誤差不超過 **0.027300**；平均名次差 **0.993**，最大 **45** 名。前 10／20／50／100 名名單均完全重疊，名單相同不表示每個位置相同。

完整逐股分數、價格、五項輸入及名次差距：`reports/comparison-2026-11-09.csv`。原網站跨日對照：`reports/published-before-2026-11-10.csv`。固定 588 股結果另見 `reports/comparison-2026-11-09-original-cohort.json`。

## 計分權重

```text
LokiRS = 0.25 × 1H 超額 + 0.25 × 4H 超額 + 0.25 × 1D 超額
       + 0.15 × 5D 超額 + 0.10 × 20D 超額
```

權重不變。以原站最新 596 筆公開預設輸入驗算，最大差距 0.00007500 分，符合顯示精度。這是公開未啟用波動率調整模式的覆核；不是官方公式確認，也未驗證會員模式。

行情及產品分數由 Yahoo 獨立計算；原站數字只用作核對報告，沒有寫入產品行情來偽造一致結果。

## 已修正的更新流程

- 美股、自選及比較頁每 60 秒檢查已發布快照；返回可見分頁時立即檢查。支援暫停，避免重疊下載。
- 首頁共用相同的可見分頁恢復檢查。舊版 CDN 回應不能覆蓋較新的日期或發布版本。
- 重讀相同快照時明示行情日期，不再聲稱已是最新行情。快照超過 36 小時未發布新版本時提示使用者檢查是否已有新交易日，不把週末直接判為交易日錯誤。
- 新增「抓取最新行情」入口，連到現有 Actions。倉庫擁有人按 Run workflow 並啟用 refresh_data 後，由 GitHub 抓價、計分及部署；完成發布後頁面自動檢查會取得新版本。前端沒有儲存 GitHub token。
- 股票更新嘗試時間改為香港交易日後 06:27、08:37、11:17（UTC cron 22:27、00:37、03:17），避開整點並增加後備嘗試。GitHub cron 可能延遲或漏觸發，不能保證精準時間。
- 股票及情緒工作流程取得共同部署鎖後，checkout 當前分支最新版本，減少排隊後使用舊事件 SHA 的機會。
- Actions 摘要顯示股票交易日、發布時點、覆蓋率及首頁股票日期；本機 build 自行產生輸出所需的 nojekyll 標記。

## 收市資料、派息及剩餘差距

日線缺值時，必須先有完整、已觀測的常規 30 分鐘交易時段。優先使用同一已完成時段且時戳在收市後 0–300 秒內的常規報價；否則使用最後完整 30 分鐘收市。仍保留恢復標記、時點及 CSV 來源，不把它冒充原生已完成日線。先恢復符合條件資料，再重試仍未解決的日線。

一般公司行動、拆股、未知調整因子仍阻止恢復；只有具獨立日期及金額的普通現金派息可用已知調整因子處理，並防止重複派息補正。新核對 AMP 1.70、GWW 2.49、LNG 0.625、VMC 0.52 美元／股的 11 月 9 日派息；來源與記錄日保留在 `config/verified_dividends.json`。

INFY：Deutsche Bank 公開存託資料列出 11 月 3 日 **暫定**總派息 0.274815 USD（淨額 0.234805，不用作總回報調整），狀態為 Approx。已採用公開暫定總額補正缺失的調整價，並在畫面、CSV 及快照保留 provisional 標記；銀行定案後須覆核。這不是最終美元派息確認。

| 代號 | LazyRS | LokiRS | Loki − Lazy | 共同池名次差 |
| --- | ---: | ---: | ---: | ---: |
| HLT | +1.6810 | +2.1476 | +0.4666 | -45 |
| SCCO | -0.5978 | -0.8126 | -0.2148 | +13 |
| NVR | +1.2261 | +1.1187 | -0.1074 | +12 |
| MARA | -1.4174 | -1.4909 | -0.0735 | +3 |
| LYG | +0.9605 | +0.9054 | -0.0551 | +5 |
| ESS | +0.8290 | +0.7785 | -0.0505 | +9 |
| SOMN | +0.6262 | +0.5765 | -0.0497 | +9 |
| CBOE | +1.5037 | +1.4628 | -0.0409 | +3 |

HLT 的價格來源差異最明顯：LazyRS 373.23，Yahoo 常規報價 376.53，因而分數差 0.4666。未以原站價格覆蓋獨立行情。SCCO 同時涉及現金及股票派息，原始調整與公告細節未完全一致，沒有按目標分數猜調整；NVR 主要是小時線來源差異。相近分數仍可能有數名差距。

板塊有效分數目前 **35/37**；IPAY、PBJ 缺完整有效資料，相關板塊排名及 vs 板塊保留缺值。主頁 27/32 個跨市場資產有效，FRED／部分文章保留各自原日期。這些不代表 596 股分數缺值。

## 安裝到現有 GitHub Pages

1. 解壓本包，把 `LokiRS-main/` **內的內容**放到現有 LokiRS repository 根目錄，並完整保留 `.github/workflows/`，不要把整個資料夾再套一層。
2. 一併更新 assets、scripts、config、index.html、package.json、data；不能只換 JSON 或只換前端。
3. 確認 Settings → Pages 的 Source 使用 GitHub Actions。到 Actions → Update data and deploy Pages → Run workflow，選 main，啟用 refresh_data。
4. 等 prepare 及 deploy 都成功，在網站確認美股日期至少是 2026-11-09。如果後續還是沒有新排程紀錄，檢查 Actions 是否啟用、執行者狀態及帳戶限制；本包不能代替帳戶層檢查。

若此時原站／市場已有更新交易日，應先用更新流程再抓行情，避免把本包日期當作將來的最新資料。`preview/LokiRS_Nov10_Preview.html` 可直接開啟，內嵌固定日期資料作離線審閱，無法持續抓價，不需發布。

```bash
python3 scripts/update_data.py --refresh --workers 4
python3 scripts/compare_rankings.py --output comparison.json --csv comparison.csv
python3 -m unittest discover -s tests -v
node --test tests/*.test.js
python3 scripts/build.py
```

## 驗證及來源

已通過 83 項 Python 測試、9 項 JavaScript 測試、JavaScript／Python 語法檢查、workflow YAML 解析、快照驗證及靜態 build。新增測試涵蓋自動檢查／暫停／切回分頁／重疊防護、舊快照拒收、報價時點、現金派息不重複計算、暫定狀態沿用、CSV 欄位對齊，以及跨日比較不可誤稱公式驗證。瀏覽器控制未獲准，因此未聲稱已做真實桌面或手機視覺驗收。

- [LazyRS 公開預設美股頁](https://lazyrs.trade/?tab=stocks)
- [LokiRS 現有快照](https://kawai2342006.github.io/LokiRS/data/latest.json)
- [LokiRS Actions](https://github.com/kawai2342006/LokiRS/actions/workflows/pages.yml)
- [GitHub schedule 事件說明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Ameriprise 派息公告](https://ir.ameriprise.com/news/news-details/2026/Ameriprise-Financial-Declares-Regular-Quarterly-Dividend-61e458ebe/default.aspx)
- [Grainger 派息公告](https://invest.grainger.com/investor-news/news-details/2026/GRAINGER-DECLARES-QUARTERLY-DIVIDEND-fcfa98f72/default.aspx)
- [Cheniere SEC 披露](https://www.sec.gov/Archives/edgar/data/3570/000000357026000040/cei20263rdqtrerex991.htm)
- [Vulcan 派息公告](https://www.vulcanmaterials.com/news-and-events/press-releases/2026/vulcan-declares-quarterly-dividend-on-common-stock-122511)
- [Deutsche Bank INFY 存託資料](https://adr.db.com/drwebrebrand/dr-universe/dr_details.html?identifier=116)
- [Deutsche Bank 公開派息歷史資料](https://adr.db.com/drwebrebrand/api/druniverse/dividend-history/116)
- [Southern Copper 現金及股票派息披露](https://www.sec.gov/Archives/edgar/data/1001838/000110465926117588/scco-20261020x8k.htm)
- [FINRA T+1 普通派息記錄日規則](https://www.finra.org/sites/default/files/2024-02/Regulatory_Notice_24-04.pdf)

機器可讀覆核結果及來源雜湊：`data/verification_2026-11-10.json`。數值只覆核本次收市快照，並非保證未來交易日、會員模式、長線 RS、歷史 Δ 或板塊欄位與原站完全一致。
