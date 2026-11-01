# LokiRS v1.2.1 — 恐懼與貪婪來源更新

美股排名中的「恐懼與貪婪」現在先讀取 [MacroMicro 轉載的 CNN 指數](https://en.macromicro.me/charts/50108/cnn-fear-and-greed)，CNN 公開端點為後備。

此更新已在本機完成，未推送或部署到你的 GitHub。

## 上傳

1. 解壓縮 `LokiRS_Sentiment_Update.zip`。
2. 將更新包內的檔案與資料夾上傳到現有 `kawai2342006/LokiRS` 根目錄，覆蓋同名檔案。`index.html` 直接放在根目錄，不要再包一層資料夾。
3. 必須包含新的 `assets/sentiment.js`、`data/sentiment.json` 及 `scripts/` 內各更新檔案。
4. 沿用目前 GitHub Pages 發佈方式，完成後重新整理頁面。離線預覽 `preview/LokiRS_Sentiment_Preview.html` 可直接開啟，預設顯示美股排名；此預覽不需要上傳。

這是現有專案的增量更新包。它不包含 `data/latest.json`、`data/home.json` 或股票池設定檔，不會覆蓋倉庫中較新的股價及主頁行情。預覽則內嵌固定快照，供離線檢視。

## 數據及日期

- 本次附帶的 CNN 指數為 **26.2387**，畫面顯示 **26.24 · 恐懼**，觀測日期 **2026-10-30**。
- MacroMicro 公開頁面最近兩筆：2026-10-29 為 30.7672、2026-10-30 為 26.2387。欄位標示「上一筆」，不將它冒稱 CNN 官方「前收」。
- 來源標示「MacroMicro（轉載 CNN）」，連結指向指定頁面。此來源不是 MacroMicro 自有的恐懼貪婪指數，也不是加密市場情緒指數。
- 來源僅提供日期，因此畫面不會補上不存在的時間。更新檢查時間與觀測日期分開保存。
- 一週前／一月前只使用來源提供或已累積的同來源真實觀測值；初次啟用時這兩項保留「—」。目標日休市時最多採用前三個曆日的既有觀測，滑鼠提示會列實際日期。
- 所有來源失敗時保留上次有效數值及原日期，標示「舊值」。超過七個曆日的快照亦會顯示舊值；缺值不會變成 0 或自行合成。

## 更新資料

只更新這個情緒指數，不需重新下載全部股票：

```bash
python3 scripts/update_sentiment.py
```

一般整批更新亦已整合此來源：

```bash
python3 scripts/update_data.py
```

兩者都會更新獨立的 `data/sentiment.json`。前端會與股價快照內的情緒資料比較觀測日期，採用較新的有效資料。網站「檢查更新」只重讀已發佈快照；GitHub Pages 本身不直接抓取來源。

更新包亦附上先前提供的 `.github/workflows/pages.yml`，已加入保存 `data/sentiment.json`。若你使用這份 GitHub Actions 工作流程，請一併上傳完整 `.github/` 資料夾，Pages 來源選擇 GitHub Actions。使用分支式 Pages 的話可沿用原設定，本機更新後提交 `data/sentiment.json` 即可。

## 驗證

標準函式庫測試涵蓋 CNN 序列辨認、資料日期、有效範圍、後備來源、同來源歷史及更新失敗保留原值。已通過 Python 測試與現有圖表測試，並以 DOM 模擬驗證完整頁面的情緒欄、主頁、589 股排名、自選和比較功能。離線預覽已驗證不會發出行情網路請求；尚未進行實際瀏覽器的桌面／手機視覺檢查。

```bash
python3 -m unittest discover -s tests -v
node --test tests/charts.test.js
python3 scripts/build.py
```
