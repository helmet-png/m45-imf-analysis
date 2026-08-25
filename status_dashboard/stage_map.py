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
"""
from __future__ import annotations

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
                    "nbody_pdmf_smoke.py",
                    "nbody_pdmf_ensemble.py",
                    "petar_pdmf_analysis.py",
                    "petar_pdmf_ensemble.py",
                ],
                "queue_labels": ["nbody_prior_from_radial"],
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
                # 實際派工用的標籤是 c5_davform_truncexp（截尾指數分布這個
                # 變體），不是 WORK_BOARD.md 的任務名稱本身——跟 D2 同一種
                # 「任務名稱≠真正佇列標籤」的坑，2026-08-25 對照
                # cloud_queue.txt 實際內容訂正。
                "queue_labels": ["c5_davform_truncexp"],
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
                "scripts": [
                    "scripts/diagnostics/inject_mass_dependent_fbin.py",
                    "scripts/diagnostics/summarize_mass_dependent_fbin.py",
                ],
                "queue_labels": ["mass_dependent_fbin"],
            },
            {
                "name": "praesepe_pr11_close_out（D8、A5）Praesepe 多星團驗證收尾",
                "scripts": [
                    "scripts/multicluster/cluster_imf_tier1.py",
                    "cluster_forward_validation.py",
                ],
                "note": "含 PR #11 審查，狀態不只看腳本，也要看 PR 是否合併。",
            },
            {
                "name": "comaber_tier1（A5、D8）Coma Berenices 多星團驗證",
                "scripts": [
                    "scripts/multicluster/cluster_imf_tier1.py",
                    "prepare_cluster_tier2.py",
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
