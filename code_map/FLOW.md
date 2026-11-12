<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->

# 資料流程圖

方框是程式，圓角框是檔案（藍色在 repo 內，紅色是外部來源或外部程式）。實線箭頭是讀寫檔案，虛線是一支程式執行另一支。箭頭完全由 catalog.json 的 reads／writes／calls 決定；只被 import、自己不讀寫檔案的函式庫不在圖上，見 [每支程式的上下游](views/relations.md)。

```mermaid
flowchart TD
  subgraph g10["10 取得資料"]
    n0["fetch_gaia.py"]
  end
  subgraph g20["20 成員判定"]
    n1["prep.py"]
    n2["run_variant.py"]
  end
  subgraph g30["30 色光圖與測光品質"]
    n3["run_pipeline.py"]
    n4["build_selection.py"]
  end
  subgraph g40["40 PDMF 擬合"]
    n5["isochrones.py"]
    n6["traditional_accounting.py"]
    n7["fit_real.py"]
    n8["40_傳統法.py"]
  end
  subgraph g50["50 驗證與誤差"]
    n9["injection_recovery.py"]
    n10["profile_lowmass.py"]
  end
  subgraph g60["60 N-body 模擬"]
    n11["generate_training_grid.py"]
    n12["run_training_queue.py"]
    n13["run_nbody_case.py"]
  end
  subgraph g70["70 PDMF → IMF"]
    n14["emulator_fit.py"]
  end
  subgraph gx["基礎設施"]
    n15["build_map.py"]
    n16["cloud_queue.py"]
  end
  n0 --> n17(["data/m45_r5_g18_plx4.csv"]):::file
  n18(["Gaia Archive"]):::ext --> n0
  n1 --> n19(["prepared/m45_raw.dat"]):::file
  n17(["data/m45_r5_g18_plx4.csv"]):::file --> n1
  n2 --> n20(["results/baseline.dat"]):::file
  n19(["prepared/m45_raw.dat"]):::file --> n2
  n2 -.->|執行| n21(["pyUPMASK"]):::ext
  n3 --> n22(["data/cmd_members.csv"]):::file
  n3 --> n23(["data/errmodel.npz"]):::file
  n20(["results/baseline.dat"]):::file --> n3
  n17(["data/m45_r5_g18_plx4.csv"]):::file --> n3
  n4 --> n24(["data/selection.npz"]):::file
  n17(["data/m45_r5_g18_plx4.csv"]):::file --> n4
  n5 --> n25(["isochrones/parsec_*.dat"]):::file
  n26(["PARSEC 等時線網頁服務"]):::ext --> n5
  n6 --> n27(["results/traditional_accounting_v2.npz"]):::file
  n22(["data/cmd_members.csv"]):::file --> n6
  n23(["data/errmodel.npz"]):::file --> n6
  n24(["data/selection.npz"]):::file --> n6
  n25(["isochrones/parsec_*.dat"]):::file --> n6
  n7 --> n28(["results/fit_real*.npz"]):::file
  n22(["data/cmd_members.csv"]):::file --> n7
  n23(["data/errmodel.npz"]):::file --> n7
  n24(["data/selection.npz"]):::file --> n7
  n25(["isochrones/parsec_*.dat"]):::file --> n7
  n9 --> n29(["results/injection_recovery*.npz"]):::file
  n22(["data/cmd_members.csv"]):::file --> n9
  n23(["data/errmodel.npz"]):::file --> n9
  n24(["data/selection.npz"]):::file --> n9
  n25(["isochrones/parsec_*.dat"]):::file --> n9
  n10 --> n30(["results/profile_lowmass*.npz"]):::file
  n22(["data/cmd_members.csv"]):::file --> n10
  n23(["data/errmodel.npz"]):::file --> n10
  n24(["data/selection.npz"]):::file --> n10
  n25(["isochrones/parsec_*.dat"]):::file --> n10
  n11 --> n31(["petar_m45_training_grid.csv"]):::file
  n12 --> n32(["runs_training/queue_progress.json"]):::file
  n31(["petar_m45_training_grid.csv"]):::file --> n12
  n12 -.->|執行| n13
  n13 --> n33(["runs_training/*/result.json"]):::file
  n31(["petar_m45_training_grid.csv"]):::file --> n13
  n13 -.->|執行| n34(["mcluster_sse"]):::ext
  n13 -.->|執行| n35(["PeTar"]):::ext
  n36(["runs_training/*/observed.stats.json"]):::file --> n14
  n31(["petar_m45_training_grid.csv"]):::file --> n14
  n37(["results/nbody_observed_targets.json"]):::file --> n14
  n22(["data/cmd_members.csv"]):::file --> n8
  n25(["isochrones/parsec_*.dat"]):::file --> n8
  n27(["results/traditional_accounting_v2.npz"]):::file --> n8
  n38(["code_map/catalog.json"]):::file --> n15
  n16 --> n39(["logs/cloud_queue_done.txt"]):::file
  n40(["cloud_queue.txt"]):::file --> n16
  classDef file fill:#eef,stroke:#88a
  classDef ext fill:#fee,stroke:#a88
```
