# 計劃：傳統法完整版——全部主流雙星修正法 + 前向模型比較

**這份文件是給下一個執行階段（Sonnet 5）的完整交接計劃，不含任何已完成的實作**——
使用者要求先只做規劃，把方向和每一步具體內容定案，實作留給 Sonnet 5 做以節省 token。

---

## 一、背景與目的

**現況**：`traditional_accounting.py` 目前只有兩種雙星修正變體（全當單星、CMD 剔除），
且新版程式碼（含 P7 質量範圍對齊）**已寫但從未執行過**——`results/traditional_accounting.npz`
與兩份 log（`trad_acc.log`、`trad_acc2.log`）的時間戳（08-08 11:25）都早於程式碼最後一次
修改（08-09 23:46），npz 裡的鍵格式也對不上目前程式碼會寫出的格式（見下方「已確認的落差」）。

**使用者這次的要求**：不要只做三種，把**全部主流的傳統雙星修正法**都拿來跟前向模型放在
同一張表比較，目的是把這個比較本身做成論文有創新意義的內容——即「同一批資料、同一套
誤差核算，把好幾種業界常見的雙星處理手法跟我們的前向模型並列比較」，這在文獻裡沒人做過
（先前查證過，見 PAPER_OUTLINE.md:51-59 的「用語校準」）。

**要交付的東西**：
1. 5 種傳統雙星修正變體 + 前向模型，共 6 欄的比較表（同一批 1,078 顆星、同一個質量範圍、
   同一個 isochrone）
2. 確認後的「傳統版最終 IMF 數字」（含誤差棒，可寫進 Table 3）
3. 每個變體都有文獻依據，且驗證過跟前人的做法一致（不是自己發明的定義）
4. 明確記錄哪裡跟前向模型「控制變因一致」、哪裡本質上做不到一致（要誠實講，不要假裝）

---

## 二、五種傳統變體 + 前向模型（全部方法論依據）

| # | 變體 | 演算法 | 文獻依據 | 現有程式碼 | 統計誤差怎麼量 |
|---|---|---|---|---|---|
| A | **全當單星**（忽略雙星） | 每顆星（含未偵測雙星）直接查單星等時線質量，未分箱 MLE 冪律 | 這是幾乎所有前 Gaia 時代傳統法論文的**隱含預設**（未特別處理雙星），本專案拿它當基準線 | 已有：`traditional_accounting.py` `remove_cmd_binaries=False` | 已有：注入回收（20 trials） |
| B | **CMD 偏移剔除法** | 比同顏色單星主序亮超過門檻（0.753 mag 等質量雙星偏移的一半 = 0.375 mag）就剔除，剩下當單星查質量 | **Cordoni et al. 2023, A&A 672, A29**（78 星團光度法雙星，DOI 10.1051/0004-6361/202245457）；**Mikhnevich, Plotnikova, Carraro & Seleznev 2026, arXiv:2604.20722**（8 個近距星團含 M45 本身，光度法識別雙星，f_bin 0.16–0.44） | 已有：`ms_colour_to_g` + `cmd_thresh=0.375` | 已有：注入回收（20 trials） |
| C | **RUWE 剔除法** | Gaia RUWE（renormalized unit weight error）>1.4 視為天測法偵測到的雙星，剔除後查質量 | RUWE 作為雙星／天測品質指標的標準文獻：**Lindegren et al. 2021, A&A 649, A2**（Gaia EDR3 天測解，RUWE 定義與品質判準）——**目前 `hb_cite.py` 沒有這條，需要新增** | 部分有：`pipeline/step4_binaries.flag_ruwe()` 已存在（Table 2 四法之一），但**從未整合進 `traditional_accounting.py`** | **無法注入回收**（`make_fake()` 不模擬 RUWE）——只能對真實 1,078 顆做 bootstrap 重抽（見第四節） |
| D | **Gaia NSS 剔除法** | `non_single_star` 官方目錄旗標非零即剔除 | Gaia 官方 non-single-star 處理鏈：**Gaia Collaboration, Arenou et al. 2023, A&A 674, A34**（"Gaia DR3: Stellar multiplicity, a teaser..."）——需要新增到 `hb_cite.py` | 部分有：`pipeline/step4_binaries.flag_nss()` 已存在，**從未整合進 `traditional_accounting.py`** | 同 C，只能 bootstrap（且樣本只有 24 顆被標記，2.2%，效應量預期很小——這本身是有意義的交叉檢查結果，不是失敗） |
| E | **文獻解析統計修正法**（不逐星剔除） | 不剔除任何星，直接對變體 A 的 α 加上文獻給的解析修正量 | **Rosen 2026, arXiv:2603.15779**（"Confidently Wrong: Why Ignoring Binaries Biases IMF Inference at Large Sample Sizes"）給的光度加總修正量 −0.011～−0.021；經典先例 **Maíz Apellániz 2008, ApJ 677, 1278**（"Biases on IMF determinations II"）——族群層級的解析修正，不是逐星判定，方法論上與 A–D 是不同類別 | 全新——只是把已經在 `hb_cite.py`/LIMITATIONS.md 裡的文獻數字套用成一個修正步驟 | 已有：注入回收（跟 A 共用同一批合成資料，只是後處理多一步） |
| F | **前向模型**（統計混合模型，不逐星判定） | f_bin、q_gamma 是聯合概似裡的自由參數，雙星用流量相加模擬、整批一起擬合，沒有任何單星判定 | 直接先例：**Li, Shao, Li, Yu, Zhong & Chen 2020, ApJ 901, 49**（NGC 3532，MCMC 對 CMD 做 single+binary 混合模型統計推斷 f_bin 與質量比分布）——本專案的 `JointModel` 是同一種哲學的獨立實作（Hess 圖 Poisson 概似而非逐星 CMD 密度） | 已有：`fit_real.py` config C（`p2_final2`，等 P10 定案） | 已有：注入回收（S3F，σ_α=0.144） |

