# LokiRS — 相對強弱情報局

以免費行情獨立計算的美股相對強弱儀表板，採用 **Loki Archive** 視覺主題。可部署於 GitHub Pages，使用原生 HTML、CSS、JavaScript 與 Python，沒有前端框架或付費 API 依賴。

現有網站：https://kawai2342006.github.io/LokiRS/

## 套用本次主題更新

將主題更新包內的 `index.html`、`assets/` 及其餘同名檔案，上傳至現有 repository 的根目錄並覆蓋；請保留資料夾層級。沿用現有 GitHub Pages 發佈設定，等待原有發佈流程完成後重新整理網站。

`assets/fonts/` 包含網站所需的 Noto Serif TC、Noto Sans TC 和 IBM Plex Mono 字體，必須一併上傳。字體已自託管，頁面不需要連線 Google Fonts。

這次更新集中於外觀、品牌及瀏覽器儲存相容性。更新包不包含 `data/`、`config/` 或抓價／計算程式，因此可直接套用而保留倉庫中較新的行情與參數。既有資料更新及部署設定沿用原本的版本。

詳細更新說明：[README_THEME.md](README_THEME.md)。

## 功能

- 589 隻美股及 37 個板塊 ETF 對照，包含 SPY 基準。
- 多時段相對回報、LokiRS 綜合分數、強弱 Top 10、排名變動、長線 RS、持續日數與板塊比較。
- 搜尋、板塊及數值篩選、排序、分頁、裝置本機自選、最多 10 隻走勢比較。
- 市場寬度、FRED 流動性與金融狀況；可選來源無法取得時保留缺值。
- CSV 及 SVG 匯出、鍵盤搜尋快捷鍵、響應式版面。
- 檔案紙紋／純色閱讀模式。兩種模式都保留深綠與黃銅配色。

## 主題

主背景 `#091b14`、深層 `#07130f`、暖紙白 `#f0e6cb`、舊黃銅 `#cdb477`、TVA 橙 `#dba15d`。

磷光綠 `#8ddd9b` 與暖珊瑚 `#f18a73` 用於正負數據。比較圖以黃銅、紙白、檔案橙、灰綠及不同線型標識資產。

標題使用 Noto Serif TC，正文使用 Noto Sans TC，數據及股票代號使用 IBM Plex Mono。字體附 SIL Open Font License 授權；目前中文字體是涵蓋現有 UI 的子集，新增字元會由系統字體補足。

[設計規格](docs/LOKI_THEME.md) · [原始風格 Prompt](docs/LOKI_STYLE_REFERENCE.md) · [主題驗證](docs/LOKI_THEME_VALIDATION.md)

## 計算及資料

LokiRS 延續原 OpenRS 的開放公式：

```text
超額回報（百分點） = 100 × [(個股結束價 / 起始價 − 1) − (SPY 結束價 / 起始價 − 1)]
LokiRS = 0.5 × 超額 1D + 0.3 × 超額 5D + 0.2 × 超額 20D
長線值 = 0.4 × 超額 63D + 0.2 × 超額 126D + 0.2 × 超額 189D + 0.2 × 超額 252D
vs 板塊 = 個股 LokiRS − ETF LokiRS
```

這是獨立近似重建；原站 LazyRS 的完整權重、長線公式及封存排名未經核實。名稱更新不改變數學公式、歷史行情或資料格式。完整價格口徑、時間錨點及資料限制，見網頁「計算方法」、[原始欄位對照](docs/REFERENCE_MAP.md) 及 [原始數據驗證](docs/VALIDATION.md)。

網頁的更新按鈕只重讀已發佈的 JSON；抓價仍由原本的 GitHub 工作流程或以下本機指令執行：

```bash
python scripts/update_data.py
```

## 本機預覽與驗證

需要 Python 3.11+，網站本身無第三方套件依賴。

```bash
python scripts/serve.py
# 開啟 http://localhost:5173
```

不要直接雙擊正式 `index.html`，因為 JavaScript modules 及 JSON 讀取需要 HTTP 服務。附帶的 `LokiRS_Preview.html` 是特別打包的離線快照，可以直接開啟；它不會抓取新行情。

```bash
python -m unittest discover -s tests -v
node --test tests/charts.test.js
node --check assets/app.js
python scripts/build.py
```

建置輸出為 `_site/`，可交給現有靜態部署流程。所有網站資源均採相對路徑，可放在 `/LokiRS/` 子路徑。

程式碼採 MIT 授權。行情內容及附帶字體依各自來源授權。
