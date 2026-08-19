# -*- coding: utf-8 -*-
"""四參數聯合擬合：年齡、消光、雙星比例、IMF 斜率一次解出。

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
"""
from __future__ import annotations

import numpy as np

from . import isochrones as iso_mod
from .step3_age import (IMF_BREAKS, _Ext, _interp_err, draw_randoms, hess,
                        poisson_loglike, sample_imf)

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
        # 共用亂數：整條 MCMC 鏈共用同一批，概似才是參數的確定性函數
        self.draws = draw_randoms(
            self.n_syn, np.random.default_rng(cfg.step1_membership.random_seed))
        # 先驗範圍。金屬量與 q_gamma 從固定值升格為自由參數 ——
        # 輪廓測試顯示固定它們會讓 alpha 分別偏移 0.40 與 0.10，
        # 是統計誤差 0.003 的 133 倍與 33 倍，不能再當成已知量。
        b = cfg.joint_fit
        self.bounds = np.array([
            [b.logage_min, b.logage_max],
            [b.av_min, b.av_max],
            [b.fbin_min, b.fbin_max],
            [b.alpha_min, b.alpha_max],
            [b.mh_min, b.mh_max],
            [b.qgamma_min, b.qgamma_max],
        ])
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

    def log_prior(self, theta):
        nb = len(self.bounds)
        if len(theta) != nb:
            raise ValueError(f"theta 長度 {len(theta)} 與 bounds {nb} 不符")
        if np.any(theta < self.bounds[:, 0]) or np.any(theta > self.bounds[:, 1]):
            return -np.inf
        lp = 0.0
        # 金屬量用高斯先驗（若有設定）。均勻先驗的邊界會變成硬牆並決定答案，
        # 高斯先驗則是「大概在這裡，偏離越多越不可能，但沒有絕對禁區」——
        # 資料夠強時仍能把後驗拉離先驗中心。
        if self._mh_sigma > 0:
            lp += -0.5 * ((theta[4] - self._mh_mean) / self._mh_sigma) ** 2
        return lp

    def synthesise(self, theta, return_binary_flag=False):
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
        logage, av, fbin, alpha, mh, qgamma = theta[:6]
        # 第七、八個參數都是選配的，長度不足就沿用物件屬性。
        # 這樣六參數與七參數的既有結果與呼叫端完全不受影響。
        #   theta[6] = dav        差異消光的星對星散布
        #   theta[7] = p_lowmass  低質量段（0.08-0.5 Msun）的冪次
        dav = float(theta[6]) if len(theta) > 6 else self.dav
        low_mass = (-float(theta[7]) if len(theta) > 7
                    else getattr(self, "low_mass_slope", -1.3))
        iso = self._isochrone(logage, mh)
        if iso is None:
            return None
        mi, gi, bpi, rpi = iso

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
            IMF_BREAKS["kroupa"] = (orig[0], [orig[1][0], low_mass, -alpha])
            m1 = sample_imf(d["u_mass"][:n], "kroupa", mi.min(), mi.max())
        finally:
            IMF_BREAKS["kroupa"] = orig

        g = np.interp(m1, mi, gi)
        bp = np.interp(m1, mi, bpi)
        rp = np.interp(m1, mi, rpi)

        is_bin = d["u_bin"][:n] < fbin
        if is_bin.any():
            u = d["u_q"][:n][is_bin]
            qg, qm = qgamma, self.c3.binary_q_min
            if abs(qg + 1) < 1e-9:
                q = qm * (1.0 / qm) ** u
            else:
                q = (qm ** (qg + 1) + u * (1.0 - qm ** (qg + 1))) ** (1.0 / (qg + 1))
            m2 = np.clip(m1[is_bin] * q, mi.min(), None)
            for arr, tab in ((g, gi), (bp, bpi), (rp, rpi)):
                second = np.interp(m2, mi, tab)
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
        if dav <= 0 or av < 1e-6:
            av_i = av
        else:
            s2 = np.log1p((dav / av) ** 2)
            av_i = np.exp(np.log(av) - 0.5 * s2
                          + np.sqrt(s2) * d["z_av"][:n])
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
            bp += d["z_bp"][:n] * _interp_err(g, self.errmodel, "e_bp")
            rp += d["z_rp"][:n] * _interp_err(g, self.errmodel, "e_rp")

        keep = (g <= self.g_faint) & (g >= self.g_bright)
        # 測光品質篩選：第 2 步把 1,297 顆砍到 1,078，而且**不是隨機砍的** ——
        # G>=17 的紅星被砍掉 59%、藍星只有 20%，因為 BP 訊噪比那一刀對
        # 同星等的紅星特別不利。模型不套用同一組篩選，就會生出觀測裡已經
        # 被砍掉的暗紅星，擬合只好改 alpha 去補 —— 直接偏誤要測的量。
        if self.selection is not None:
            keep &= self.selection.keep(g, bp, rp,
                                        d["z_snr"][:n], d["u_sel"][:n])
        if keep.sum() < 50:
            return None
        if return_binary_flag:
            return (bp - rp)[keep], g[keep], is_bin[keep]
        return (bp - rp)[keep], g[keep]

    def log_likelihood(self, theta):
        """給定六個參數，生成合成星團並與觀測 CMD 比對。"""
        syn = self.synthesise(theta)
        if syn is None:
            return -np.inf
        mod_h = hess(syn[0], syn[1], self.nb_c, self.nb_m,
                     self.crange, self.mrange,
                     smooth=self.c3.model_hess_smooth)
        return poisson_loglike(self.obs_h, mod_h, self.n_obs,
                               outlier_frac=getattr(self, "outlier_frac", 0.01))

    def log_posterior(self, theta):
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


def run_mcmc(model: JointModel, n_walkers: int, n_steps: int, n_burn: int,
             start: np.ndarray, seed: int, progress: bool = True,
             pool=None, moves=None):
    """跑 emcee。start 是四個參數的起始點（通常用循序擬合的結果）。

    pool 可傳入 multiprocessing.Pool 做平行取樣。
    moves 預設用 DEMove + DESnookerMove 的組合，比 emcee 內建的 StretchMove
    更適合有相關性的參數（我們的 A_V 與 alpha 相關係數達 0.66）；
    StretchMove 在強相關的後驗上接受率會很低。
    """
    import emcee

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
    sampler = emcee.EnsembleSampler(n_walkers, ndim, fn,
                                    pool=pool, moves=moves)
    sampler.run_mcmc(p0, n_steps, progress=progress)

    chain = sampler.get_chain(discard=n_burn, flat=True)
    logp = sampler.get_log_prob(discard=n_burn, flat=True)
    try:
        tau = sampler.get_autocorr_time(quiet=True)
    except Exception:
        tau = np.full(ndim, np.nan)
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
