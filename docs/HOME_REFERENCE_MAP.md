# LazyRS 首頁 → LokiRS 主頁對照

參考頁：https://lazyrs.trade/ 。檢視日期：2026-11-01。沿用使用者指定的 Loki Archive 主題。

| 原頁公開部分 | LokiRS 實作與來源 | 口徑／限制 |
| --- | --- | --- |
| SPY／QQQ／BTC／UUP／GLD／USO 行情卡 | Yahoo Finance 完整日線、顯示 Close，回報採 Adj Close | 卡片各自保留日期；BTC 為 UTC 日；並非即時價 |
| 今日行情重點 | 既有美股寬度、Yahoo／CBOE VIX、CoinGecko 及跨市場計算 | 規則生成，直接列明門檻 |
| risk-on／off 標籤 | 寬度 ≥60 加一、≤40 減一；VIX ≤15 加一、≥25 減一 | 只在寬度與 VIX 觀測日相同時計算；合計正／負／零為偏強／偏弱／中性 |
| 寬度強弱文字 | ≥70% 偏強、≤30% 偏弱，其餘中性 | 原頁公開門檻；樣本為目前美股股票池 |
| VIX | 完整日線的指數值、一日點數變化、20 日區間 | 個別日期；不是 VIX ETF |
| RS Pulse | 本站既有分數與日線名次，公開替代篩選規則 | 目前只用 589 隻美股；未重建完整港股池；分數公式影響名單 |
| 穩定幣供應 | DefiLlama `totalCirculatingUSD.peggedUSD` | 明確標為美元穩定幣；不把其他幣別原幣數量直接相加 |
| BTC 市佔及總市值 | CoinGecko `/api/v3/global` | 使用原 `updated_at`，不是頁面刷新時間 |
| 港股通南向 | HKEX SSE 與 SZSE Southbound 的 Buy Turnover − Sell Turnover | 原欄位百萬港元先換成港元；畫面以億港元顯示；五日合計需五個實際南向交易日 |
| 跨市場表 32 項資產 | 固定公開名單；Yahoo 股息／拆股調整日線 | 配對相同 SPY 交易日；價格維持原貨幣，不另做匯率換算 |
| 1D／5D／20D／60D | 各資產該段回報 − 當段有效樣本中位數 | 至少 80% 有效樣本；缺起訖資料留空；不同市場收市時點仍有差異 |
| LazyRS 分數 | 本站 LokiRS = 0.5×1D + 0.3×5D + 0.2×20D 超額 | 公開替代公式；沒有宣稱還原原站完整權重 |
| Δ5D | 固定 32 項池在五個 SPY 交易日前重新計算排名，再減去目前名次 | 不是借用原站封存排名；期間或樣本差異會影響名次 |
| RS 線 | 每日有效資產回報中位數建立參考指數，再與價格做比值 | 首點 100；不足連續共同日期時留空，避免跨休市補值 |
| 最新文章 | 原作者公開標題、日期與 HTTPS 連結 | RSS 今次不是有效 feed，保留原首頁公開標題快照並標記；後續有效 RSS 才更新 |
| 收合、排序、分類、複製、匯出 | 瀏覽器本機處理 | 自動 60 秒只檢查發布快照；數據更新由 Python／Actions 執行 |
| 關於／常見問題 | 依 LokiRS 實際功能撰寫 | 沒有聲稱已建立其他市場完整選股頁 |
| 會員、暫時試用、廣告及社群招募 | 略過 | 延續原任務的免費資料與獨立網站範圍 |

## 原站與新版本的差異

同日核對顯示 VIX、美元穩定幣及南向資料的顯示值接近／符合參考頁；跨市場分數、排名與部分期間回報有明顯差異。完整權重未獲核實；此外，原頁與 Yahoo 的報價時間、香港／加密日線期間，以及原頁「全市場」基準的樣本範圍未能全部核實。

因此新版清楚標示「vs 32 項資產中位數」與 LokiRS 近似分數，不把它描述成原站相同數字。原站數字只用作離線檢查，網站更新器不使用其行情或排名作為來源。

## 主要公開來源

- Yahoo Finance：https://finance.yahoo.com/
- CBOE VIX：https://www.cboe.com/tradable_products/vix/
- CoinGecko：https://www.coingecko.com/en/global-charts
- DefiLlama：https://defillama.com/stablecoins
- HKEX：https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en
- Lazybeanz 原文：https://lazybeanz.substack.com/archive