**已確認的落差（不是新問題，是既有事實）**：`traditional_accounting.py` 目前寫的
`traditional_alpha()` 是 boolean 旗標（`remove_cmd_binaries: bool`），只夠表示 A/B 兩種，
擴充到 5 種必須先改成字串式的 `variant` 參數（見第四節 Step 1）。

**引用修正**：`教授會談摘要.md:38` 把 arXiv:2604.20722 歸給「Carraro 等」，但第一作者其實是
Mikhnevich——Carraro 是共同作者不是通訊/第一作者，**引用格式要訂正成
"Mikhnevich et al. 2026"**（教學_傳統法誤差核算.md:179 原本就寫對了，是教授會談摘要那處錯）。

---

## 三、跟前向模型的控制變因一致性（逐項核對，誠實列出做不到的部分）

| 變因 | 現況 | 要怎麼對齊 |
|---|---|---|
| 觀測資料 | 同一份 `data/cmd_members.csv`（1,078 顆） | **已一致**，不用改 |
| 質量範圍 | 目前程式碼兩個範圍都跑（0.30–2.50 與 0.50–2.50） | **主表只放 0.50–2.50**（跟前向模型 α 定義域一致，m>0.5 M☉ 那段），**0.30–2.50 降級成附錄**，用來單獨展示「範圍不對齊」這個純方法學效應的大小（現有的 −0.2 那項） |
| isochrone（年齡/消光/金屬量） | 目前用兩個歷史選擇：`step3 舊最佳(8.00,0.20)` 與 `C 設定最佳(8.10,0.30)`，後者也不是最新 | **主表只用當下 config C 的最終確認值**（等 P9a-redo/P10/P6b 落定後的 logage/A_V/MH），`step3 舊最佳` 降級為附錄敏感度測試（現有的「傳統法對等時線選擇的敏感度 0.13」這個結論保留，只是不再混進主表） |
| 統計誤差核算方式 | A/B 用注入回收；C/D/E 目前沒有 | A/B/E 用注入回收（同一批 THETA_TRUE、f_bin 掃描、20 trials）；**C/D 做不到注入回收**（`make_fake()` 只產生 color/mag，不模擬 RUWE 或 Gaia NSS 目錄旗標），改用 bootstrap 重抽真實 1,078 顆——**這是誠實的方法論限制，不是待修的 bug**，論文裡要講清楚 C/D 的誤差棒跟 A/B/E/F 不是同一把尺，只能定性比較中心值、不能直接比誤差棒大小 |
| MH 處理 | 傳統法用固定注入/固定 isochrone 的 MH，不是自由參數 | A–E 不受 P10（前向模型的高斯先驗問題）影響，可以先做；**F（前向模型欄）的數字要等 P10 定案才能填入**，定案前先留空或標註「暫定，待 P10」 |
| 差異消光 dav | 傳統法用固定注入值 dav_true=0.30；前向模型 config C 有自由參數 | **做不到對齊，也不該假裝對齊**——傳統法完全沒有消光自由度，這是兩個方法本質上的差異，不是需要修的控制變因，要在文件裡明講（前向模型能吸收消光造成的星等展寬，傳統法只能用單一固定值，這正是前向模型設計上的優勢之一） |

