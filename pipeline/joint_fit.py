# -*- coding: utf-8 -*-
"""六參數聯合擬合：年齡、消光、雙星比例、IMF 斜率、金屬量、q_gamma 一次解出。

**這支模組存在的理由是修正一個方法論錯誤。** 原本的流程是循序擬合：
第 3 步固定 IMF 與雙星比例去解年齡與消光，第 4 步固定 IMF 去解雙星比例，
第 5 步再固定雙星比例去解 IMF 斜率。但這四個參數彼此簡併 ——
IMF 斜率改變主序上的星數分布、雙星比例改變主序上方的展寬，
兩者都會影響年齡擬合；反過來年齡又決定質量-光度關係。
循序擬合等於用「假設 A 為真」推出 B，再用 B 推出 A，得到的誤差會被低估，
而且無法呈現參數之間的相關性。

正確作法是把四個參數放進同一個機率模型一次取樣。網格搜尋在四維會爆炸
（例如各 20 格就是 16 萬次生成），所以改用 MCMC —— 它只在機率高的區域取樣，
不需要掃過整個空間。

概似函數必須是**確定性**的（給定參數就給定值），否則 MCMC 的接受判準會被
蒙地卡羅雜訊汙染。這靠 draw_randoms() 預先抽好所有亂數來達成。

======================================================================
【這支程式在做什麼】
======================================================================
前向模型的「本體」。它回答：「如果星團的年齡、消光、雙星比例、IMF 斜率、
金屬量、雙星質量比分布是某一組值，生成出來的合成星團在色光圖上會長什麼樣？
跟真正觀測到的有多像？」
  - JointModel.synthesise(theta)      給一組參數 → 生成一整群合成星
  - JointModel.log_likelihood(theta)  把合成星與觀測星都切成 Hess 圖，算相似度
  - JointModel.log_posterior(theta)   相似度 + 先驗 → 擬合要最大化的分數
  - run_mcmc()                        用 emcee 在參數空間取樣（MCMC 版）
基本模型是六個參數（PARAM_NAMES），另外可選擇加上差異消光 dav 與低質量段冪次。
⚠ 用 MCMC 跑這個模型的鏈從未收斂（LIMITATIONS.md C11），所以頭條數字不是用
  run_mcmc() 得到的，而是 fit_real.py 用同一個 log_posterior() 做網格搜尋得到的。

這個檔案**沒有 main()**，由 fit_real.py（頭條）、scripts/drivers/run_joint.py
（MCMC）、injection_recovery.py（注入回收）等程式 import 使用。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
第三方套件：
  numpy（np）
      np.interp       一維線性內插（由質量查星等、由星等查誤差）
      np.unique／np.argsort／np.argmin  去重、排序、找最小值位置
      np.log10／np.exp／np.log1p        對數與指數（星等↔流量、對數常態分布）
      np.clip         把值限制在範圍內
      np.where        依條件逐元素二選一
      np.percentile／np.corrcoef        百分位、相關係數矩陣（整理 MCMC 結果）
  scipy.stats.norm    norm.cdf：標準常態累積分布函數（只在 trunc_exp 消光分布用）
  emcee               MCMC 取樣器（在 run_mcmc() 裡才 import）
                        emcee.EnsembleSampler  一群「走者」同時在參數空間移動
                        emcee.moves.DEMove／DESnookerMove  走者決定下一步的方式
  multiprocessing.Pool  多行程平行（在 make_pool() 裡才 import）
本專案其他模組：
  pipeline/isochrones.py（iso_mod）  這個版本沒有直接用到
  pipeline/step3_age.py：
      IMF_BREAKS      各種 IMF 的分段定義（Kroupa：0.01／0.08／0.5／200 M☉，
                      冪次 −0.3／−1.3／−2.3）
      sample_imf(u, …)  逆變換抽樣：把 0–1 均勻亂數 u 換成服從 IMF 的質量
                      （每顆星只用一個亂數，跟 IMF 參數無關，共用亂數才成立）
      draw_randoms()  一次抽好所有要用的亂數（質量、是否雙星、q、測光誤差、
                      差異消光、選擇函數…），之後每次生成都重複使用
      _interp_err()   依 G 星等從 errmodel 內插出測光誤差
      hess()          把色光圖切成格子、數每格的星數（Hess 圖）
      poisson_loglike()  觀測與模型 Hess 圖逐格比較的 Poisson 對數概似
                      （混入 1% 均勻分布當殘留場星污染）
      _Ext            三個消光係數的小盒子

======================================================================
【(b) 用到的參數與意義】
======================================================================
六個擬合參數 theta（PARAM_NAMES 的順序）：
  logage    log10(年齡/年)
  A_V       V 波段消光（星等）
  f_bin     雙星比例：一個系統帶伴星的機率
  alpha     m > 0.5 M☉ 那段 IMF 的斜率（dN/dm ∝ m^−α）
  MH        金屬量 [M/H]
  q_gamma   雙星質量比 q = m2/m1 的分布 p(q) ∝ q^q_gamma（0 = 均勻）
選配的第 7、8 個參數：dav（差異消光的星對星散布）、p_lowmass（0.08–0.5 M☉ 段冪次）
config.toml [joint_fit]（先驗範圍與 MCMC 設定）：
  logage 7.30–8.30、A_V 0–0.6、f_bin 0–1、alpha 1.5–3.2、MH −0.6–0.6、
  q_gamma −1.5–1.5；金屬量高斯先驗中心 −0.03、寬度 0.10
  n_walkers = 48、n_steps = 6000、n_burn = 2000（MCMC 用）
config.toml 其他段落：
  [step3_age] n_synthetic（合成星數）、hess_*（Hess 圖格數與範圍）、
              binary_q_min = 0.1（q 的下限）、model_hess_smooth
  [step2_cmd] ext_coeff_*（消光係數）、g_bright_limit = 4.0
  [step1_membership] g_mag_max = 18.0、random_seed = 42
物件屬性（預設值＝正式設定，敏感度測試會覆寫）：
  dav = 0.0、selection = None（fit_real.py 會掛上選擇函數）、
  low_mass_slope = −1.3、outlier_frac = 0.01、use_native_bprp_err = False、
  extra_scatter = 0.0、dav_distribution = "lognormal"

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 197–264 行｜__init__() 後半：設定先驗範圍、預先取出要用的每一條等時線
  核心 2｜第 384–400 行｜log_prior()：先驗——超出範圍就是 −∞，金屬量加高斯懲罰
  核心 3｜第 402–674 行｜synthesise()：由參數生成合成星團（整個前向模型最核心的一段）
  核心 4｜第 676–697 行｜log_likelihood()／log_posterior()：合成 vs 觀測的相似度
  核心 5｜第 724–770 行｜run_mcmc()：用 emcee 取樣

======================================================================
【(d) 整體流程】
======================================================================
建立模型（一次）：
  觀測色光圖 → 觀測 Hess 圖；讀先驗範圍；預抽所有亂數；
  把先驗範圍內每個 (年齡, 金屬量) 的等時線先取出來排好
每評估一組參數 theta（擬合時重複成千上萬次）：
  先驗檢查（超界 → −∞）
    → synthesise：
        取最接近的等時線
        → 依 IMF（高質量段斜率 = α）抽 n_syn 個主星質量
        → 由質量內插出 G、BP、RP 絕對星等
        → 每個系統以機率 f_bin 帶伴星；伴星質量 = q × 主星質量；
          兩顆星的流量相加，塌縮成一個光點
        → 加距離模數與消光（可選每顆星不同的消光）
        → 加上跟觀測同等級的測光誤差
        → 只留 4 ≤ G ≤ 18、且通過選擇函數的星
    → 合成星 → 合成 Hess 圖 → 跟觀測 Hess 圖逐格比 → Poisson 對數概似
    → 加上先驗 = 對數後驗
擬合：fit_real.py 用網格搜尋找讓對數後驗最大的 theta；run_mcmc() 則是取樣
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

from . import isochrones as iso_mod
from .step3_age import (IMF_BREAKS, _Ext, _interp_err, draw_randoms, hess,
                        poisson_loglike, sample_imf)

# ↓ 六個擬合參數的名稱與順序；theta 陣列就照這個順序排
PARAM_NAMES = ["logage", "A_V", "f_bin", "alpha", "MH", "q_gamma"]


class JointModel:
    """把觀測資料與所有固定設定包起來，提供 log_posterior(theta)。"""

    def __init__(self, cfg, obs_color, obs_mag, iso_grid, errmodel, dist_mod):
        c3, c2 = cfg.step3_age, cfg.step2_cmd
        self.cfg = cfg
        self.c3, self.c2 = c3, c2
        self.grid = iso_grid
        self.errmodel = errmodel
        self.dm = dist_mod
        self.ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
        self.n_syn = c3.n_synthetic
        self.crange = tuple(c3.hess_color_range)
        self.mrange = tuple(c3.hess_mag_range)
        self.nb_c, self.nb_m = c3.hess_color_bins, c3.hess_mag_bins
        # ↓ 觀測色光圖只需要切一次 Hess 圖，之後每次比對都重複使用
        self.obs_h = hess(obs_color, obs_mag, self.nb_c, self.nb_m,
                          self.crange, self.mrange)
        self.n_obs = len(obs_color)
        self.g_faint = cfg.step1_membership.g_mag_max
        self.g_bright = c2.g_bright_limit
        self.mh = c3.metallicity_mh
        # 兩個選配的模型成分，預設關閉 -> 行為與加入它們之前完全相同。
        #   dav        差異消光的星對星散布（0 = 全星團單一 A_V）
        #   selection  測光品質篩選的選擇函數（pipeline.selection.SelectionModel）
        #              係數由資料迴歸而得、不進擬合，所以不多出簡併方向
        self.dav = 0.0
        self.selection = None
        # Kroupa 分段冪律 0.08-0.5 Msun 段的冪次。**這段從未參與擬合**——
        # `alpha` 這個自由參數只改 m>0.5 段。實測這段涵蓋 59.5% 的觀測星
        # （641/1078），跟先前「以 M45 金屬量近太陽為由固定金屬量」是同一類
        # 風險（那個代價是 alpha 偏 0.40），但從未做過輪廓測試。
        # 預設 -1.3 與 IMF_BREAKS["kroupa"] 的原始值一致，行為不變；
        # profile_lowmass.py 會覆寫它來測敏感度。
        self.low_mass_slope = -1.3
        # 殘留場星污染的均勻離群成分比例（見 poisson_loglike 的說明）。
        # **這是猜的常數，從未做過敏感度測試**（2026-08-10，LIMITATIONS.md
        # 重新分類為「現役假設」後排進待驗證清單）。與 HR23 的真正判定分歧
        # 20/1078=1.9% 量級相符，但沒驗證過改變它會不會動到 alpha。
        # 預設 0.01 與 poisson_loglike() 原本的預設值一致，行為不變；
        # profile_outlierfrac.py 會覆寫它來測敏感度。
        self.outlier_frac = 0.01
        # 用星體自己的 BP/RP 星等查誤差，而不是用 G 查（見 synthesise()
        # 裡的說明）。**這是猜的簡化，從未驗證過代價**（2026-08-10，
        # LIMITATIONS.md 重新分類為「現役假設」後排進待驗證清單）。
        # 預設 False 與原本行為一致；build_verify_bprperr.py 會把它
        # 打開來跟舊行為 A/B 比較 alpha 有沒有變。
        self.use_native_bprp_err = False
        # C19：自轉調製／前主序光變／黑子造成的額外亮度散布（星等）。
        # 模型完全沒有這一項，這個屬性是為了量「有這種未建模的物理時
        # alpha 會偏多少」的敏感度測試用（見 synthesise() 裡的說明與
        # LIMITATIONS.md C19）。預設 0.0 = 不啟用，行為與加入前
        # 逐位元相同。
        self.extra_scatter = 0.0
        # 差異消光的分布形式（見 synthesise() 裡的完整說明）。**這是猜的
        # 選擇，從未跟其他合理的分布形式比較過代價**（C5，2026-08-14）。
        # 預設 "lognormal" 與原本行為一致；extinction_form_test 會覆寫成
        # "trunc_exp"（截尾指數分布）來跟舊行為 A/B 比較 A_V 系統誤差。
        self.dav_distribution = "lognormal"
        # 共用亂數：整條 MCMC 鏈共用同一批，概似才是參數的確定性函數
        self.draws = draw_randoms(
            self.n_syn, np.random.default_rng(cfg.step1_membership.random_seed))
        # ═══════════════ 核心 1：先驗範圍與預先展開等時線 ═══════════════
        # 先驗範圍。金屬量與 q_gamma 從固定值升格為自由參數 ——
        # 輪廓測試顯示固定它們會讓 alpha 分別偏移 0.40 與 0.10，
        # 是統計誤差 0.003 的 133 倍與 33 倍，不能再當成已知量。
        b = cfg.joint_fit
        # ↓ bounds：6 列 × 2 欄，每一列是一個參數的 [下限, 上限]
        self.bounds = np.array([
            [b.logage_min, b.logage_max],
            [b.av_min, b.av_max],
            [b.fbin_min, b.fbin_max],
            [b.alpha_min, b.alpha_max],
            [b.mh_min, b.mh_max],
            [b.qgamma_min, b.qgamma_max],
        ])
        # ↓ 金屬量高斯先驗的中心與寬度；寬度 0 代表改用均勻先驗
        self._mh_mean = float(b.get("mh_prior_mean", 0.0) or 0.0)
        self._mh_sigma = float(b.get("mh_prior_sigma", 0.0) or 0.0)
        if self._mh_sigma > 0:
            print(f"金屬量先驗：高斯，中心 {self._mh_mean:+.3f}，"
                  f"sigma {self._mh_sigma:.3f}")
        else:
            print(f"金屬量先驗：均勻，{b.mh_min:+.2f} 到 {b.mh_max:+.2f}")
        # 先把先驗範圍內用得到的 isochrone 全部抽出來、排好序、轉成純 numpy。
        # 三個理由：(1) 不必每次取樣都掃過 10 萬列的大表；(2) 不必每次重排序；
        # (3) 多行程平行時只要 pickle 這些小陣列，而不是整張表。
        # 六參數版本要對 (年齡 x 金屬量) 的每個組合都預先取出來。
        # ↓ 網格裡有哪些年齡、金屬量；只保留先驗範圍內（各向外多留 0.06）的
        all_ages = np.unique(np.asarray(iso_grid["logAge"], float))
        all_mh = np.unique(np.asarray(iso_grid["MH"], float))
        alo, ahi = self.bounds[0]
        zlo, zhi = self.bounds[4]
        self._age_keys = all_ages[(all_ages >= alo - 0.06) & (all_ages <= ahi + 0.06)]
        self._mh_keys = all_mh[(all_mh >= zlo - 0.06) & (all_mh <= zhi + 0.06)]
        # 2026-08-10：先驗/搜尋軸曾經比實際下載的網格涵蓋範圍還寬，
        # _isochrone() 的最近鄰吸附會把任何越界請求悄悄黏到同一個邊界格點，
        # 形成看起來像「模型想跑到邊界外」的簡併平坦區（MIST logage 7.80
        # 下限、PARSEC MH +0.336 上限都曾經這樣被誤判成訊號）。與其等人工
        # 逐檔審查才發現，這裡在載入時就把落差印出來，一眼就能看到。
        if all_ages.min() > alo + 1e-9 or all_ages.max() < ahi - 1e-9:
            print(f"警告：logage 搜尋軸 [{alo:.2f}, {ahi:.2f}] 超出網格實際涵蓋 "
                  f"[{all_ages.min():.2f}, {all_ages.max():.2f}]——越界的請求會"
                  f"被吸附到邊界格點，argmax 若落在邊界上很可能是網格覆蓋不足"
                  f"的假象，不是真正的最佳解")
        if all_mh.min() > zlo + 1e-9 or all_mh.max() < zhi - 1e-9:
            print(f"警告：MH 搜尋軸 [{zlo:.2f}, {zhi:.2f}] 超出網格實際涵蓋 "
                  f"[{all_mh.min():.3f}, {all_mh.max():.3f}]——越界的請求會"
                  f"被吸附到邊界格點，argmax 若落在邊界上很可能是網格覆蓋不足"
                  f"的假象，不是真正的最佳解")
        ga = np.asarray(iso_grid["logAge"], float)
        gz = np.asarray(iso_grid["MH"], float)
        gm = np.asarray(iso_grid["Mini"], float)
        cols = [np.asarray(iso_grid[c], float)
                for c in ("G_fSBmag", "G_BP_fSBmag", "G_RP_fSBmag")]
        # ↓ _iso：{(年齡, 金屬量): (質量, G, BP, RP)}，每條都依質量由小到大排好
        self._iso = {}
        for ak in self._age_keys:
            for zk in self._mh_keys:
                sel = (ga == ak) & (gz == zk)
                if sel.sum() < 10:
                    continue
                o = np.argsort(gm[sel])
                self._iso[(float(ak), float(zk))] = (
                    gm[sel][o], cols[0][sel][o], cols[1][sel][o], cols[2][sel][o])
        if not self._iso:
            raise ValueError("先驗範圍內沒有可用的 isochrone，檢查網格檔與 bounds")
        print(f"預先展開 isochrone：{len(self._age_keys)} 個年齡 x "
              f"{len(self._mh_keys)} 個金屬量 = {len(self._iso)} 條")
        self.grid = None      # 大表用不到了，不要跟著 pickle 到子行程

    def _isochrone(self, logage, mh):
        # ↓ 取最接近的年齡格點與金屬量格點（不內插，見 LIMITATIONS.md C14）
        ak = float(self._age_keys[np.argmin(np.abs(self._age_keys - logage))])
        zk = float(self._mh_keys[np.argmin(np.abs(self._mh_keys - mh))])
        return self._iso.get((ak, zk))

    def with_observations(self, obs_color, obs_mag):
        """回傳一個換掉觀測資料、其餘完全共用的模型。

        注入回收測試要對很多批假資料各擬合一次。重建 JointModel 每次都要
        重新展開 240 條 isochrone，很慢；而且重建時若不小心用了別的亂數種子，
        就會變成「用不同的合成星團去擬合不同的假資料」，測到的是亂數差異。
        淺複製保證兩者用的是同一批 isochrone 與同一批共用亂數。
        """
        import copy
        m = copy.copy(self)
        m.obs_h = hess(obs_color, obs_mag, self.nb_c, self.nb_m,
                       self.crange, self.mrange)
        m.n_obs = len(obs_color)
        return m

    def enable_lowmass_fit(self, p_min=0.3, p_max=2.3):
        """把低質量段冪次（0.08-0.5 Msun）升格為自由參數。

        **為什麼要升格而不是用文獻先驗鎖住**：Kroupa (2001) 給的是
        alpha1 = 1.3 +- 0.5，而實測 d(alpha)/d(p) = -0.495 +- 0.111，
        所以那個 +-0.5 會在我們測的 alpha 上造成 0.248 的系統誤差 ——
        是統計誤差 0.144 的 1.7 倍，也是目前最大的單一誤差來源。
        用高斯先驗鎖住並不能消除它（先驗的寬度本身就是誤差來源），
        只有讓資料自己約束才可能縮小。而我們有 641 顆星（59.5%）
        落在這個質量範圍，理論上是有約束力的。

        **但可辨識性必須先驗證**：dav 的教訓是「參數可以放進模型卻完全
        不被資料約束，只會貼著先驗邊界跑」。所以升格前要先用注入回收
        確認它能被回收，不能因為「樣本數多」就假設它可解。

        掃描範圍 0.3-2.3 刻意開得比 Kroupa 的 1.3+-0.5（即 0.8-1.8）寬，
        才能看出資料偏好的值有沒有超出文獻範圍、以及會不會貼牆。
        """
        self.bounds = np.vstack([self.bounds, [[p_min, p_max]]])
        return self._param_names() + ["p_lowmass"]

    def _param_names(self):
        """目前實際啟用的參數名稱（依 bounds 的維度決定）。"""
        names = list(PARAM_NAMES)
        if len(self.bounds) > 6:
            names.append("dav")
        return names

    def enable_dav_fit(self, dav_min=0.0, dav_max=0.8):
        """把差異消光升格為第七個自由參數（擴充 bounds）。

        只有注入回收測試判定它可解之後才該呼叫。沒呼叫時模型仍是六參數。
        """
        self.bounds = np.vstack([self.bounds[:6], [[dav_min, dav_max]]])
        return PARAM_NAMES + ["dav"]

    def set_mass_dependent_fbin(self, contrast, m_break=0.5):
        """讓合成星團的雙星比例隨主星質量變化（**只用於生成假資料**）。

        現況（見 `synthesise()` 第 (2) 步的註解與 `LIMITATIONS.md` D14）：
        決定「誰帶伴星」的 Bernoulli(f_bin) 跟主星質量 m1 完全獨立，等於
        假設雙星比例不隨質量變化。這是已知簡化但從沒量化過代價。這支
        鉤子讓注入端可以生成「雙星比例隨質量變化」的假資料，再用現有的
        常數 f_bin 模型去擬合，量 alpha 被推歪多少。

        **整體雙星比例會被固定住，不隨 contrast 改變**：`contrast` 是
        「重星段的 f_bin 減去輕星段的 f_bin」，兩段各自的值由下式決定，
        使得**樣本加權平均恰好等於原本的 f_bin**：

            f_lo = f_bin - contrast * w_hi
            f_hi = f_bin + contrast * w_lo      （w 是各段的星數比例）

        這樣做是刻意的：如果只是把某一段調高，整體雙星比例會跟著變，
        那就同時動了兩個變因（質量相依性 **與** 整體雙星比例），量到的
        alpha 偏移分不清是哪一個造成的。固定總量才是「只動質量相依性
        這一個變因」。

        contrast=0 時逐位元等同於原本的常數 f_bin 行為（不呼叫這個方法
        也一樣），所以既有結果不受影響。

        參數
        ----
        contrast : float
            f_bin(重) - f_bin(輕)。正值 = 重星比較容易有伴星。
        m_break : float
            分段質量（Msun）。預設 0.5，跟 Kroupa 分段點、以及 `alpha`
            自由參數只控制 m>0.5 段這件事一致。
        """
        self._fbin_contrast = float(contrast)
        self._fbin_m_break = float(m_break)
        return self

    def _effective_fbin(self, fbin, m1):
        """把純量 f_bin 換成逐星的 f_bin（若有設定質量相依性）。

        沒設定時直接回傳原本的純量，呼叫端的比較運算完全不變。
        """
        contrast = getattr(self, "_fbin_contrast", 0.0)
        if not contrast:
            return fbin
        m_break = getattr(self, "_fbin_m_break", 0.5)
        hi = m1 >= m_break
        w_hi = float(hi.mean())
        w_lo = 1.0 - w_hi
        if w_hi == 0.0 or w_lo == 0.0:
            # 全部落在同一段時「兩段」沒有意義，退回常數（不是靜默失敗：
            # 這種情況下質量相依性本來就無從表現，硬算會除出無意義的值）
            return fbin
        f_lo = fbin - contrast * w_hi
        f_hi = fbin + contrast * w_lo
        # contrast 太大會讓機率超界，也會破壞「固定整體 f_bin」的控制變因。
        # 不可偷偷 clip，否則診斷測到的是另一個沒有明說的模型。
        if not (0.0 <= f_lo <= 1.0 and 0.0 <= f_hi <= 1.0):
            raise ValueError(
                "mass-dependent binary fractions fall outside [0, 1]")
        return np.where(hi, f_hi, f_lo)

    # ═══════════════ 核心 2：先驗 ═══════════════
    def log_prior(self, theta):
        nb = len(self.bounds)
        if len(theta) != nb:
            raise ValueError(f"theta 長度 {len(theta)} 與 bounds {nb} 不符")
        # ↓ 任何一個參數超出 [下限, 上限] → 不可能（對數機率 −∞）
        if np.any(theta < self.bounds[:, 0]) or np.any(theta > self.bounds[:, 1]):
            return -np.inf
        # ↓ 範圍內一律平坦（加 0）
        lp = 0.0
        # 金屬量用高斯先驗（若有設定）。均勻先驗的邊界會變成硬牆並決定答案，
        # 高斯先驗則是「大概在這裡，偏離越多越不可能，但沒有絕對禁區」——
        # 資料夠強時仍能把後驗拉離先驗中心。
        if self._mh_sigma > 0:
            # ↓ 高斯先驗的對數：−½ × ((MH − 中心) / 寬度)²
            lp += -0.5 * ((theta[4] - self._mh_mean) / self._mh_sigma) ** 2
        return lp

    # ═══════════════ 核心 3：生成合成星團 ═══════════════
    def synthesise(self, theta, return_binary_flag=False,
                   return_source_index=False):
        """由參數生成合成星團，回傳套用選擇函數後的 (顏色, 星等[, 是否雙星])。

        `return_binary_flag=True` 時多回傳一個布林陣列，標出每顆合成星
        是不是雙星——預設 `False`，行為與加入這個參數前完全相同，現有
        呼叫端不用改。2026-08-11 加入，為了讓 CMD／前向模型的逐星雙星
        判準能對答案（精確率／召回率），之前 `make_fake()` 只回傳
        color/mag，沒辦法驗證這幾種判準本身準不準，只能驗證下游 alpha
        準不準。

        從 log_likelihood 拆出來的，因為「生成合成星團」與「拿它跟觀測比對」
        是兩件獨立的事：同一批合成星可以餵給不同的概似函數
        （分箱的 Poisson-Hess、無分箱的 KDE），比較才是同基準的。
        拆開前若要比較兩種概似，得把生成邏輯抄一份，抄錯就變成在比較兩份不同的
        合成星團而不是兩種概似。
        """
        # ↓ 把前六個參數拆開
        logage, av, fbin, alpha, mh, qgamma = theta[:6]
        # 第七、八個參數都是選配的，長度不足就沿用物件屬性。
        # 這樣六參數與七參數的既有結果與呼叫端完全不受影響。
        #   theta[6] = dav        差異消光的星對星散布
        #   theta[7] = p_lowmass  低質量段（0.08-0.5 Msun）的冪次
        dav = float(theta[6]) if len(theta) > 6 else self.dav
        low_mass = (-float(theta[7]) if len(theta) > 7
                    else getattr(self, "low_mass_slope", -1.3))
        # ↓ 取這組年齡、金屬量的等時線：質量 mi 與三個波段的絕對星等
        iso = self._isochrone(logage, mh)
        if iso is None:
            return None
        mi, gi, bpi, rpi = iso

        # ↓ n：合成星（系統）數；d：預先抽好的亂數
        n = self.n_syn
        d = self.draws
        orig = IMF_BREAKS["kroupa"]
        try:
            # 中間段（0.08-0.5 Msun）用 self.low_mass_slope 而不是 orig[1][1]，
            # 才能被 profile_lowmass.py 覆寫，且透過 Pool initializer 正確
            # 傳給工人行程（工人各自重新 import 模組，不會看到主行程對
            # 模組層級字典的修改，只有跟著 model 一起 pickle 的屬性才會到）。
            #
            # 用 getattr 而非 self.low_mass_slope 直接讀：多行程平行時，
            # 工人 unpickle 一個物件時，方法（synthesise 本身）來自工人
            # **當下從磁碟重新 import** 的類別定義，但屬性值來自主行程
            # pickle 當時的 __dict__。若這支模組在背景工作跑到一半時被
            # 即時修改（新增了這個屬性），舊模型物件的 __dict__ 裡沒有它，
            # 新版 synthesise 卻無條件讀取，就會撞 AttributeError ——
            # 這正是 2026-08-08 讓 p2_final 中途失敗的原因。
            # low_mass 已在函式開頭決定（可能來自 theta[7] 或物件屬性）。
            # ↓ 暫時改寫 Kroupa 的三段冪次：最低段維持原值、中段 = 低質量段冪次、
            #   高質量段 = −α（存的是 dN/dm 的冪次，斜率 α 對應冪次 −α）
            IMF_BREAKS["kroupa"] = (orig[0], [orig[1][0], low_mass, -alpha])
            # **這裡抽的是「主星」質量，不是「所有恆星」的質量**（D14，
            # 見下面 is_bin 那段與本方法末尾的說明）。抽樣範圍是等時線網格
            # 實際涵蓋的質量區間（mi.min()–mi.max()），不是 config 設定值——
            # 換一份質量涵蓋較窄的網格（例如 BHAC15 只到 1.4 Msun）會連帶
            # 改變被抽樣的質量上限，比較不同網格的結果時要記得這一點。
            # ↓ 用預抽的均勻亂數 u_mass，依這個 IMF 逆變換抽出 n 個主星質量
            m1 = sample_imf(d["u_mass"][:n], "kroupa", mi.min(), mi.max())
        finally:
            IMF_BREAKS["kroupa"] = orig

        # ↓ 由主星質量在等時線上內插出三個波段的絕對星等
        g = np.interp(m1, mi, gi)
        bp = np.interp(m1, mi, bpi)
        rp = np.interp(m1, mi, rpi)

        # **合成星團的一「筆」是一個系統，不是一顆恆星**（D14）。抽樣順序是：
        #   (1) 抽 n_syn 個主星質量 m1（冪次由 alpha 決定，見上面）
        #   (2) 獨立地擲 Bernoulli(f_bin) 決定哪些主星帶伴星
        #   (3) 伴星質量 m2 = q*m1，q 抽自 p(q) ∝ q^qgamma，**不是抽自 IMF**
        #   (4) 主星與伴星的**流量相加**，塌縮成同一筆測光點
        # 所以 alpha 是**主星質量分布**的冪次（等價於以主星質量標記的
        # system MF），不是把伴星也算進去的 stellar／single-star MF。
        # 要換算成 stellar MF 必須把 f_bin 與 q 分布一起摺積回去，那是
        # 一個後處理步驟，這裡沒有做，報出來的 alpha 也不是那個東西。
        # 另外第 (2) 步與 m1 獨立，等於假設**雙星比例不隨質量變化**——
        # 這是已知的簡化，不是疏忽（見 LIMITATIONS.md）。
        # A diagnostic may set ``binary_fraction_profile`` to
        # ``(mass_break, f_below, f_above)``.  This deliberately affects only
        # synthetic *injections*: normal production fits do not set it and
        # therefore retain the original mass-independent Bernoulli(f_bin).
        # Keeping this switch on the model rather than adding a fitted theta
        # parameter prevents a diagnostic from silently changing the headline
        # model.
        binary_profile = getattr(self, "binary_fraction_profile", None)
        binary_contrast = getattr(self, "binary_fraction_contrast", None)
        if binary_contrast is not None:
            mass_break, contrast = map(float, binary_contrast)
            if not (mi.min() < mass_break < mi.max()):
                raise ValueError("binary_fraction_contrast mass break is outside the isochrone")
            hi = m1 >= mass_break
            w_hi = float(hi.mean())
            w_lo = 1.0 - w_hi
            f_below = fbin - contrast * w_hi
            f_above = fbin + contrast * w_lo
            if not (0.0 <= f_below <= 1.0 and 0.0 <= f_above <= 1.0):
                raise ValueError("mass-dependent binary fractions fall outside [0, 1]")
            p_bin = np.where(hi, f_above, f_below)
        elif binary_profile is None:
            # Main's supported diagnostic API.  With no diagnostic setting,
            # _effective_fbin returns the original scalar fbin unchanged.
            p_bin = self._effective_fbin(fbin, m1)
        else:
            mass_break, f_below, f_above = map(float, binary_profile)
            if not (mi.min() < mass_break < mi.max()):
                raise ValueError("binary_fraction_profile mass break is outside the isochrone")
            if not (0.0 <= f_below <= 1.0 and 0.0 <= f_above <= 1.0):
                raise ValueError("binary_fraction_profile fractions must be in [0, 1]")
            p_bin = np.where(m1 < mass_break, f_below, f_above)
        # ↓ 每個系統擲一次骰：預抽亂數 u_bin < 雙星機率 → 這個系統帶伴星
        is_bin = d["u_bin"][:n] < p_bin
        if is_bin.any():
            # ↓ 帶伴星的系統，用預抽亂數 u_q 抽質量比 q
            u = d["u_q"][:n][is_bin]
            qg, qm = qgamma, self.c3.binary_q_min
            # ↓ 逆變換抽樣：讓 q 在 [q_min, 1] 之間服從 p(q) ∝ q^q_gamma
            #   （q_gamma = −1 時公式分母為 0，改用對數均勻的特例）
            if abs(qg + 1) < 1e-9:
                q = qm * (1.0 / qm) ** u
            else:
                q = (qm ** (qg + 1) + u * (1.0 - qm ** (qg + 1))) ** (1.0 / (qg + 1))
            # ↓ 伴星質量 = q × 主星質量，不低於等時線最小質量
            m2 = np.clip(m1[is_bin] * q, mi.min(), None)
            for arr, tab in ((g, gi), (bp, bpi), (rp, rpi)):
                # ↓ 伴星的絕對星等
                second = np.interp(m2, mi, tab)
                # ↓ 未解析雙星 = 一個光點：星等換成流量 10^(−0.4 m)，兩顆相加，
                #   再換回星等 −2.5 log10(總流量)
                arr[is_bin] = -2.5 * np.log10(
                    10 ** (-0.4 * arr[is_bin]) + 10 ** (-0.4 * second))

        # 差異消光：每顆星有自己的 A_V。dav = 0 時 av_i 是純量，
        # 運算結果與加入這段之前逐位元相同。
        #
        # **不能用截斷常態 max(0, A_V + dav*z)。** 實測過（注入回收 S4）：
        # 截斷讓實際平均變成 A_V 與 dav 的混合函數，於是 A_V=0 配大的 dav
        # 可以完美模仿 A_V=0.15 配小的 dav —— 擬合把 A_V 推到 0 貼牆，
        # dav 則從真值 0.30 overshoot 到 0.45。兩者不可分離。
        #
        # 改用對數常態：平均恰為 A_V、標準差恰為 dav、恆正、不需截斷。
        # 關鍵是 A_V -> 0 時整個分布跟著 -> 0，dav 再大也變不出消光來，
        # 這在結構上就切斷了那條簡併。物理上也合理：塵埃是沿視線的
        # 乘性遮蔽，對數常態比常態更貼近。
        # 用 getattr 而非 self.dav_distribution 直接讀，理由跟上面
        # low_mass_slope 那段一樣（2026-08-08 讓 p2_final 中途失敗的
        # AttributeError race condition）：多行程 worker unpickle 到的
        # 物件屬性值來自主行程 pickle 當時的 __dict__，若這個屬性是背景
        # 工作跑到一半時才新增的，舊物件的 __dict__ 裡沒有它，直接讀會
        # 拋 AttributeError。2026-08-14 的 p6b4 補測任務就是撞到這個
        # class 的 bug（見 WORK_BOARD.md），當時是另一個屬性但同一個
        # 成因，這裡順手把 dav_distribution 也改成防禦性寫法。
        dav_distribution = getattr(self, "dav_distribution", "lognormal")
        # ↓ 沒有差異消光（正式設定）→ 全部星用同一個 A_V
        if dav <= 0 or av < 1e-6:
            av_i = av
        elif dav_distribution == "trunc_exp":
            # C5 替代分布（系統誤差比較用，見 LIMITATIONS.md C5）：截尾
            # 指數分布，scale **恆為 dav**（不像 2026-08-14 第一版那樣在
            # av<dav 時偷偷把 scale 換成 av——那個版本會讓「dav 這個展寬
            # 參數」在 av<dav 時完全不影響生成的樣本，等於在測試最想看的
            # 「dav 遠大於 av」這個區間時，trunc_exp 這條線根本沒有真的
            # 用到那個 dav，比較會失去意義。CodeRabbit review 抓到這個
            # 問題，這裡改成一律 scale=dav、location 可以是負的，對負值做
            # 真正的截尾（夾到 0），這才是「截尾指數分布」字面上的意思。
            # 用同一個 z_av（標準常態）先轉成 U(0,1) 再反解指數分布的 CDF，
            # 維持「同一組共用亂數 -> 概似是參數的確定性函數」這個前提，
            # 不能另外重新抽樣。
            #
            # **location 要做均值校正**（2026-08-19 CodeRabbit PR #63）：
            # 第二版一律用 loc = av - dav，av >= dav 時沒問題（沒有任何值
            # 被截到，平均恰為 av），但 av < dav 時有一部分機率質量被截到
            # 剛好 0，平均會**高於** av。當時的註解把這說成「物理上合理」，
            # 那個說法在單獨看一條分布時成立，放進 C5 這個比較裡卻是錯的：
            # C5 要量的是「分布形狀」造成的系統誤差，若 trunc_exp 與
            # lognormal 在同一組 (av, dav) 下平均 A_V 不同，量到的差就混進
            # 了「平均消光不同」這個混淆因子，分不出哪一部分是形狀造成的。
            # 實測偏差不小：av=0.15、dav=1.20 時舊寫法的平均是 0.50 而非
            # 0.15，等於把 dav 掃描偷偷變成平均消光掃描。
            #
            # 令 X = loc + Exp(scale=dav)、Y = max(X, 0)，解 E[Y] = av：
            #   loc >= 0：整條分布都在正半軸，E[Y] = loc + dav
            #             -> loc = av - dav（av >= dav 時適用，與舊版相同）
            #   loc <  0：P(X>0) = exp(loc/dav)，指數分布無記憶性使得
            #             (X | X>0) ~ Exp(dav)，故 E[Y] = dav*exp(loc/dav)
            #             -> loc = dav*ln(av/dav)（av < dav 時適用）
            # 兩式在 av == dav 交會於 loc = 0，連續；av >= dav 的既有結果
            # 逐位元不變，只有 av < dav 那一段被修正。0 這個離散質量點仍然
            # 保留（消光本來就不能是負的），只是不再連帶把平均推高。
            u = norm.cdf(d["z_av"][:n])
            loc = av - dav if av >= dav else dav * np.log(av / dav)
            av_i = np.clip(loc - dav * np.log1p(-u), 0.0, None)
        else:
            # ↓ 對數常態：選 s2 讓分布的平均恰為 A_V、標準差恰為 dav，
            #   再用預抽的常態亂數 z_av 產生每顆星自己的消光
            s2 = np.log1p((dav / av) ** 2)
            av_i = np.exp(np.log(av) - 0.5 * s2
                          + np.sqrt(s2) * d["z_av"][:n])
        # ↓ 絕對星等 → 視星等：加距離模數，再加各波段的消光（係數 × A_V）
        g += self.dm + self.ext.g * av_i
        bp += self.dm + self.ext.bp * av_i
        rp += self.dm + self.ext.rp * av_i

        # C19 敏感度測試：自轉調製／前主序光變／黑子造成的額外亮度散布。
        # 模型本身完全沒有這一項（見 LIMITATIONS.md C19），這裡不是要
        # 「把它建模進去」，而是要量「真的存在這種未建模物理時，alpha
        # 會被推多少」——掃過幾個散布量級跑注入回收，得到敏感度曲線。
        #
        # **刻意用同一個 z_var 加到三個波段**（消色差、純垂直方向的
        # CMD 模糊化），不是三個波段各抽一次：黑子/自轉調製的實際效應
        # 確實有顏色相依（變暗時偏紅），但那需要多一個「顏色振幅比」
        # 參數，而這個測試要回答的是「光度散布本身對冪律 MLE 的影響」——
        # IMF 斜率是從光度分布量出來的，垂直方向的模糊化才是主效應。
        # **這個簡化是已知限制，不是疏漏**：這條敏感度曲線只涵蓋消色差
        # 那一半，顏色方向的效應沒有測到，解讀時不能宣稱涵蓋全部。
        #
        # 加在測光誤差**之前**：光變是天體本身的亮度變化，Gaia 的測光
        # 誤差是在那之上再疊加的觀測誤差，次序反過來在物理上說不通
        # （雖然兩個都是高斯、對最終散布量級的影響相同，但選擇函數與
        # g_faint 截斷是對「觀測到的星等」作用的，次序會影響哪些星被
        # 截掉，所以不是純粹的形式問題）。
        extra_scatter = getattr(self, "extra_scatter", 0.0)
        if extra_scatter > 0:
            dvar = d["z_var"][:n] * extra_scatter
            g += dvar
            bp += dvar
            rp += dvar

        # ↓ 加 G 測光誤差：預抽常態亂數 z_g × 該星等的誤差（errmodel 內插）
        g += d["z_g"][:n] * _interp_err(g, self.errmodel, "e_g")
        # **已知現役缺陷**：用 G 查 BP/RP 的誤差。同一個 G 之下紅星的 BP
        # 暗得多，用 G 查等於用一個比真實 BP 星等亮的值去查，會低估紅星
        # 的 BP 誤差。`self.use_native_bprp_err=True` 時改用星體自己的
        # （加消光後、加誤差前的）BP/RP 星等去查各自波段的誤差曲線，
        # 需要 errmodel 裡有 `pipeline.step2_cmd.photometric_error_model()`
        # 2026-08-10 新增的 "bp"/"e_bp_native"/"rp"/"e_rp_native" 鍵，
        # 沒有就自動退回舊行為（舊快取的 errmodel.npz 不會炸掉）。
        if (getattr(self, "use_native_bprp_err", False)
                and "e_bp_native" in self.errmodel):
            em = self.errmodel
            e_bp_val = np.interp(bp, em["bp"], em["e_bp_native"],
                                 left=em["e_bp_native"][0],
                                 right=em["e_bp_native"][-1])
            e_rp_val = np.interp(rp, em["rp"], em["e_rp_native"],
                                 left=em["e_rp_native"][0],
                                 right=em["e_rp_native"][-1])
            bp += d["z_bp"][:n] * e_bp_val
            rp += d["z_rp"][:n] * e_rp_val
        else:
            # ↓ 正式設定走這裡：BP、RP 的誤差也用 G 星等去查（見上方說明的已知缺陷）
            bp += d["z_bp"][:n] * _interp_err(g, self.errmodel, "e_bp")
            rp += d["z_rp"][:n] * _interp_err(g, self.errmodel, "e_rp")

        # ↓ 只留跟觀測同樣星等範圍的星：4 ≤ G ≤ 18
        keep = (g <= self.g_faint) & (g >= self.g_bright)
        # 測光品質篩選：第 2 步把 1,297 顆砍到 1,078，而且**不是隨機砍的** ——
        # G>=17 的紅星被砍掉 59%、藍星只有 20%，因為 BP 訊噪比那一刀對
        # 同星等的紅星特別不利。模型不套用同一組篩選，就會生出觀測裡已經
        # 被砍掉的暗紅星，擬合只好改 alpha 去補 —— 直接偏誤要測的量。
        if self.selection is not None:
            keep &= self.selection.keep(g, bp, rp,
                                        d["z_snr"][:n], d["u_sel"][:n])
        # ↓ 剩不到 50 顆代表這組參數生成不出像樣的星團，回傳 None（概似 −∞）
        if keep.sum() < 50:
            return None
        if return_source_index:
            return (bp - rp)[keep], g[keep], is_bin[keep], np.flatnonzero(keep)
        if return_binary_flag:
            return (bp - rp)[keep], g[keep], is_bin[keep]
        # ↓ 正式用法：回傳合成星的顏色 (BP−RP) 與 G 星等
        return (bp - rp)[keep], g[keep]

    # ═══════════════ 核心 4：概似與後驗 ═══════════════
    def log_likelihood(self, theta):
        """給定六個參數，生成合成星團並與觀測 CMD 比對。"""
        # ↓ 生成合成星團；生成失敗 → −∞
        syn = self.synthesise(theta)
        if syn is None:
            return -np.inf
        # ↓ 合成星切成 Hess 圖（格子跟觀測一樣）
        mod_h = hess(syn[0], syn[1], self.nb_c, self.nb_m,
                     self.crange, self.mrange,
                     smooth=self.c3.model_hess_smooth)
        # ↓ 逐格比較觀測與合成的星數分布，回傳 Poisson 對數概似
        return poisson_loglike(self.obs_h, mod_h, self.n_obs,
                               outlier_frac=getattr(self, "outlier_frac", 0.01))

    def log_posterior(self, theta):
        # ↓ 對數後驗 = 對數先驗 + 對數概似；先驗不合格就不必生成星團
        lp = self.log_prior(theta)
        if not np.isfinite(lp):
            return -np.inf
        ll = self.log_likelihood(theta)
        return lp + ll if np.isfinite(ll) else -np.inf


# 多行程平行時，模型只在工人啟動時送一次，之後靠模組層級的全域變數取用。
#
# 若直接把 model.log_posterior 這個綁定方法交給 pool.map，Python 會在**每一步**
# 把整個 JointModel 打包送給每個工人 —— 240 條 isochrone 加上 24 萬個預抽亂數
# 約 4 MB，兩萬步下來是幾百 GB 的搬運量。實測症狀是主行程吃滿而工人各只有
# 20% 上下、整機 CPU 只到 50%：工人都在等資料，不是在算。
_WORKER_MODEL: "JointModel | None" = None


def _init_worker(model):
    global _WORKER_MODEL
    _WORKER_MODEL = model


def _worker_logpost(theta):
    return _WORKER_MODEL.log_posterior(theta)


def make_pool(model, n_proc):
    """建立已經把模型送進去的行程池。"""
    from multiprocessing import Pool
    return Pool(n_proc, initializer=_init_worker, initargs=(model,))


# ═══════════════ 核心 5：MCMC 取樣 ═══════════════
def run_mcmc(model: JointModel, n_walkers: int, n_steps: int, n_burn: int,
             start: np.ndarray, seed: int, progress: bool = True,
             pool=None, moves=None):
    """跑 emcee。start 是 PARAM_NAMES 六個參數的起始點（通常用循序擬合的結果）。

    pool 可傳入 multiprocessing.Pool 做平行取樣。
    moves 預設用 DEMove + DESnookerMove 的組合，比 emcee 內建的 StretchMove
    更適合有相關性的參數；StretchMove 在強相關的後驗上接受率會很低。
    （A_V 與 alpha 的相關係數目前沒有可引用的值：不同鏈長給出
    +0.66／−0.05／−0.22，是鏈未收斂的產物，見 docs/reference/REFUTED.md。）
    """
    import emcee

    # ↓ ndim：參數個數（6）
    ndim = len(PARAM_NAMES)
    rng = np.random.default_rng(seed)
    # 在起始點附近撒開走者，但不能撒到先驗範圍外
    span = (model.bounds[:, 1] - model.bounds[:, 0]) * 0.05
    p0 = start + rng.normal(0, span, size=(n_walkers, ndim))
    p0 = np.clip(p0, model.bounds[:, 0] + 1e-6, model.bounds[:, 1] - 1e-6)

    if moves is None:
        moves = [(emcee.moves.DEMove(), 0.8),
                 (emcee.moves.DESnookerMove(), 0.2)]
    # 有 pool 時用模組層級函式（工人已持有模型），沒有才用綁定方法
    fn = _worker_logpost if pool is not None else model.log_posterior
    # ↓ 建立取樣器：n_walkers 個走者、ndim 維、目標函數 fn（對數後驗）
    sampler = emcee.EnsembleSampler(n_walkers, ndim, fn,
                                    pool=pool, moves=moves)
    # ↓ 每個走者從 p0 出發走 n_steps 步
    sampler.run_mcmc(p0, n_steps, progress=progress)

    # ↓ 丟掉前 n_burn 步暖身，把所有走者的樣本攤平成一張表（每列一組參數）
    chain = sampler.get_chain(discard=n_burn, flat=True)
    logp = sampler.get_log_prob(discard=n_burn, flat=True)
    # ↓ 自相關時間 τ：相隔幾步的樣本才算「互相獨立」。鏈長要遠大於 τ
    #   （常用 50 倍）才算收斂；這個模型實測 τ 達 822–1454，遠不夠
    try:
        tau = sampler.get_autocorr_time(quiet=True)
    except Exception:
        tau = np.full(ndim, np.nan)
    # ↓ acceptance：所有走者「提議的下一步被接受」的平均比例
    #   best：樣本裡對數後驗最高的那一組參數
    return {"chain": chain, "logp": logp, "tau": tau,
            "acceptance": float(np.mean(sampler.acceptance_fraction)),
            "best": chain[int(np.argmax(logp))]}


def summarise(chain: np.ndarray) -> dict:
    """回傳每個參數的中位數與 16/84 百分位。"""
    out = {}
    for i, name in enumerate(PARAM_NAMES):
        q = np.percentile(chain[:, i], [16, 50, 84])
        out[name] = {"median": float(q[1]), "lo": float(q[0]),
                     "hi": float(q[2]),
                     "minus": float(q[1] - q[0]), "plus": float(q[2] - q[1])}
    return out


def correlation_matrix(chain: np.ndarray) -> np.ndarray:
    """參數之間的相關係數 —— 這正是循序擬合看不到的東西。"""
    return np.corrcoef(chain.T)
