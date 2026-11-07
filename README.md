# LokiRS — 跨市場情報主頁

以免費公開來源計算的市場觀測網站，採用 Loki Archive 深綠黃銅風格，可獨立部署到 GitHub Pages。前端使用原生 HTML／CSS／JavaScript，資料更新使用 Python 3.11+ 標準函式庫。

現有網站：https://kawai2342006.github.io/LokiRS/

## v1.3.2 — 2026-11-06 美股核對

同一交易日對比 LazyRS 591 筆公開排名，LokiRS 589 股之中 588 股可排名。五時段權重毋須修改；修補 10 隻股票已核實派息但 Yahoo 調整價暫缺的日線。共同股票的平均分數差距由 0.01827 減至 0.01226，平均名次差距由 1.91 減至 1.01。完整結果、來源與安裝方式見 [README_NOV06_DIVIDENDS.md](README_NOV06_DIVIDENDS.md)，逐股差異見 [reports/comparison-2026-11-06.csv](reports/comparison-2026-11-06.csv)。

## v1.3.1 日期與發佈修正

修正跨日報價與排名基準不一致，新增日線完整性及寫出前驗證。11 月 4 日公式覆核與安裝方式見 [README_NOV04_FIX.md](README_NOV04_FIX.md)。

## v1.3 美股排名校準

美股綜合分數改為 1H／4H／1D／5D／20D 五時段權重，已用兩日公開快照與獨立行情核對。安裝、更新及比較命令見 [README_CALIBRATION.md](README_CALIBRATION.md)，完整結果見 [校準紀錄](docs/CALIBRATION.md)。

## v1.2 主頁更新

詳細安裝與更新步驟見 [README_HOME.md](README_HOME.md)。更新包的預設入口是跨市場主頁，原有美股排名、自選及走勢比較保留。

可先開啟 `preview/LokiRS_Home_Preview.html` 看離線效果，再將更新檔案上傳到現有 repository 根目錄。`preview/` 不需要發布。網站字體已自託管，`assets/fonts/` 必須一併上傳。

## 功能

- 六項市場快照、規則摘要、市場寬度、VIX、Crypto 市值及 RS Pulse。
- 32 項跨市場資產的相對強弱、五日輪動、分類搜尋、排序與 CSV 匯出。
- 穩定幣供應、BTC 市佔、港股通南向淨買入。
- 589 隻美股及 37 個板塊 ETF 對照、多時段超額、Top 10、長線 RS 與持續日數。
- 裝置本機自選、最多 10 隻股票／跨市場資產比較、SVG 匯出。
- 紙紋／純色閱讀模式、原有設定相容、手機響應式版面及鍵盤搜尋。

## 本機執行

```bash
python scripts/serve.py
# 開啟 http://localhost:5173
```

正式網站入口需要 HTTP 服務；專用離線預覽檔可以直接開啟。

```bash
python scripts/update_home.py   # 只更新首頁
python scripts/update_data.py   # 更新美股，然後更新首頁
python scripts/build.py         # 輸出到 _site/
```

GitHub 更新工作流程隨新版提供，設定方法見 README_HOME。頁面上的更新／自動檢查只重讀已發布的檔案。

## 驗證

```bash
python -m unittest discover -s tests -v
node --test tests/charts.test.js
node --check assets/app.js
node --check assets/home.js
python scripts/build.py
```

當次另完成 40 項模擬 DOM 互動檢查；真實瀏覽器與手機視覺驗收受預覽環境限制而未完成。

[主頁來源及公式](docs/HOME_REFERENCE_MAP.md) · [主頁驗證](docs/HOME_VALIDATION.md) · [Loki Archive 設計規格](docs/LOKI_THEME.md)

LokiRS 延續原 OpenRS 的公開替代公式；原站完整 LazyRS 權重未經核實。本站排名可能與原頁不同。行情、股票池、指標及來源限制另見網頁「計算方法」與原有 [數據驗證](docs/VALIDATION.md)。

程式碼 MIT；行情內容與字體依各自來源授權。字體授權附於 `assets/fonts/`。