---

## 四、給 Sonnet 5 的具體實作步驟

**Step 1 — 重構 `traditional_alpha()` 簽名**（`traditional_accounting.py:76`）：
把 `remove_cmd_binaries: bool` 改成 `variant: str`（值：`"ignore"` / `"cmd_offset"` /
`"ruwe"` / `"nss"` / `"analytic_correct"`），內部用 if/elif 分派。`ignore` 保留現有行為，
`cmd_offset` 沿用現有 `ms_colour_to_g` 邏輯，`analytic_correct` 直接呼叫 `ignore` 分支後
對回傳的 alpha 加上修正量（見 Step 4）。

**Step 2 — RUWE/NSS 整合**：`main()` 目前只讀 `color`/`mag`（`cmd_members.csv` 的
`bp_rp`/`phot_g_mean_mag`），要一併讀 `ruwe`／`non_single_star` 兩欄（欄位已存在，見
`pipeline/step4_binaries.flag_ruwe`/`flag_nss` 的用法），`ok` 過濾要保留這兩欄跟
color/mag 同步（同一個布林遮罩）。`variant="ruwe"`/`"nss"` 呼叫
`step4_binaries.flag_ruwe(mask_table, cfg.step4_binaries.ruwe_threshold)` /
`flag_nss(mask_table)`，剔除後走 `assign_masses`+`mle_powerlaw`。

**Step 3 — 新增 bootstrap 誤差函式**：
```python
def bootstrap_alpha_err(color, mag, ruwe, nss, iso, dm, av, ext,
                        m_lo, m_hi, variant, n_boot=1000, seed=7000):
    rng = np.random.default_rng(seed)
    n = len(color)
    outs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)   # with replacement
        a, *_ = traditional_alpha(color[idx], mag[idx], iso, dm, av, ext,
                                  m_lo, m_hi, variant=variant,
                                  ruwe=ruwe[idx] if ruwe is not None else None,
                                  nss=nss[idx] if nss is not None else None)
        if np.isfinite(a):
            outs.append(a)
    return float(np.mean(outs)), float(np.std(outs))
```
用在 C、D 兩個變體的真實資料點估計；**也順便對 A/B 各跑一次 bootstrap 當交叉檢查**，
在文件裡明講「bootstrap 量的是『對同一批 1,078 顆重抽樣的敏感度』，注入回收量的是
『對真實但未知的星團真值的偏差與散布』，兩者是不同的量，數字接近是好現象但不是必然」。

**Step 4 — `analytic_correct` 修正量的選擇**：Rosen 2026 給的光度加總修正量區間是
−0.011～−0.021。**建議固定用區間中點 −0.016**，修正後的誤差棒 = 變體 A 注入回收的散布
（不因為修正而變小或變大，因為修正量本身沒有獨立不確定度可用）；在
LIMITATIONS.md 記一筆「修正量用固定中點是簡化，文獻本身的區間寬度 0.01 沒有被
傳播進誤差棒，之後有空可以做敏感度測試」。

**Step 5 — 更新 `main()` 的兩段迴圈**（注入回收、真實資料）：
- 變體集合改成 `[("ignore","全當單星"), ("cmd_offset","CMD剔除"), ("analytic_correct","文獻解析修正")]`
  三個能做注入回收的先跑；C/D 只在真實資料段落跑（用 Step 3 的 bootstrap）。
- isochrone 選擇：主表只用「當下 config C 的最終確認值」（等 P9a-redo/P10/P6b 定案後
  從 `results/`（例如未來的 `p2_final3.npz` 或等價物）讀出 logage/A_V/MH，不要寫死數字），
  `step3 舊最佳` 移到獨立的「附錄：等時線敏感度」段落。
- 質量範圍：主表只跑 0.50–2.50；0.30–2.50 移到附錄段落。

**Step 6 — 前向模型欄位**：不重新計算，直接讀取 P10 定案後的最終 config C 結果
（alpha 均值、標準差），塞進同一張比較表當第 6 欄。**這一欄要等 P10 完成才能定案**，
Step 5 的其餘 5 欄不受此阻塞，可以先做完。

**Step 7 — 輸出**：
- 新結果檔 `results/traditional_accounting_v2.npz`（**不要覆蓋舊檔**，舊的兩變體結果
  留著當歷史對照，尤其是還沒對齊 isochrone/質量範圍前的版本）。
- 印出一張 6 欄比較表（5 傳統變體 + 前向模型），欄位：變體、α、誤差、誤差核算方式
  （注入回收/bootstrap）、剔除星數、資料來源引用。

