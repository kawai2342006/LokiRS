# LokiRS v1.2 — 跨市場情報主頁更新

## 上傳到現有 LokiRS

1. 解壓 `LokiRS_Home_Update.zip`。
2. 可先直接開啟 `preview/LokiRS_Home_Preview.html`，查看離線版本；內附快照，不會抓取新行情。
3. 將更新包中的檔案與資料夾上傳到現有 `kawai2342006/LokiRS` 根目錄，覆蓋同名檔案；不要多包一層目錄。`index.html` 應直接位於倉庫根目錄。
4. 必須完整包含 `assets/`、`data/home.json`、`config/home_markets.json` 及 `scripts/` 內的更新檔案。`preview/` 可留在本機。
5. 沿用現有 GitHub Pages 發佈流程，完成後重新整理。這個更新包沒有推送或部署到你的 GitHub。

更新包不包含 `data/latest.json`、`config/universe.json` 或 `config/settings.json`，因此不會覆蓋倉庫中較新的美股行情、股票池及原有權重。

## 首頁內容

- 預設 `/LokiRS/` 開啟新首頁；美股、自選及比較由上方分頁進入。
- 六項完整日線快照：SPY、QQQ、BTC、UUP、GLD、USO。
- 規則生成的行情重點：美股寬度、VIX、Crypto 市值、跨市場最強及五日輪動。
- RS Pulse：突然走強、持續領先、走弱警示；目前以既有 589 股美股股票池計算。
- 美元穩定幣供應與 7／30 日變化、BTC 市佔率、南向淨買入及近五個港股交易日合計。
- 32 項資產的中位數比較、1D／5D／20D／60D 超額、五日排名變化及 21 日 RS 線。
- 跨市場搜尋、分類、排序、CSV 匯出、TradingView 代號複製、個別資產詳情及加入原有走勢比較。
- 公開文章標題及原文連結、LokiRS 使用說明與公開公式。
- 沿用深綠、黃銅、襯線標題、等寬數字及檔案紙紋／閱讀模式。

直接連結例子：`?tab=stocks`、`?tab=watchlist`、`?tab=compare`、`?tab=stocks&s=NVDA`。瀏覽器上一頁／下一頁可切換分頁。

## 更新資料

只更新首頁，使用現有美股快照產生異動：

```bash
python scripts/update_home.py
```

更新美股後連同首頁更新：

```bash
python scripts/update_data.py
```

主頁每 60 秒的「自動檢查」只重讀已發布 JSON，不會讓 GitHub Pages 自己抓價。可以暫停，自選與主題設定繼續保存在原本瀏覽器。

本次補齊 GitHub Actions 工作流程 `Update data and deploy Pages`，預設星期一至五 22:17 UTC（香港翌日 06:17）抓價、測試並部署。若要使用，請完整上傳工作流程資料夾，並在 repository 的 Pages 發佈來源選擇 GitHub Actions。上傳後仍需在 GitHub 自己確認首次工作流程成功；本次未在遠端執行它。

若保留現有分支式發佈而不使用這份工作流程，可本機執行上面的更新命令，再提交更新的 `data/`。免費端點及 GitHub 排程都可能延遲或失敗，頁面保留觀測日期與缺值狀態。

## 公式與範圍差異

```text
各時段超額 = 資產回報 − 同期有效資產回報中位數
主頁 LokiRS = 0.5 × 超額 1D + 0.3 × 超額 5D + 0.2 × 超額 20D
Δ5D = 五個 SPY 交易日前名次 − 本日名次
```

原站完整權重、歷史排名及異動選股規則未公開核實。這裡採可查核的替代公式與固定 32 項資產池，因此分數、排名及部分回報不保證與原頁一致。不是把原站數字當作本站行情來源。

表格期間統一以 SPY 的相同交易日期作錨點，缺起訖日不填補；不同市場收市時間仍不同。行情卡則採每項資產自己的最近完整日線，BTC 卡的 5D 是五個 UTC 完整日，因此卡片與跨市場表的時點可能不同。

市場異動目前沒有加入完整港股股票池。原站文章 RSS 今次未返回有效資料，因此使用其公開首頁的六項標題快照並標示狀態，只連到原文，不複製文章內容。會員功能、推廣廣告及第三方社群招募沒有加入。

[欄位及來源對照](docs/HOME_REFERENCE_MAP.md) · [驗證與限制](docs/HOME_VALIDATION.md)
