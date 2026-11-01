# LOKI TYPEFACE STYLE — 可移植設計規格 + AI Prompt

> 來源：Mobius「TVA 財經日報」v2.0.0 `THE VARIANT ARCHIVE`（`tvazette_render.py`），2026-10-28 核准。
> 用途：把同一套視覺語言套用到任何專案（網站、簡報、報告、卡片、dashboard）。以下分「規格」＋「可直接貼的 Prompt」兩部分。

---

## A. 規格（Design tokens）

### A1. 色彩（顏色有語義，唔可以亂用）

```
PAGE_BG  #091b14   黑松綠（主背景）
INK      #f0e6cb   暖紙白（主要文字）
MUT      #a5b1a1   灰綠（次要文字）
GOLD     #cdb477   舊黃銅（結構線、標籤、印章 —— 唔係螢光金）
AMBER    #dba15d   TVA 檔案橙（機密標籤、警示帶、索引號）
UP       #8ddd9b   磷光綠 —— 只可以代表「上升 / 正面數據」
DOWN     #f18a73   暖珊瑚 —— 只可以代表「下跌 / 風險」
LINE     rgba(205,180,119,.31)   銅色主分隔線
LINE_SOFT rgba(205,180,119,.16)  銅色細分隔線
```
規則：
- 綠／珊瑚**只**用於數據語義，唔可以做裝飾色。
- 結構（框、分隔線、標籤、印章）一律黃銅系（GOLD / AMBER / LINE）。
- 大面積底色只可以係 PAGE_BG 或比佢更深嘅 `#07130f` / `#030a07`；**唔用純黑**。

### A2. 字體（三套，各有分工）

```
標題 / 引文   Noto Serif TC 700–900（襯線，中文報頭感）
內文         Noto Sans TC 400–700
數據 / 代號   IBM Plex Mono 400–600，font-variant-numeric: tabular-nums
Latin fallback: Georgia / Arial / Courier New
```
數字**一律** mono + `tnum`（等寬對齊），唔可以用比例字體排價格／百分比。

### A3. 字級階梯（以 600px 頁寬計）

```
報頭 wordmark   47–50px（letter-spacing:-6px，襯線斜體 V）
報頭紙名        29px / 900 / letter-spacing:3px
主標題 h2       31px / 900 / line-height:1.5
欄目標題        15px / 900 / letter-spacing:1px（上 2px 銅線、下 1px 銅線）
引文 editorial  15px / 700 / line-height:1.95
新聞小標 h4     14px / 700 / line-height:1.7
卡片價格        15.5px / 600 / letter-spacing:-.75px
內文            10–12px / line-height:1.85–1.9
數據細項        9–10px / mono
檔案標籤        7–8.5px / mono / letter-spacing:1–2.8px（全大寫或全中文）
```

### A4. 版面骨架

```
頁寬 600 CSS px，輸出 2x（1200px 實體），高度自適應內容
頁邊距 20px 24px 16px；外框 1px solid LINE
欄網格：主文 1fr / 側欄 1.04fr，gap 16px（側欄用左側銅線 + 14px padding 分隔）
卡片網格：2 欄，gap 8–13px
所有卡片：border:1px solid LINE，底色 rgba 疊加（例 #04110c88），細圓角 0（**硬直角**，唔用圓角）
```

### A5. 質感層（三層疊加，缺一層就唔似）

```css
background:
  radial-gradient(ellipse at 88% 0%, rgba(54,104,58,.15), transparent 44%),   /* 角落松綠光 */
  repeating-linear-gradient(0deg, rgba(219,209,164,.018) 0 1px, transparent 1px 4px),  /* 4px 掃描線 */
  linear-gradient(155deg, #091b14, #07130f 76%);                              /* 主漸層 */
box-shadow: 0 18px 60px #0007;                                                /* 紙張浮起 */
```
另外：內縮 10px 再畫一層細銅線（左右兩邊），四角加 12px 銅色 tick —— 呢個係「檔案館文件」感嘅關鍵。

### A6. 必備裝飾元件（Ornament）

1. **檔案列**（`archive-line`）：頁頂 `TVA / CLASSIFIED · ARCHIVE` 左，日期右，8px mono，字距 1.35px，底部 1px 銅線；左邊一個 5×5 銅色方塊做 classification 標記。
2. **雙線銅規**（`border-bottom:3px double GOLD`）：報頭、迷你報頭、區塊標題都用，報紙排版語言。
3. **皇冠／時間線 SVG**：純線稿，`stroke-width:.75`，opacity .32 的同心圓 + 軸線做底，實色部分只有 3 個幾何塊。唔用點陣圖、唔用 emoji、唔用漸變填色。
4. **圓形印章**（`seal`）：50px，1px 銅圈，內圈 `1px dashed` 銅線 + `rotate(-9deg) scale(.80)`，6px mono 文字。
5. **檔案頁籤**（`file-tab`）：銅底 + 深字（`#102218`）+ 8px mono，貼住 kicker 左邊。
6. **條紋警示帶**（`alert`）：`repeating-linear-gradient(135deg, AMBER 7% 0 3px, transparent 3px 8px)`，1px `#dba15d77` 邊框，左邊 70px 標籤欄（襯線 13px）。
7. **檔案編號**：每張卡左上 `VARIANT FILE / 03`（7px mono，字距 1.5px），右下 7×7 銅色小三角。
8. **頁腳**：`pageno` 左頁碼右代號，8px mono，頂部 1px 銅線，全大寫 + 字距。

### A7. 鐵律（唔可以破）

