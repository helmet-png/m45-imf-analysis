# -*- coding: utf-8 -*-
"""主控板的「階段 → 步驟 → 腳本」靜態索引，手動維護（見
status_dashboard/app.py 檔頭說明：為什麼這塊沒辦法自動生成）。

每筆 script 路徑相對於 m45_membership repo 根目錄（不是這個檔案所在的
status_dashboard/ 目錄）。`queue_labels`（可選）是這個步驟對應到
cloud_queue.txt／queue.txt 裡的實際標籤，用來對到執行紀錄——沒填就代表
這個步驟目前不是透過佇列系統跑的單一標籤（例如手動跑、或是文件查證類
工作），主控板只會顯示腳本說明，不會顯示執行狀態列。

**新增 WORK_BOARD.md 任務或新腳本時，記得回來這裡加一筆**——這是
CONTRIBUTING.md 裡「新結果要記進 RESULTS_LOG.md」同一種「找不到自動生成
辦法、只能手動維護索引」的協作規則，不是遺漏。

---

## 每個步驟可以填的欄位（2026-08-26 擴充，為了科展解說）

必填：
  `name`         步驟名稱
選填：
  `scripts`      這一步用到的程式，路徑相對 repo 根目錄
  `queue_labels` 對應 cloud_queue.txt／queue.txt 的實際標籤（顯示執行狀態）
  `note`         一句話補充
  `external`     {腳本路徑: 上游網址}，標記「第三方套件，本 repo 不夾帶
                 原始碼」（見 .gitignore「第三方原始碼」那段）。標了之後
                 找不到檔案會顯示成正常情況＋上游連結，不會誤報成路徑壞掉
  `key_points`   這一步最該先看懂的兩三句話（人工挑，不是自動摘要）
  `formula`      [{expr, where, source}]，這一步真正在算的數學式
  `refs`         [{cite, role, arxiv?}]，這個做法的文獻出處
  `core`         {file, line, name, why}，這一步最核心的那個函式

**`refs` 的內容一律抄自專案自己已經核對過的兩張文獻對照表**
（`docs/teaching/教學_傳統法誤差核算.md` 第十節、
`docs/teaching/教學_前向模型.md` 第十節）——那兩張表是有人真的讀過原文
才寫下來的。**不要在這裡自己加沒查證過的文獻**：這份資料會被拿去科展
解說，掛一個沒讀過的引用比不掛還糟。要新增就先去讀原文、補進那兩張
對照表，再抄過來。

`formula` 的 `expr` 用純文字數學式，不是 LaTeX——主控板刻意不載入
MathJax 之類的外部函式庫（零外部依賴，見 app.py 檔頭設計原則），這樣
在科展現場離線開也一定看得到。
"""
from __future__ import annotations

# 本專案自己的教學／參考文件路徑，給 refs 的 doc 欄位用（點進去會落在
# GitHub 上對應的行）。抽成常數是因為同一份文件會被很多筆文獻引用，
# 檔名之後若搬動只要改這裡一處。
TRAD = "docs/teaching/教學_傳統法誤差核算.md"
FWD = "docs/teaching/教學_前向模型.md"
MET = "docs/reference/METHODS.md"

