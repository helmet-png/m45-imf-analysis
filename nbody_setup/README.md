# N-body（PeTar + mcluster）Windows 原生編譯設定

PDMF→IMF 第 5 步（N-body 重建 M45 初始狀態）的環境設定，記錄如何在
**沒有 WSL** 的 Windows 機器上用 MSYS2/MinGW-w64 編譯 PeTar（含 BSE 恆星
演化）與 mcluster。背景見 `docs/planning/PDMF_TO_IMF_PLAN.md` 第七節。

PeTar、FDPS、SDAR、mcluster 本身都是外部專案，不進這個 repo 的版控
（跟 `pyUPMASK/`、gaia-export 姊妹專案是同一個道理）。這個資料夾只放
**讓別人重現這次編譯所需要的東西**：外部專案的釘選 commit、對它們原始碼
的修改（patch）、以及重跑一次的腳本。

## 釘選的 commit（2026-08-12 驗證過可用）

| 專案 | commit |
|---|---|
| [FDPS](https://github.com/FDPS/FDPS)（pin 到 v7.0，PeTar 文件建議，v7.1 有已知 bug） | `6fedb4b8bd7a504598e83a4189a7a83c533a0848` |
| [SDAR](https://github.com/lwang-astro/SDAR) | `f64f11801f494bdceda9f4c93dad71dd64c57278` |
| [PeTar](https://github.com/lwang-astro/PeTar) | `84b81a8c339c49291de53f7a72829dd80e188182` |
| [mcluster](https://github.com/lwang-astro/mcluster) | `a147bb5f1c0186a2d2d5b513ed112992929dd12a` |

## 兩個修正

1. **`petar_configure_mingw.patch`**：PeTar 的 `configure`（已由 autoconf
   產生的那份，不是 `configure.ac`）第 3022 行附近的 `case` 判斷式
   `Cygwin*|Mingw*` 只匹配大小寫混合的 `Mingw*`，但 MSYS2 的 `uname`
   回傳全大寫的 `MINGW64_NT-...`，導致 `configure` 誤判成不支援的
   作業系統而中止。改成 `Cygwin*|Mingw*|MINGW*|MSYS*` 後
   `./configure`／`make` 都一次過。

2. **`mcluster_main_mingw.patch` + `mingw_compat.c`/`.h`**：mcluster 的
   `main.c` 用了三個 MinGW-w64 runtime 沒有的 glibc/POSIX 擴充函式：
   `srand48`／`drand48`（48-bit rand48 亂數產生器）跟 `feenableexcept`
   （浮點例外 trap，僅除錯用）。`mingw_compat.c`/`.h` 實作標準 rand48
   演算法（`X_{n+1}=(0x5DEECE66D·X_n+0xB) mod 2^48`）跟一個空的
   `feenableexcept`（不影響結果正確性，只是少了除錯用的 FP 例外中斷）。

## 重現步驟（Windows／MSYS2）

```bash
# 1. 裝 MSYS2（若尚未安裝）
winget install --id MSYS2.MSYS2 --silent --accept-package-agreements --accept-source-agreements

# 2. 更新核心並裝工具鏈（第一次 pacman -Syu 可能要求重啟 MSYS2 終端機，重跑一次即可）
/c/msys64/usr/bin/bash.exe -lc "pacman -Syu --noconfirm"
/c/msys64/usr/bin/bash.exe -lc "echo '' | pacman -S --noconfirm mingw-w64-x86_64-toolchain mingw-w64-x86_64-cmake mingw-w64-x86_64-gsl mingw-w64-x86_64-gcc-fortran make autoconf automake libtool"

# 3. 跑這個資料夾的 setup_windows_nbody.sh（clone 到 ~/../nbody，跟本 repo 平行、不進版控）
bash nbody_setup/setup_windows_nbody.sh
```

## 重現步驟（Linux 運算節點）

**正式的 M45 模擬網格建議跑在這裡，不是 Windows 筆電**（2026-09-03）：
`petar_m45_grid.csv` 每次要跑 2,369 顆星（1,215 個系統、1,154 對聯星），
比上面驗證用的 128／1024 顆星大一個量級；而筆電闔蓋睡眠會直接砍掉背景
行程（2026-08-29～30 主控板就這樣掉了四次），長時間模擬跑不完。SSH 常駐
運算節點沒有這個問題，也沒有 Kaggle 那種 12 小時 session 上限。

```bash
# 1. 裝編譯工具（Debian/Ubuntu；需要 sudo，先確認機器擁有者同意）
sudo apt update && sudo apt install -y build-essential gfortran \
     autoconf automake libtool libgsl-dev git

# 2. 跑這個資料夾的 setup_linux_nbody.sh
bash nbody_setup/setup_linux_nbody.sh
```

Linux 版**不套用任何 patch**——`petar_configure_mingw.patch` 與
`mcluster_main_mingw.patch`／`mingw_compat.c` 都只是繞過 MinGW 的相容性
問題（`configure` 認不得全大寫的 `MINGW64_NT-*`、MinGW runtime 缺
`srand48`／`drand48`／`feenableexcept`），Linux 的 glibc 本來就有這些。
釘選的四個 commit 兩個平台完全一致，確保跨機器比對模擬結果時不會多出
無法歸因的變因。

腳本會**先檢查編譯工具齊不齊、缺什麼就列出來並停下**，不會未經確認就
對別人提供的機器 `sudo apt install`。

## 為什麼是 shell 腳本，不是 Dockerfile（H14，2026-09-05 考慮過後的決定）

`setup_linux_nbody.sh`／`setup_windows_nbody.sh` 已經做到 H14 真正要的
東西——**釘選 commit（見上表）＋可重現的建置流程**，而且是實測跑過、
真的編出可用執行檔的版本，不是紙上談兵。沒有另外包一層 Dockerfile：
這批運算節點是隊友／學長借用的既有機器（見 `WORK_BOARD.md` 的
`senior24`／`gcp1`），不是我們自己申請的乾淨容器環境，臨時要求對方
先裝 Docker、把工作流程改成容器化，成本比維持現有 shell 腳本高，且
腳本本身已經內建「先檢查、缺什麼列出來、不擅自 `sudo apt install`」
這個對借用機器的禮貌——直接用 Docker 反而繞不過這個限制（容器化通常
需要更高權限或至少要能裝 Docker daemon）。如果未來運算節點換成我們
能完全控制的雲端 VM（例如比照 `docs/reference/CLOUD_WORKERS_IAP_SETUP.md`
的協調 VM 模式），再回頭評估 Dockerfile 值不值得投資。

**唯一發現且已修的版本鎖定缺口：galpy**——`petar_m45_grid.py` 目前還
沒有任何指令用到 galpy（見 D19／H3，銀河潮汐場還沒接上），但兩支
setup 腳本都已經預先加了鎖版本的安裝路徑（`INSTALL_GALPY=1` 觸發，
`pip install "galpy<=1.10.2"`），理由是 PeTar 官方文件明講只支援
galpy 到 1.10.2（1.11.0 改了 `PowerSphericalPotentialwCutoff`，跟
PeTar 現在對 `MWPotential2014` 的參數設定不相容，且不一定會直接報錯，
是「跑起來但結果不對」這種最難發現的失敗模式）。等 H3 真的把銀河潮汐場
接上 PeTar 時，直接設這個環境變數重跑腳本即可。

## 驗證（2026-08-12 已跑過，結果正常）

- `petar.omp.avx2.bse -h`：正常印出說明並結束（exit 0）
- 1000 顆星 Plummer 模型測試（`petar -n 1000 -t 1 __Plummer`）：能量守恆
  誤差 ~2.5e-5、角動量守恆誤差 ~1e-10
- 全鏈 `mcluster_sse` → `petar.init` → `petar`（100 顆星、25 組聯星、
  BSE 恆星演化）：exit 0

## 環境已就緒 ≠ 正式模擬可以跑

**這個資料夾只解決「能不能編譯、能不能跑」的問題。** 要跑真正對應
Converse & Stahler (2010) 的正式模擬，還需要：

- 正確的初始條件參數（該文獻的設定是**氣體驅離後、已達 virial 平衡**的
  星團狀態，不含胚胎星團／氣體動力學階段本身——後者該論文明講留給
  未來工作，不要把兩者混為一談，見 `docs/planning/PDMF_TO_IMF_PLAN.md` 對這篇文獻的
  說明）
- 第 2 步（`radial_r1/r2/r3/rall`）的觀測基準線結果，用來校準/比對
  模擬輸出的 α(r)，這部分還沒跑完（見 `WORK_BOARD.md`）