**Step 8 — 補文獻條目到 `hb_cite.py`**：
- Lindegren et al. 2021, A&A 649, A2（RUWE 定義；Sonnet 5 執行時應該查一次確認精確的
  卷期頁碼，這裡給的是暫定書目資訊）
- Gaia Collaboration, Arenou et al. 2023, A&A 674, A34（Gaia NSS 處理鏈；同上，執行時
  查證確認）
- Maíz Apellániz 2008, ApJ 677, 1278（Biases on IMF determinations II，DOI 已知
  10.1086/529041，可直接查證）
- Li, Shao, Li, Yu, Zhong & Chen 2020, ApJ 901, 49（NGC 3532 混合模型，DOI 已知
  10.3847/1538-4357/abaef3）
- Rosen 2026, arXiv:2603.15779（目前只有 arXiv 編號沒有作者，補上 "Anna L. Rosen"）
- 訂正 `教授會談摘要.md:38` 的 arXiv:2604.20722 作者歸屬（Mikhnevich et al.，不是
  「Carraro 等」）

**Step 9 — `PAPER_OUTLINE.md` 更新**：
- 表 3 改寫成 6 欄比較（5 傳統變體 + 前向模型），質量範圍統一標註 0.50–2.50
- P7 標記完成，內容改成「不只對齊質量範圍，同時擴充成 5 種傳統變體 + 前向模型的完整比較」
- 新增一段解釋這個比較本身的論文貢獻定位：**跟第 51-59 行「用語校準」的既有原則一致**
  ——誠實定位是「同一批資料、同一套誤差核算，把好幾種業界常見雙星處理手法系統性並列」，
  不要宣稱發明了新方法
- P1 描述更新，反映擴充後的比較範圍

**Step 10 — `LIMITATIONS.md` 記錄**：
- C/D 用 bootstrap 而非注入回收，是方法論上的誠實限制不是待修 bug（比照 `CLAUDE.md`
  的待辦分類標準：這是「已知、不會被誤認成待辦」的一種第三類——結構性做不到，不是
  現役缺陷也不是未來風險）
- `analytic_correct` 用固定修正量中點，未傳播文獻區間寬度，標記為待改善但非現役缺陷

**Step 11 — P8（傳統法文獻基準驗證）順手完成**：不需要真的下載 NGC 3532 資料重現數字
（那是可選項，成本高），優先做**方法論核對**：把 `traditional_accounting.py` 的質量範圍
（0.50–2.50 對齊後）、isochrone 來源（PARSEC）、MLE 誤差核算方式，跟 Li+2020 的
0.5–1.5 M☉／PARSEC／MCMC 混合模型逐項對照，寫一段到 `PAPER_OUTLINE.md`，
確認我們的傳統法實作定義（未分箱 MLE 冪律 + 單星質量指派）本身沒有跟主流脫節。

---

## 五、時程與依賴順序

Step 1–4（程式碼改動）跟目前跑著的 P9a-redo/P9c/P10/P11/P12 完全independent，
可以立刻開始。Step 5–7（真的跑比較）裡，A/B/E/C/D 五個傳統變體**不需要等 P10**，
可以先在本機佇列排開；**只有 Step 6 的前向模型欄位要等 P10 定案**，定案前該欄先留
「暫定（p2_final2, 未套用高斯先驗）」的標註，不要假裝已經是最終數字。

**建議執行順序**：Step 1-4（程式碼）→ Step 8（補文獻，跟程式碼改動平行做）→
Step 5-7 用小 `--trials 2` 先跑一次確認沒有崩潰 → 確認後排進 `queue.txt` 用正式
trials 數（建議跟現有一致，20 trials）→ Step 9-11（文件更新，等數字出來後才能寫）。

---

## 六、驗證方式

- 每個修改過的檔案先用 `py -c "import ast; ast.parse(open(f,encoding='utf-8').read())"` 過語法檢查
- 全部變體先用 `--trials 2` 跑一次，確認 RUWE/NSS/analytic_correct 三個新變體不會崩潰、
  數字看起來合理（alpha 落在 1.5–3.0 這個物理上合理的範圍），再排正式的 `--trials 20`
- bootstrap 誤差函式要對 A/B 兩個「兩把尺都能算」的變體做交叉檢查，確認 bootstrap
  標準差跟注入回收標準差量級相近（不要求相等，只要求同量級，否則代表 bootstrap
  實作有問題）
- 完成後 commit + push，訊息裡列出這次擴充了哪幾個新變體、引用了哪些新文獻