STAGES = [
    {
        "name": "傳統法",
        "steps": [
            {
                "name": "質量指定 + MLE 冪次律擬合（5 個二元星修正變體）",
                "scripts": [
                    "pipeline/step5_imf.py",
                    "scripts/diagnostics/traditional_accounting.py",
                ],
                "key_points": [
                    "**要回答的問題**：星團裡「輕的星」跟「重的星」數量比例是多少？"
                    "==重星永遠比輕星少，我們要量的就是「少得多快」這個速率==，"
                    "這個數字叫 alpha。",
                    "**這一支的做法（也是天文界最傳統的做法）**：先量每顆星有多亮，"
                    "查赫羅圖（等時線）換算成質量，得到 1,078 顆星的質量清單，"
                    "再問「什麼樣的 alpha 最能解釋這串數字」。",
                    "⚠️ **這個做法有個先天問題**：望遠鏡看到的一個亮點，"
                    "可能其實是**兩顆星靠得太近、分不開**（叫「未解析雙星」）。"
                    "兩顆星的光加起來比較亮，就會被誤判成「一顆很重的星」。"
                    "==結果就是重星被高估、alpha 被算得偏小==。"
                    "旁邊那一支「前向模型」就是為了繞開這個問題才做的。",
                    "**本專案的貢獻**：把天文界處理雙星的 5 種主流做法"
                    "（乾脆全當單星／用赫羅圖位置剔除／用 Gaia 的 RUWE 指標剔除／"
                    "用 Gaia 官方雙星目錄剔除／直接套文獻公式修正）"
                    "==放在同一組資料、同一把尺上比較==，這張比較表是本專案"
                    "自己做的，不是照抄文獻。",
                ],
                "prereq": [
                    "**質量函數（Mass Function）**：一個描述「不同質量的星各有幾顆」"
                    "的數學式。就像班上身高分布可以畫成一條曲線，"
                    "星團的質量也可以。",
                    "**冪次律（power law）**：形如 y = x^(-a) 的關係。"
                    "高一數學的指數函數，只是這裡指數是負的（所以 x 越大 y 越小）。",
                    "**最大概似估計（MLE）**：一種找答案的方法——"
                    "==「哪一個 alpha，會讓我們實際看到這 1,078 顆星的機率最大？"
                    "那個就是最佳答案」==。概念上跟「猜一個最合理的解釋」一樣，"
                    "只是用機率把「合理」量化。",
                ],
                "formula": [
                    {
                        "expr": "dN/dm  ∝  m^(-alpha)",
                        "plain": "==「質量每變大一點，星的數量就掉得多快」==。"
                                 "alpha 越大代表重星掉得越兇（重星特別稀少）；"
                                 "alpha 越小代表重星沒那麼稀少。"
                                 "**這條式子裡的 alpha 就是整個專案要量的那個數字。**",
                        "meaning": "`dN/dm` 讀作「每單位質量區間內的星數」——"
                                   "例如「質量在 1.0～1.1 個太陽之間有幾顆星」。"
                                   "`∝` 是「正比於」。Salpeter 在 1955 年量到 2.35，"
                                   "這個值到今天仍是標準對照值，也是本專案"
                                   "測試自己程式對不對時採用的「正確答案」。",
                        "source": "Salpeter (1955)",
                    },
                    {
                        "expr": "C    = (1-alpha) / ( m_hi^(1-alpha) - m_lo^(1-alpha) )\n"
                                "lnL  = n · ln(C)  -  alpha · Σ ln(m_i)",
                        "plain": "==把「這組 alpha 有多符合觀測資料」算成一個分數==，"
                                 "然後用電腦去試不同的 alpha，找出分數最高的那個。"
                                 "分數就是 lnL，越大代表越吻合。",
                        "meaning": "`C` 的作用是**歸一化**：我們只看得到質量介於 "
                                   "m_lo 到 m_hi 之間的星（太暗的看不見、太亮的很少），"
                                   "所以要把冪次律在這段區間內的總機率調整成 1，"
                                   "`C` 就是那個調整係數。"
                                   "`Σ ln(m_i)` 是把每顆星的質量取對數後全部加起來"
                                   "——==有趣的是，1,078 顆星的資料最後只透過這一個"
                                   "數字影響答案==。",
                        "inputs": "1,078 顆星各自的質量 m_i、質量範圍上下限 "
                                  "m_lo = 0.50、m_hi = 2.50（單位是太陽質量）",
                        "outputs": "最佳的 alpha，以及它的誤差範圍",
                        "source": "`pipeline/step5_imf.py` 的 `mle_powerlaw()`；"
                                  "完整推導見 `docs/teaching/教學_傳統法誤差核算.md`",
                    },
                    {
                        "expr": "F        = 10^(-0.4 · m)            （星等 → 亮度）\n"
                                "Δm       = -2.5 · log10(2)  ≈  -0.753",
                        "plain": "==兩顆一模一樣的星疊在一起，看起來會亮 0.753 星等==。"
                                 "這就是「用赫羅圖位置剔除雙星」那個做法的判斷依據："
                                 "如果一顆星比主序帶高出約 0.75 星等，它很可能其實是兩顆。",
                        "meaning": "地科學過「星等越小越亮，差 5 等亮度差 100 倍」，"
                                   "寫成數學就是第一條式子。兩顆一樣亮的星加起來亮度變 2 倍，"
                                   "代入後得到 -2.5·log10(2) ≈ -0.753 —— "
                                   "負號代表變亮。**這裡只用到高一的對數運算**。",
                        "inputs": "星等 m",
                        "outputs": "等質量雙星在赫羅圖上會往上偏移的量（0.753 星等）",
                        "source": "星等定義 m = -2.5·log10(F) 的直接推論",
                    },
                ],
                "refs": [
                    {"cite": "Salpeter (1955), ApJ 121, 161",
                     "bibstem": "ApJ", "volume": "121", "page": "161", "year": "1955",
                     "doc": TRAD, "doc_line": 727,
                     "role": "alpha = 2.35 的來源，注入回收的真值"},
                    {"cite": "Kroupa (2001), MNRAS 322, 231",
                     "bibstem": "MNRAS", "volume": "322", "page": "231", "year": "2001",
                     "doc": TRAD, "doc_line": 728,
                     "role": "分段冪律（0.3／1.3／2.3 三段），低質量段的定義"},
                    {"cite": "Rosen (2026), arXiv:2603.15779", "arxiv": "2603.15779",
                     "doc": TRAD, "doc_line": 729,
                     "role": "忽略雙星造成的偏差量級（光度相加 −0.011～−0.021），"
                             "**文獻解析修正法**的修正量來源"},
                    {"cite": "Cordoni et al. (2023), A&A 672, A29",
                     "bibstem": "A&A", "volume": "672", "page": "A29", "year": "2023",
                     "doc": TRAD, "doc_line": 730,
                     "role": "78 個疏散星團的光度雙星與質量函數；"
                             "**CMD 偏移剔除法**的方法論依據"},
                    {"cite": "Mikhnevich et al. (2026), arXiv:2604.20722",
                     "arxiv": "2604.20722",
                     "doc": TRAD, "doc_line": 731,
                     "role": "含 M45 本身的八個星團、光度雙星判定；"
                             "CMD 剔除法的另一個方法論依據"},
                    {"cite": "Lindegren et al. (2021), A&A 649, A2",
                     "bibstem": "A&A", "volume": "649", "page": "A2", "year": "2021",
                     "doc": TRAD, "doc_line": 732,
                     "role": "RUWE 的定義，**RUWE 剔除法**的依據"},
                    {"cite": "Gaia Collaboration, Arenou et al. (2023), A&A 674, A34",
                     "bibstem": "A&A", "volume": "674", "page": "A34", "year": "2023",
                     "doc": TRAD, "doc_line": 733,
                     "role": "Gaia NSS 目錄的處理鏈，**Gaia NSS 剔除法**的依據"},
                    {"cite": "Maíz Apellániz (2008), ApJ 677, 1278",
                     "bibstem": "ApJ", "volume": "677", "page": "1278", "year": "2008",
                     "doc": TRAD, "doc_line": 734,
                     "role": "族群層級解析修正法的經典先例"},
                ],
                "core": {
                    "file": "pipeline/step5_imf.py", "line": 127,
                    "name": "mle_powerlaw()",
                    "why": "傳統法的心臟。輸入是一串已經指派好的恆星質量，"
                           "輸出是 alpha 與它的標準誤。上面第二條公式就是"
                           "這個函式裡的 `neg_ll()` 在算的東西——"
                           "整個傳統法路線最後都收斂到這十幾行。",
                },
            },
        ],
    },
    {
        "name": "前向模型（5 步，對應 config.toml 的 [step1_membership]…[step5_imf]）",
        "steps": [
            {
                "name": "Step1 成員資格判定（pyUPMASK）",
                "scripts": [
                    "scripts/data_prep/fetch_gaia.py",
                    "scripts/data_prep/prep.py",
                    "pyUPMASK/pyUPMASK.py",
                    "scripts/drivers/run_variant.py",
                ],
                # pyUPMASK 是第三方套件，依 .gitignore「第三方原始碼：用
                # clone 取得，不納入本 repo」的規定不夾帶對方的程式碼。
                # 標了 external 之後，本機沒 clone 時會顯示成正常情況＋
                # 上游連結，不會再誤報成「路徑可能已經搬動」（2026-08-26）。
                "external": {
                    "pyUPMASK/pyUPMASK.py": "https://github.com/msolpera/pyUPMASK",
                },
                "key_points": [
                    "==目標：從 6,956 顆候選星裡挑出真正屬於 M45 的成員==。"
                    "判準是天測——自行（proper motion）與視差（parallax），"
                    "**不看亮度也不看顏色**，這一點很關鍵：後面要拿 CMD"
                    "（顏色-亮度圖）去擬合質量函數，如果成員判定本身就用了"
                    "顏色資訊，等於先偷看答案再考試。",
                    "pyUPMASK 的作法是**無監督分群**：在自行＋視差構成的空間裡"
                    "找出比背景場星更集中的一團，重複抽樣多次後統計每顆星"
                    "被歸進星團的頻率，當作成員機率。",
                    "**本專案採用 P ≥ 0.7 當門檻，得到 1,297 顆成員**，"
                    "再經第 2 步的測光品質篩選後剩 1,078 顆進入擬合。",
                    "⚠️ **這個 0.7 跟 Cantat-Gaudin 用的 0.7 只是數值恰好相同**，"
                    "兩者的機率構造完全不同（一個是重抽頻率、一個是密度比後驗），"
                    "==數值不可通約，不能直接拿來互相比較==，詳見 "
                    "`docs/reference/COMPARISON.md`。",
                ],
                "refs": [
                    {"cite": "Pera et al. (2021), A&A 650, A109 (pyUPMASK)",
                     "bibstem": "A&A", "volume": "650", "page": "A109", "year": "2021",
                     "doc": MET, "doc_line": 4,
                     "role": "成員判定使用的分群工具本身"},
                    {"cite": "Hunt & Reffert (2023), A&A 673, A114",
                     "bibstem": "A&A", "volume": "673", "page": "A114", "year": "2023",
                     "doc": "docs/reference/COMPARISON.md", "doc_line": 10,
                     "role": "獨立的成員目錄，用來對照驗證本專案的判定結果"
                             "（recall 1.000）"},
                ],
            },
            {
                "name": "Step2 CMD 建構與測光篩選",
                "scripts": ["pipeline/step2_cmd.py"],
            },
            {
                "name": "Step3 年齡/消光前向合成擬合",
                "scripts": [
                    "pipeline/step3_age.py",
                    "pipeline/isochrones.py",
                    "pipeline/mist.py",
                    "pipeline/bhac.py",
                ],
            },
            {
                "name": "Step4 雙星族群與逐星判定",
                "scripts": ["pipeline/step4_binaries.py"],
            },
            {
                "name": "Step5 IMF 冪次律 / 質量分層",
                "scripts": [
                    "pipeline/step5_imf.py",
                    "fit_real.py",
                    "pipeline/joint_fit.py",
                ],
                "queue_labels": ["p2_final2_v3"],
                "key_points": [
                    "==核心想法整個反轉過來：不去「修正」觀測資料，而是"
                    "**自己造一個假的星團**==——電腦裡生出 40,000 顆虛擬的星，"
                    "連雙星、望遠鏡誤差、看不見暗星的效應全部一起模擬進去，"
                    "然後問：==哪一組參數造出來的假星團，最像我們真的看到的那個？==",
                    "**這樣雙星就不再是麻煩**：傳統法必須先猜「哪幾顆是雙星」"
                    "再把它們挑掉，而那個猜測本身就是最大的誤差來源。"
                    "前向模型直接把「有多少比例是雙星」當成一個**待解的參數**"
                    "（`f_bin`），讓資料自己告訴我們答案，不用事先判斷任何一顆星。",
                    "**六個參數同時解，不是一個一個解**：年齡、消光、雙星比例、"
                    "IMF 斜率這幾個會互相影響（例如星團看起來偏紅，可能是比較老、"
                    "也可能是灰塵比較多）。==一個一個解等於「假設 A 是對的推出 B，"
                    "再用 B 反推 A」，繞了一圈回到自己，誤差會被低估==。",
                    "**本專案的最終答案：alpha = 2.382 ± 0.068**"
                    "（跑 10 次取平均，工作代號 `p2_final2_v3`）。"
                    "順帶一提，傳統法那一支算出 2.37–2.42 —— "
                    "==兩條完全獨立的路線得到幾乎一樣的答案，這是很強的交叉驗證==。",
                ],
                "prereq": [
                    "**赫羅圖／CMD（顏色-亮度圖）**：地科學過的那張圖——"
                    "橫軸是顏色（其實就是溫度），縱軸是亮度，"
                    "每顆星是圖上一個點。這個專案幾乎所有工作都在這張圖上進行。",
                    "**等時線（isochrone）**：==「同樣年齡的一群星，在赫羅圖上"
                    "應該排成什麼形狀」的理論預測線==。"
                    "給定年齡和質量，它就能告訴你這顆星該有多亮、什麼顏色。",
                    "**消光（extinction, A_V）**：星光穿過太空中的灰塵會變暗變紅，"
                    "就像隔著霧看路燈。要算對質量就必須先扣掉這個效應。",
                    "**參數簡併（degeneracy）**：兩個不同的原因造成幾乎一樣的結果，"
                    "光看結果分不出是哪個造成的。例如「星團比較老」和"
                    "「灰塵比較多」都會讓星團看起來偏紅。",
                ],
                "formula": [
                    {
                        "expr": "① 抽主星質量   m1  ~  dN/dm ∝ m^(-alpha)\n"
                                "② 擲骰子決定是不是雙星   機率 = f_bin\n"
                                "③ 若是雙星，抽質量比     q  ~  p(q) ∝ q^q_gamma\n"
                                "④ 伴星質量   m2 = q · m1",
                        "plain": "==造一顆假星的四個步驟==。就像抽籤："
                                 "先抽這顆星多重，再擲一次骰子看它有沒有伴星，"
                                 "有的話再抽伴星相對多重。重複 40,000 次，"
                                 "就有了一整個假星團。",
                        "meaning": "第①步的 `~` 是「按照這個分布抽」的意思。"
                                   "注意 ==伴星的質量是用「比例 q」決定的，"
                                   "不是另外再抽一次 IMF==。這代表我們最後量到的"
                                   "`alpha`，描述的是**主星**的質量分布。"
                                   "**這件事必須講清楚**，否則跟別人的論文比較時，"
                                   "可能對方算的是「所有星（含伴星）」，"
                                   "那就不是同一個東西、不能直接比大小。",
                        "inputs": "`alpha`（要量的 IMF 斜率）、`f_bin`（雙星比例）、"
                                  "`q_gamma`（伴星相對大小的分布），三個都是待解參數",
                        "outputs": "40,000 顆假星各自的質量",
                        "source": "`pipeline/joint_fit.py` 的 `synthesise()`；"
                                  "IMF 的分段形式取自 Kroupa (2001)",
                    },
                    {
                        "expr": "F_total  =  F1 + F2                        （亮度直接相加）\n"
                                "m_total  =  -2.5 · log10( F1 + F2 )        （再換回星等）",
                        "plain": "==把雙星的兩顆星「黏成」望遠鏡實際看到的一個點==。"
                                 "亮度可以直接相加，但星等不行（星等是對數），"
                                 "所以要先換成亮度、加完再換回星等。",
                        "meaning": "==這兩行就是整個專案的問題核心==："
                                   "望遠鏡分不開靠太近的兩顆星，只會記錄到總亮度。"
                                   "一對雙星因此看起來像「一顆特別亮的星」，"
                                   "傳統法就會把它誤判成「一顆特別重的星」。"
                                   "**前向模型的解法是：既然真實宇宙會這樣疊，"
                                   "那我造假星團的時候也照樣疊一次**，"
                                   "兩邊用同樣的規則，比較才公平。",
                        "inputs": "主星與伴星各自查等時線得到的星等（先換算成亮度 F）",
                        "outputs": "合成後的一個觀測點（G、BP、RP 三個波段各算一次）",
                        "source": "星等定義 m = -2.5·log10(F)；"
                                  "推導見 `docs/teaching/教學_前向模型.md` 第 3.4 節",
                    },
                    {
                        "expr": "把真實觀測與合成星團都畫成 CMD 上的格子圖（Hess 圖）\n"
                                "\n"
                                "模型 = (1 - eps) × 合成星團分布  +  eps × 均勻分布\n"
                                "lnL  = Σ (每一格) [ 實際星數 × ln(模型預測星數) - 模型預測星數 ]",
                        "plain": "==打分數：這組參數造出來的假星團，跟真的有多像？=="
                                 "做法是把赫羅圖切成一格一格，"
                                 "比較每一格「真的有幾顆星」和「模型預測幾顆星」，"
                                 "全部加起來就是分數 lnL。分數最高的那組參數就是答案。",
                        "meaning": "那個 `eps`（預設 0.01，即 1%）是必要的保險。"
                                   "==如果某一格模型預測 0 顆、但實際有星，"
                                   "算出來會是 ln(0) = 負無限大，整個計算就爆掉==。"
                                   "所以摻入 1% 的「均勻背景」，讓每一格都有一點點機率，"
                                   "物理意義是「總有少數星是模型沒描述到的」"
                                   "（殘留的非成員星、變星、測光異常的星）。",
                        "inputs": "真實觀測的格子圖、模型合成的格子圖、觀測星數 1,078",
                        "outputs": "一個分數 lnL —— 越大代表這組參數越能重現真實觀測",
                        "source": "`pipeline/step3_age.py` 的 `poisson_loglike()`。"
                                  "另外本專案有代數證明這個寫法跟更嚴謹的多項分布"
                                  "寫法只差一個常數，==不是近似、不影響答案=="
                                  "（見 `check_poisson_vs_multinomial.py`）",
                    },
                ],
                "refs": [
                    {"cite": "Kroupa (2001), MNRAS 322, 231",
                     "bibstem": "MNRAS", "volume": "322", "page": "231", "year": "2001",
                     "doc": FWD, "doc_line": 749,
                     "role": "分段冪律 IMF 的定義（0.3／1.3／2.3 三段）"},
                    {"cite": "Salpeter (1955), ApJ 121, 161",
                     "bibstem": "ApJ", "volume": "121", "page": "161", "year": "1955",
                     "doc": FWD, "doc_line": 750,
                     "role": "高質量端冪律形式的最早文獻"},
                    {"cite": "Li et al. (2020), ApJ 901, 49 (NGC 3532)",
                     "bibstem": "ApJ", "volume": "901", "page": "49", "year": "2020",
                     "doc": FWD, "doc_line": 753,
                     "role": "==統計混合模型處理雙星的直接先例，跟本專案前向模型"
                             "同哲學==。前向模型不是本專案發明的，這一點在"
                             "`PAPER_OUTLINE.md` 的新穎性聲明裡有明確界定"},
                    {"cite": "Bressan et al. (2012) PARSEC isochrones",
                     "bibstem": "MNRAS", "volume": "427", "page": "127", "year": "2012",
                     "doc": FWD, "doc_line": 751,
                     "role": "主要使用的等時線（恆星演化模型），"
                             "把質量換算成各波段星等的那張查表"},
                    {"cite": "Choi et al. (2016) MIST isochrones",
                     "bibstem": "ApJ", "volume": "823", "page": "102", "year": "2016",
                     "doc": FWD, "doc_line": 751,
                     "role": "第二套獨立的等時線，用來量「換一個恆星演化模型"
                             "會不會改變結論」這項系統誤差"},
                    {"cite": "Rosen (2026), arXiv:2603.15779", "arxiv": "2603.15779",
                     "doc": FWD, "doc_line": 12,
                     "role": "忽略雙星的偏差不隨樣本數縮小——"
                             "統計誤差以 1/√N 遞減、偏差是常數，"
                             "==樣本越大只會「越精確地錯」=="},
                ],
                "core": {
                    "file": "pipeline/joint_fit.py", "line": 287,
                    "name": "JointModel.synthesise()",
                    "why": "==整個前向模型的心臟==。上面前兩條公式都在這個函式裡："
                           "抽主星質量、擲骰子決定誰是雙星、抽質量比、查等時線、"
                           "光通量相加、疊上測光誤差、套用選擇函數——"
                           "一次生出 40,000 顆假星。外層的最佳化器要做的"
                           "就是不斷換參數呼叫它，直到生出來的假星團"
                           "最像真的觀測。",
                },
            },
        ],
    },
    {
        "name": "PDMF → IMF（五步，見 docs/planning/PDMF_TO_IMF_PLAN.md 第五節）",
        "steps": [
            {
                "name": "第1步 文獻基準線（Li+2026）",
                "scripts": [],
                "note": "手算代入文獻公式，沒有對應腳本，已完成。",
            },
            {
                "name": "第2步 前向模型逐半徑重跑 α(<r)",
                "scripts": ["fit_real.py"],
                "queue_labels": [
                    "radial_r1_final", "radial_r2_final",
                    "radial_r3_final", "radial_rall_final",
                ],
            },
            {
                "name": "第3步 LIMEPY 多質量平衡模型",
                "scripts": [
                    "scripts/diagnostics/limepy_multimass.py",
                    "scripts/diagnostics/limepy_radial_crosscheck.py",
                ],
                "queue_labels": ["limepy_radial_crosscheck"],
            },
            {
                "name": "第4步 放大搜尋半徑（5°→8–17°）",
                "scripts": [
                    "scripts/data_prep/fetch_gaia.py",
                    "scripts/drivers/run_pipeline.py",
                ],
                "queue_labels": ["pdmf_step4_radius_expansion"],
            },
            {
                "name": "第5步 N-body 校準（PeTar / Converse & Stahler 2010）",
                "scripts": [
                    "scripts/nbody_petar/nbody_pdmf_smoke.py",
                    "scripts/nbody_petar/nbody_pdmf_ensemble.py",
                    "scripts/nbody_petar/petar_pdmf_analysis.py",
                    "scripts/nbody_petar/petar_pdmf_ensemble.py",
                ],
                "queue_labels": ["nbody_prior_from_radial"],
                "key_points": [
                    "⚠️ **這幾支腳本的檔頭說明是英文**——是另一位協作者"
                    "（Codex）寫的，不是這個主控板顯示錯誤。下面先給中文"
                    "重點，原文說明還是可以往下展開看。",
                    "**要回答的問題**：前面幾步量到「星團中心的星比較輕、"
                    "外圍的星比較重」（核心 alpha=1.77 → 外圍 alpha=2.29）。"
                    "==這可能是真正的質量分層（重星會慢慢往中心沉），也可能"
                    "只是雙星比例隨半徑變化造成的假象==——N-body 模擬是唯一"
                    "能分辨這兩種可能的方法：先在電腦裡真的放進去一群"
                    "有各種質量的星、讓重力交互作用跑一段時間，看看動力學"
                    "本身會不會自然生出跟觀測一樣的分層。",
                    "**做法**：用 `mcluster_sse` 生成初始條件（星的質量分布"
                    "照 Kroupa IMF、依照文獻參數決定聯星比例），交給 `PeTar`"
                    "（一套 N 體重力模擬程式）真的算重力交互作用隨時間如何"
                    "演化，再用這裡的分析腳本量算完之後 alpha 隨半徑怎麼變。",
                    "**先導測試的結果（探索性、非正式數字）**："
                    "==核心 alpha=0.879 → 外圍 alpha=1.316，方向跟觀測"
                    "（核心較平、外圍較陡）一致==——這是這條路線第一次拿到"
                    "跟觀測同方向的動力學預測，但只是 270 個系統的單次示範"
                    "跑（文獻建議至少 25 次取平均才能報統計誤差），"
                    "不能拿來跟觀測數字比大小或引用。",
                ],
                "prereq": [
                    "**N-body 模擬**：把星團裡每一顆星都當成一個質點，"
                    "電腦一步一步算它們之間的重力如何互相拉扯、如何隨時間"
                    "移動——不是套公式直接解，是真的一步步算出來的。",
                    "**質量分層（mass segregation）**：重的星因為交互作用"
                    "會漸漸往星團中心沉澱，輕的星則相對容易被推往外圍或"
                    "彈射出去。這是天文學裡已知的動力學效應，不是本專案"
                    "發現的，本專案要驗證的是「這個效應能不能解釋我們"
                    "量到的分層幅度」。",
                ],
                "refs": [
                    {"cite": "Converse & Stahler (2010), MNRAS 405, 666",
                     "bibstem": "MNRAS", "volume": "405", "page": "666", "year": "2010",
                     "doc": "docs/teaching/教學_PDMF轉IMF.md", "doc_line": 414,
                     "role": "本步驟初始條件的參數來源（星數、聯星比例、"
                             "virial 平衡狀態等），模擬設定盡量對齊這篇的"
                             "假設，方便結果互相比較"},
                ],
            },
        ],
    },
    {
        "name": "穩健性 / 敏感度診斷（LIMITATIONS.md A–D 類，來自 WORK_BOARD.md）",
        "steps": [
            {
                "name": "p6_lowmass_v3（A1、A3）低質量段冪次系統誤差",
                "scripts": ["profile_lowmass.py"],
                "queue_labels": ["p6_lowmass_v3"],
            },
            {
                "name": "p6b_inject_lowmass_v2（A1）低質量段可辨識性",
                "scripts": ["inject_lowmass.py"],
                "queue_labels": ["p6b_inject_lowmass_v2"],
            },
            {
                "name": "D2 membership_threshold 敏感度掃描",
                "scripts": ["scripts/diagnostics/sensitivity_sweep.py"],
                # 注意：WORK_BOARD.md 裡這個任務叫
                # sensitivity_sweep_membership_threshold，但實際派工到
                # cloud_queue.txt 時用的是下面這兩個帶批次後綴的標籤——
                # 前者從沒被當成真正的佇列標籤用過，留著只會讓這個步驟的
                # 狀態徽章被一筆「查無紀錄」的假陰性拖成「不確定」，
                # 即使兩批真正的工作其實都已完成（2026-08-25 發現並修正）。
                "queue_labels": [
                    "d2_membership_threshold_p06_p07_retry",
                    "d2_membership_threshold_p05_p08_p09",
                ],
            },
            {
                "name": "bhac15_isochrone_test（C1、D1）等時線模型效應分解",
                "scripts": ["pipeline/bhac.py", "fit_real.py"],
                "queue_labels": ["bhac15_isochrone_test"],
            },
            {
                "name": "extinction_form_test（C5，現役缺陷）消光分布形式",
                "scripts": ["fit_real.py"],
                "note": "透過 fit_real.py 換消光分布設定跑，沒有獨立診斷腳本。",
                # 實際派工用的標籤是 c5_davform_truncexp／c5_davform_lognormal
                # （截尾指數／對數常態兩個消光分布變體），不是 WORK_BOARD.md
                # 的任務名稱本身——跟 D2 同一種「任務名稱≠真正佇列標籤」的
                # 坑，2026-08-25 對照 cloud_queue.txt 實際內容訂正；
                # 2026-08-26 補上先前漏收的 lognormal 那一半（gcp1 當時正在
                # 跑，漏收會讓這個步驟在導覽列被誤判成「沒有紀錄」）。
                "queue_labels": ["c5_davform_truncexp", "c5_davform_lognormal"],
            },
            {
                "name": "pyupmask_completeness_test（C8）完整度召回率",
                "scripts": ["scripts/diagnostics/completeness.py"],
                "queue_labels": ["pyupmask_completeness_test"],
            },
            {
                "name": "extra_scatter_sensitivity（C19）額外亮度散布敏感度",
                "scripts": ["fit_real.py"],
                "note": "透過 fit_real.py 換 σ_extra 設定跑，沒有獨立診斷腳本。",
                "queue_labels": ["extra_scatter_sensitivity"],
            },
            {
                "name": "configCD_real_data_compare（D10）dav 上界比較",
                "scripts": ["fit_real.py"],
                "note": "config C／D 只差 dav 上界，透過 fit_real.py 換設定跑。",
                # 實際派工用的是全小寫 configcd_real_data_compare，跟
                # WORK_BOARD.md 任務名稱的大小寫不一樣，2026-08-25 對照
                # cloud_queue.txt 實際內容訂正。
                "queue_labels": ["configcd_real_data_compare"],
            },
            {
                "name": "empirical_ml_relation_test（D11）經驗質光關係可行性查證",
                "scripts": [],
                "note": ("文件查證工作（見 docs/planning/"
                        "PLAN_D11_經驗質光關係_可行性評估.md），"
                        "沒有程式輸出，狀態要看那份文件。"),
            },
            {
                "name": "mass_dependent_fbin（D14 衍生）雙星比例對質量的相依性",
                # 之前這裡誤指到 scripts/diagnostics/inject_mass_dependent_fbin.py
                # ——那是一支英文 docstring 的小型決定性煙霧測試，不是
                # cloud_queue.txt 實際派工用的腳本；真正跑 contrast=0/0.15/0.30
                # 正式 sweep 的是根目錄的 inject_massdep_fbin.py（2026-08-26
                # 核對兩份檔頭說明才發現這個對不上，改回正確的那支）。
                "scripts": ["inject_massdep_fbin.py"],
                "queue_labels": ["mass_dependent_fbin"],
            },
            {
                "name": "praesepe_pr11_close_out（D8、A5）Praesepe 多星團驗證收尾",
                "scripts": [
                    "scripts/multicluster/cluster_imf_tier1.py",
                    "scripts/multicluster/cluster_forward_validation.py",
                ],
                # PR #11 實際上已經合併（codex/ngc3532-praesepe-generalization，
                # 見 WORK_BOARD_DONE.md 2026-08-20 那行），這個任務名稱本身
                # 也已經過期——後續的多星團驗證收尾工作見
                # docs/planning/D8_POSTMERGE_MULTICLUSTER_VALIDATION_2026-08-23.md
                # （2026-08-26 訂正，原本的說明還在講「PR #11 是否合併」）。
                "note": "PR #11 已合併；後續驗證見 D8_POSTMERGE_MULTICLUSTER_VALIDATION_2026-08-23.md。",
            },
            {
                "name": "comaber_tier1（A5、D8）Coma Berenices 多星團驗證",
                "scripts": [
                    "scripts/multicluster/cluster_imf_tier1.py",
                    "scripts/multicluster/prepare_cluster_tier2.py",
                ],
                "queue_labels": ["comaber_tier1"],
            },
            {
                "name": "bp15_bp20_paired_comparison（D12）BP 誤差門檻配對比較",
                "scripts": [
                    "scripts/diagnostics/prepare_bp15_paired_dispatch.py",
                    "scripts/diagnostics/summarize_bp15_formal_paired.py",
                ],
                "queue_labels": ["bp15_bp20_paired_comparison"],
            },
        ],
    },
]
