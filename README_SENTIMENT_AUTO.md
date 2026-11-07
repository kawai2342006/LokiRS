# 收市後自動更新「恐懼與貪婪」

已確認目前倉庫的自動股價更新正常，但 2026-11-07 的 GitHub runner 讀取 MacroMicro 公開頁面得到 HTTP 403、CNN 端點得到 HTTP 418，因此情緒數值只能保留 2026-10-30 並顯示「舊值」。改動是補上另外一個公開、定時發佈的 CNN 資料鏡像，並讓情緒部署不依賴 589 股批量抓價是否成功。

來源順序：MacroMicro 公開頁面 → CNN 端點 → [公開 CNN 歷史數據鏡像](https://github.com/whit3rabbit/fear-greed-data)。第三個來源在網站標示為「公開鏡像（轉載 CNN）」，絕不冒充 CNN 官方連線，也不換成 Crypto 或另一套自行計算的指數。只使用明確的 0–100 讀數及觀測日期；來源資料未到當前美股交易日，就標記舊值並保留原日期。

`.github/workflows/pages.yml` 原本已安排香港時間週二至週六 06:17 及 08:17 的更新，整批更新時同時嘗試情緒來源。新增 `.github/workflows/sentiment.yml` 在香港時間**週二至週六 09:47** 再單獨檢查情緒；取得新的、至少跟目前股票快照同日的讀數，才提交 `data/sentiment.json` 並重新部署 Pages。沒有新觀測便略過提交及部署，不會把舊數值改成今日日期。鏡像本身於美股收市後嘗試每日更新；GitHub 排程可能延遲，來源亦可能未及時發佈，因此這是自動重試，不是準時出新數值的保證。

## 上傳與檢查

1. 解壓更新包到 LokiRS 倉庫根目錄，**兩份 `.github/workflows/pages.yml` 及 `sentiment.yml` 都要保留路徑**，提交至 `main`。
2. 首次提交由 **Update data and deploy Pages** 的 `push` 執行發布。如要之後即時重查，Actions → **Update sentiment and deploy Pages** → **Run workflow**。讀數較倉庫記錄新時才建置並部署；包內已有相同日期及數值時會成功略過部署。
3. `prepare` 和 `deploy` 都成功後重新整理網站，檢查情緒欄的觀測日期與來源標籤。頁面上的 Refresh 只讀已部署 JSON，不能直接替 GitHub runner 抓價。

這個流程單獨抓情緒，不重抓股票；已驗證的 2026-11-06 情緒觀測可隨更新包一併上傳。更新包是本地準備，尚未代你提交或部署到 GitHub。
更新包同時包含上一版 v1.3.2 的 11 月 6 日美股分數補正，可直接覆蓋目前公開倉庫，不需要先安裝上一個 ZIP。