1. **圖片內唔用 emoji**（headless 渲染會出豆腐格）→ 用文字徽章（`01/02/03`）、色塊、或 mono 符號。
2. **任何文字唔可以壓線／出界**：所有文字容器要 `overflow-wrap:anywhere` 或 `nowrap` + `min-width:0`；同一行嘅 flex 用 `nowrap`，唔好靠 `wrap` 補位（會令對齊走位）。
3. **顏色語義唔可以倒轉**（綠=升、珊瑚=跌）；如果主題本身有品牌色，只能換 PAGE_BG / GOLD / AMBER，UP／DOWN 必須保留冷暖對比。
4. **對比度**：INK on PAGE_BG ≥ 7:1；MUT 只用於 ≤10px 輔助字，唔可以用嚟排主要數據。
5. **裝飾唔可以覆蓋正文**：所有 ornament 走 gutter（`z-index:-1`）或獨立欄位。
6. 頁數固定、高度可變；內容多就加長，**唔可以縮字**。

---

## B. 可直接貼的 Prompt（給任何 AI／專案用）

```
你要為我設計【<專案名 / 頁面 / 卡片>】，套用一套叫「Loki Archive」的視覺語言。
呢套語言來自一份虛構情報機構的財經日報，特徵係：黑松綠紙、舊黃銅線、襯線報頭、
等寬數字、檔案館蓋章感。以下係硬性規格，唔可以自由發揮：

【色彩 —— 有語義，唔可以亂用】
- 主背景 #091b14（黑松綠），深層 #07130f，最底 #030a07（唔用純黑）
- 主文字 #f0e6cb（暖紙白）｜次要文字 #a5b1a1（灰綠）
- 結構線／標籤／印章 #cdb477（舊黃銅）｜檔案標籤 #dba15d（TVA 橙）
- 上升／正面 #8ddd9b（磷光綠）｜下跌／風險 #f18a73（暖珊瑚）
- 主分隔線 rgba(205,180,119,.31)，細線 rgba(205,180,119,.16)
- 綠同珊瑚**只**用於數據語義；結構一律黃銅系；唔可以用鮮藍、鮮紫、純白大面積。

【字體】
- 標題／引文：Noto Serif TC 700–900
- 內文：Noto Sans TC 400–700
- 數字／代號：IBM Plex Mono 400–600 + font-variant-numeric: tabular-nums
- 所有價格、百分比、代號一律 mono 等寬對齊

【版面】
- 頁寬 600px（輸出 2x），邊距 20/24/16，外框 1px 銅線
- 硬直角，唔用圓角；卡片 border 1px 銅線 + 半透明深底（例 #04110c88）
- 主文 / 側欄 1fr : 1.04fr，gap 16px；卡片 2 欄，gap 8–13px
- 字級：報頭 47px／主標 31px／欄目標題 15px／卡片數字 15.5px／內文 10–12px／標籤 7–8.5px

【質感（三層疊加，缺一層就唔似）】
radial-gradient(ellipse at 88% 0%, rgba(54,104,58,.15), transparent 44%)
+ repeating-linear-gradient(0deg, rgba(219,209,164,.018) 0 1px, transparent 1px 4px)
+ linear-gradient(155deg, #091b14, #07130f 76%)，再加 box-shadow: 0 18px 60px #0007
另外內縮 10px 畫一層細銅線（左右），四角 12px 銅色 tick。

【必備元件】
1. 頁頂檔案列：8px mono 全大寫、字距 1.35px、左邊 5×5 銅方塊、底部 1px 銅線
2. 報頭用 3px double 銅線；區塊標題同樣「上 2px 銅線、下 1px 銅線」
3. 純線稿 SVG ornament：同心圓 opacity .32 + 極細 stroke(.75)，實色只用幾何塊
4. 圓形印章：50px 銅圈，內圈 dashed + rotate(-9deg) scale(.8)，6px mono 字
5. 警示帶：repeating-linear-gradient(135deg, #dba15d 7% 0 3px, transparent 3px 8px)，左邊 70px 襯線標籤
6. 每張卡：左上 7px mono 檔案編號（FILE / 01），右下 7×7 銅色小三角
7. 頁腳：8px mono，左頁碼右代號，頂部 1px 銅線

【鐵律】
1. 圖片內唔用 emoji（用 01/02/03 徽章、色塊或 mono 符號）
2. 任何文字唔可以壓線／出界；flex 用 nowrap + min-width:0，唔靠 wrap 補位
3. 綠=升、珊瑚=跌，唔可以倒轉；只可以換底色／黃銅色去配品牌
4. 主文字對比 ≥7:1；MUT 只排 ≤10px 輔助字
5. 裝飾走 gutter（z-index:-1）或獨立欄，唔覆蓋正文
6. 內容多就加長版面，唔可以縮字

【內容語氣】
冷靜、檔案館式、帶情報機構的克制幽默；標題用襯線重字，數據用等寬字；
短標籤全大寫＋字距；唔用感嘆號、唔用 emoji、唔用可愛風。

輸出要求：<HTML/CSS 可直接 render，或 React/Tailwind 對應 class>
所有色值用上面 hex，唔好自己調；完成後自我檢查有冇文字溢出、對比不足、圓角殘留。
```

---

## C. 一頁速查（Cheat sheet）

```
底色    #091b14 / #07130f / #030a07
字色    #f0e6cb  次 #a5b1a1
銅線    #cdb477 (0.31 / 0.16 alpha)
標籤    #dba15d
升      #8ddd9b   跌 #f18a73
字體    Serif=標題 / Sans=內文 / Mono=數字
結構    1px 銅框、硬直角、3px double 報頭線
質感    角落松綠光 + 4px 掃描線 + 深漸層 + 紙影
裝飾    檔案列、印章、雙線、檔案編號、頁腳 mono
禁止    emoji 入圖、圓角、鮮色裝飾、縮字塞內容
```
