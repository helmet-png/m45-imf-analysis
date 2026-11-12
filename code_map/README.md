<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->

# 程式地圖

這個資料夾回答「這麼多程式，彼此是什麼關係」。檔案沒有搬動；每支程式在 [`catalog.json`](catalog.json) 裡貼了五種標籤，下面每一頁是同一份登記的不同排法。

## 從哪裡開始看

- [資料流程圖](FLOW.md)：誰的輸出是誰的輸入
- [每支程式的上下游](views/relations.md)：讀、寫、import、被誰 import
- [依資料流順序](views/by_order.md)
- [依角色](views/by_role.md)
- [依方法](views/by_method.md)
- [依層級](views/by_layer.md)
- [依可信度](views/by_trust.md)

## 結論

- [前向模型的質量函數斜率 α（M45，0.5 M☉ 以上）](claims/alpha_forward.md)：α = 2.382

## 登記進度

已登記 19 支，尚未登記 123 支（`_archive/` 與 `__init__.py` 不計）。

找不到來源的輸入檔（產生它的程式多半還沒登記）：

- `runs_training/*/observed.stats.json`，由 `scripts/nbody_petar/emulator_fit.py` 讀取

<details><summary>尚未登記的程式</summary>

- `gcp_vm_lifecycle.py`
- `iap_tunnel_manager.py`
- `inject_lowmass.py`
- `inject_massdep_fbin.py`
- `kaggle_accounts.py`
- `kaggle_queue.py`
- `kaggle_smoketest.py`
- `kaggle_sync.py`
- `measure_overconfidence.py`
- `nbody_setup/analyze_alpha_r.py`
- `pipeline/bhac.py`
- `pipeline/config.py`
- `pipeline/mist.py`
- `pipeline/net.py`
- `pipeline/selection.py`
- `pipeline/step2_cmd.py`
- `pipeline/step3_age.py`
- `pipeline/step4_binaries.py`
- `pipeline/table_compat.py`
- `profile_outlierfrac.py`
- `run_queue.py`
- `scripts/data_prep/build_bhac_grid.py`
- `scripts/data_prep/build_dr2_grid.py`
- `scripts/data_prep/build_mist_grid.py`
- `scripts/data_prep/fetch_hr23_lost_photometry.py`
- `scripts/data_prep/fetch_m45_field_public_tap.py`
- `scripts/data_prep/gaia_astrophys.py`
- `scripts/data_prep/gaia_radial_velocity.py`
- `scripts/diagnostics/analyze_d19_membership_reliability.py`
- `scripts/diagnostics/analyze_lowmass.py`
- `scripts/diagnostics/assess_colour_options.py`
- `scripts/diagnostics/assess_stickout_fraction.py`
- `scripts/diagnostics/audit_gaia_astrometric_covariance.py`
- `scripts/diagnostics/build_bp15_selection_smoke.py`
- `scripts/diagnostics/build_m45_control_field.py`
- `scripts/diagnostics/check_bp15_candidate_cmd_sides.py`
- `scripts/diagnostics/check_bright_outlier_kinematics.py`
- `scripts/diagnostics/check_c20_disagree_set.py`
- `scripts/diagnostics/check_giant_subgiant_contamination.py`
- `scripts/diagnostics/check_hr23_cmd_recall.py`
- `scripts/diagnostics/check_imf_form.py`
- `scripts/diagnostics/check_massrange_crosscal.py`
- `scripts/diagnostics/check_nebula_colour_robustness.py`
- `scripts/diagnostics/check_poisson_vs_multinomial.py`
- `scripts/diagnostics/check_rv_binary_fraction.py`
- `scripts/diagnostics/check_selection_color_residual.py`
- `scripts/diagnostics/check_wd_exclusion_impact.py`
- `scripts/diagnostics/check_white_dwarf_contamination.py`
- `scripts/diagnostics/compare_bp15_candidate_color_errors.py`
- `scripts/diagnostics/compare_lowmass_isochrones.py`
- `scripts/diagnostics/completeness.py`
- `scripts/diagnostics/crosscheck_hr23_bright_stars.py`
- `scripts/diagnostics/d19_completeness_injection.py`
- `scripts/diagnostics/d19_full_membership_run.py`
- `scripts/diagnostics/diagnose_m45_bright_end_loss.py`
- `scripts/diagnostics/diagnose_ngc3532_selection_colour.py`
- `scripts/diagnostics/diagnose_praesepe_cmd_residual.py`
- `scripts/diagnostics/dynamics_estimate.py`
- `scripts/diagnostics/estimate_lowmass_precision.py`
- `scripts/diagnostics/finalize_limepy_radial_crosscheck.py`
- `scripts/diagnostics/finalize_lowmass_recovery.py`
- `scripts/diagnostics/inject_mass_dependent_fbin.py`
- `scripts/diagnostics/limepy_multimass.py`
- `scripts/diagnostics/limepy_radial_crosscheck.py`
- `scripts/diagnostics/map_bp15_candidates_to_mass.py`
- `scripts/diagnostics/prepare_bp15_paired_dispatch.py`
- `scripts/diagnostics/profile_test.py`
- `scripts/diagnostics/pyupmask_feasibility.py`
- `scripts/diagnostics/quantify_bp15_sample_scale.py`
- `scripts/diagnostics/replay_hr23_lost_quality_cuts.py`
- `scripts/diagnostics/selection_probe.py`
- `scripts/diagnostics/sensitivity_sweep.py`
- `scripts/diagnostics/summarize_bp15_formal_paired.py`
- `scripts/diagnostics/summarize_bp15_forward_smoke.py`
- `scripts/diagnostics/summarize_free_lowmass_recovery.py`
- `scripts/diagnostics/summarize_mass_dependent_fbin.py`
- `scripts/diagnostics/sweep_hr23_lost_quality_thresholds.py`
- `scripts/diagnostics/system_vs_stellar_mf.py`
- `scripts/diagnostics/trace_hr23_recall_stages.py`
- `scripts/diagnostics/verify_binary_detection.py`
- `scripts/drivers/run_joint.py`
- `scripts/multicluster/cluster_forward_validation.py`
- `scripts/multicluster/cluster_imf_tier1.py`
- `scripts/multicluster/final_imf.py`
- `scripts/multicluster/prepare_cluster_tier2.py`
- `scripts/nbody_petar/build_m45_system_bridges.py`
- `scripts/nbody_petar/build_training_stats.py`
- `scripts/nbody_petar/emulator_holdout_check.py`
- `scripts/nbody_petar/emulator_infer.py`
- `scripts/nbody_petar/energy_bulk_correction.py`
- `scripts/nbody_petar/kaggle_nbody_smoke.py`
- `scripts/nbody_petar/m45_orbit_init.py`
- `scripts/nbody_petar/nbody_pdmf_ensemble.py`
- `scripts/nbody_petar/nbody_pdmf_smoke.py`
- `scripts/nbody_petar/nbody_summary_stats.py`
- `scripts/nbody_petar/observe_snapshot.py`
- `scripts/nbody_petar/pdmf_limepy_bootstrap.py`
- `scripts/nbody_petar/pdmf_limepy_smoke.py`
- `scripts/nbody_petar/pdmf_system_definition_bridge.py`
- `scripts/nbody_petar/petar_m45_grid.py`
- `scripts/nbody_petar/petar_pdmf_analysis.py`
- `scripts/nbody_petar/petar_pdmf_ensemble.py`
- `scripts/nbody_petar/petar_system_catalog.py`
- `scripts/nbody_petar/prepare_nbody_prior_queue.py`
- `scripts/nbody_petar/queue_training_batch.py`
- `scripts/nbody_petar/summarize_training_runs.py`
- `scripts/plotting/plot_m45_nbody_correction_summary.py`
- `scripts/plotting/plot_step3.py`
- `scripts/plotting/plot_step45.py`
- `scripts/plotting/plots.py`
- `scripts/tools/check_append_only.py`
- `scripts/tools/check_stage_map_paths.py`
- `scripts/tools/checkpoint.py`
- `scripts/tools/concat_p2final_v3.py`
- `scripts/tools/concat_radial_final.py`
- `scripts/tools/preflight.py`
- `scripts/tools/zotero_literature_sync.py`
- `scripts/tools/zotero_sync.py`
- `ssh_sync.py`
- `ssh_workers.py`
- `status_dashboard/app.py`
- `status_dashboard/open_dashboard.py`
- `status_dashboard/stage_map.py`

</details>

## 新增或搬動程式時

1. 在 `catalog.json` 的 `scripts` 加上或修改那一筆（欄位說明在檔案開頭）。
2. 執行 `python code_map/build_map.py` 重新生成頁面，一起 commit。
3. CI 會跑 `--check`：路徑不存在、標籤值不合法、頁面沒重新生成都會擋下。
