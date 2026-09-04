#!/usr/bin/env bash
# 在 Linux 運算節點上重現 PDMF->IMF 第 5 步的 N-body 編譯環境
# （PeTar + mcluster）。跟同資料夾的 setup_windows_nbody.sh 是同一件事
# 的兩個平台版本，釘選的 commit 完全一致。
#
# **為什麼要有 Linux 版**（2026-09-03）：原本只有 Windows 版，因為當時
# 唯一的機器是使用者的筆電。但正式的 M45 模擬網格（petar_m45_grid.csv）
# 每次要跑 2,369 顆星（1,215 個系統、1,154 對聯星），比先前驗證用的
# 128／1024 顆星大一個量級，在 15W 的筆電 CPU 上跑不切實際，而且那台
# 筆電闔蓋睡眠會直接砍掉背景行程（2026-08-29～30 主控板就這樣掉了四次）。
# 改在 24 核的 SSH 常駐運算節點上跑，速度快、不會被睡眠中斷、也沒有
# Kaggle 那種 12 小時 session 上限。
#
# **Linux 版比 Windows 版簡單**：Windows 版需要的兩個 patch
# （petar_configure_mingw.patch、mcluster_main_mingw.patch + mingw_compat.c）
# 純粹是繞過 MinGW 的相容性問題——`configure` 認不得全大寫的
# `MINGW64_NT-*`、MinGW runtime 缺 `srand48`／`drand48`／`feenableexcept`。
# Linux 的 glibc 本來就有這些，所以這裡完全不套用任何 patch。
#
# 用法：
#   bash nbody_setup/setup_linux_nbody.sh
#
# 冪等：外部專案 clone 到跟本 repo 平行的 nbody/ 目錄（不進版控），
# 已存在就跳過 clone，只重新 checkout 釘選 commit 並重新 build。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
NBODY_DIR="$(cd "$REPO_ROOT/.." && pwd)/nbody"

# 跟 setup_windows_nbody.sh 逐字相同——兩個平台編出來的必須是同一份
# 原始碼，否則跨機器比對模擬結果時會多出一個無法歸因的變因。
FDPS_COMMIT=6fedb4b8bd7a504598e83a4189a7a83c533a0848
SDAR_COMMIT=f64f11801f494bdceda9f4c93dad71dd64c57278
PETAR_COMMIT=84b81a8c339c49291de53f7a72829dd80e188182
MCLUSTER_COMMIT=a147bb5f1c0186a2d2d5b513ed112992929dd12a

# ---------------------------------------------------------------- 前置檢查
# **先檢查、不要直接 sudo apt install**：這個腳本會跑在別人提供的機器上
# （目前是學長借給我們的那台），不該未經確認就動人家的系統套件。缺什麼
# 先列出來，讓操作的人自己決定要不要裝、用什麼方式裝。
echo "=== 檢查編譯需要的工具 ==="
MISSING=()
# **編譯器要支援兩種來源**（2026-09-03 實測補上）：系統套件（apt）裝的是
# 純名稱 `gcc`／`g++`／`gfortran`；但沒有 sudo 的機器只能用 conda-forge
# 在家目錄裝，而 conda 的編譯器執行檔是**帶目標三元組前綴**的
# （`x86_64-conda-linux-gnu-cc` 之類），純名稱根本不存在，只有啟動環境時
# 設好的 $CC／$CXX／$FC 指得到。原本只檢查純名稱，在 conda 環境下會誤判
# 成「缺工具」而停下——senior24 就是這個情況（學長的機器，我們沒有 sudo）。
: "${CC:=gcc}"
: "${CXX:=g++}"
: "${FC:=gfortran}"
for var in CC CXX FC; do
    bin="${!var}"
    command -v "$bin" >/dev/null 2>&1 || MISSING+=("$var=$bin")
done
for cmd in git make autoconf automake libtool; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done

# **conda 環境要手動補 include／lib 路徑**（2026-09-03 實測踩到）：
# conda 把 GSL 的標頭檔放在 $CONDA_PREFIX/include，理論上 activate 時會設
# CPATH 讓編譯器自動找到，但實測 senior24 上 activate 之後 CPATH 是空的
# （不同 conda-forge 編譯器套件版本行為不一致），結果
# `echo '#include <gsl/gsl_rng.h>' | $CC -E -` 直接失敗、腳本誤判成沒裝
# GSL。加 -I$CONDA_PREFIX/include 就過。
#
# 這不只影響檢查，**後面編譯 PeTar／mcluster 時會踩到同一個問題**，所以
# 統一用 autotools 的標準變數 CPPFLAGS／LDFLAGS 帶下去，兩邊都受益。
# 非 conda 環境（$CONDA_PREFIX 沒設）時這段完全不做事，行為不變。
if [ -n "${CONDA_PREFIX:-}" ]; then
    export CPPFLAGS="-I$CONDA_PREFIX/include ${CPPFLAGS:-}"
    export LDFLAGS="-L$CONDA_PREFIX/lib -Wl,-rpath,$CONDA_PREFIX/lib ${LDFLAGS:-}"
    echo "偵測到 conda 環境，已補上 include／lib 路徑：$CONDA_PREFIX"

    # **還要幫工具鏈建純名稱的符號連結**（2026-09-03 實測第二關）：
    # conda 的 binutils 也全部帶前綴（x86_64-conda-linux-gnu-ar 等），
    # conda 有正確設好 $AR／$RANLIB／$NM／$LD，但 PeTar 的
    # bse-interface/Makefile 是**寫死純名稱 `ar`** 的，不吃 $(AR)，
    # 實測直接爛在 `make[1]: ar: No such file or directory`。
    #
    # 與其逐一去 patch 第三方 Makefile（PeTar／mcluster 都是研究用程式碼，
    # 寫死純名稱的地方可能不只一處，改了還要跟著上游版本維護），不如建一個
    # 只放符號連結的目錄插到 PATH 最前面，讓純名稱一律解析到 conda 的工具。
    # 這也正是 conda 自己 build 套件時的做法。
    SHIM_DIR="$NBODY_DIR/.toolchain-shims"
    mkdir -p "$SHIM_DIR"
    # 用 if 而不是 `[ -x ] && ln`——後者在最後一輪測試失敗時會讓整個 for
    # 迴圈回傳非零，配上開頭的 `set -e` 會讓腳本無聲中止。
    for tool in ar ranlib nm ld as objcopy objdump strip gcc g++ gfortran cc c++; do
        src="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-$tool"
        if [ -x "$src" ]; then
            ln -sf "$src" "$SHIM_DIR/$tool"
        fi
    done
    export PATH="$SHIM_DIR:$PATH"
    echo "已建立工具鏈符號連結（純名稱 -> conda 帶前綴版本）：$SHIM_DIR"
fi
# GSL 是 mcluster 的相依函式庫，沒有對應的執行檔可以用 command -v 檢查，
# 改看標頭檔在不在（-dev 套件才會裝標頭檔，只有執行期函式庫不夠編譯）。
# 用 $CC 而不是寫死 gcc，理由同上。
if ! echo '#include <gsl/gsl_rng.h>' | "$CC" -E ${CPPFLAGS:-} - >/dev/null 2>&1; then
    MISSING+=("GSL 標頭檔（apt: libgsl-dev／conda: gsl）")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "缺少以下項目：${MISSING[*]}"
    echo
    echo "有 sudo 的機器（Debian/Ubuntu）："
    echo "  sudo apt update && sudo apt install -y build-essential gfortran \\"
    echo "       autoconf automake libtool libgsl-dev git"
    echo
    echo "沒有 sudo 的機器（裝在家目錄，不動系統）："
    echo "  micromamba create -y -n nbody -c conda-forge \\"
    echo "      gcc_linux-64 gxx_linux-64 gfortran_linux-64 gsl make cmake \\"
    echo "      autoconf automake libtool"
    echo "  然後在啟動該環境的 shell 裡重跑這個腳本（\$CC/\$CXX/\$FC 會自動設好）"
    echo
    echo "裝好之後重新執行這個腳本。"
    exit 1
fi
echo "編譯工具齊全（CC=$CC  CXX=$CXX  FC=$FC）"

# ---------------------------------------------------------------- clone
mkdir -p "$NBODY_DIR"
cd "$NBODY_DIR"

clone_pinned () {
    local name="$1" url="$2" commit="$3"
    if [ -d "$name/.git" ]; then
        echo "[$name] 已存在，跳過 clone"
    else
        git clone "$url" "$name"
    fi
    (cd "$name" && git checkout "$commit")
}

echo "=== Clone 並釘選 commit ==="
clone_pinned FDPS      https://github.com/FDPS/FDPS.git            "$FDPS_COMMIT"
clone_pinned SDAR      https://github.com/lwang-astro/SDAR.git     "$SDAR_COMMIT"
clone_pinned PeTar     https://github.com/lwang-astro/PeTar.git    "$PETAR_COMMIT"
clone_pinned mcluster  https://github.com/lwang-astro/mcluster.git "$MCLUSTER_COMMIT"

# ---------------------------------------------------------------- 編譯
# --with-mpi=no：單機多核心用 OpenMP 就夠（編出來的是 petar.omp.*），
#   不跨機器分散，省掉 MPI 的安裝與設定。
# --with-interrupt=bse：把 BSE 恆星演化編進去。第 5 步要比較的是
#   「動力學演化 + 恆星演化」之後的質量函數，少了 BSE 就少一個真實效應。
# 用上面解析出來的 $CC／$CXX／$FC，不寫死 gcc／g++／gfortran——conda
# 環境下那些純名稱不存在（見前面檢查段落的說明）。
echo "=== 編譯 PeTar（含 BSE 恆星演化）==="
cd "$NBODY_DIR/PeTar"
CXX="$CXX" CC="$CC" FC="$FC" ./configure --prefix="$NBODY_DIR/install" \
    --with-mpi=no --with-interrupt=bse
make -j"$(nproc)"
make install

# Linux 上不需要 mingw_compat.o（那是補 MinGW 缺的 rand48／feenableexcept），
# 但 -lgfortran 要留著——mcluster_sse 會連結 SSE（恆星演化）的 Fortran 常式。
# mcluster 的 Makefile 預設用 `gcc`，conda 環境下要明確覆寫成 $CC。
echo "=== 編譯 mcluster ==="
cd "$NBODY_DIR/mcluster"
# CFLAGS 要把 $CPPFLAGS（conda 的 -I）也帶進去——mcluster 的 Makefile 不吃
# CPPFLAGS，只認 CFLAGS，不併進來的話 conda 環境下找不到 gsl 標頭檔。
make mcluster_sse CC="$CC" FC="$FC" \
    CFLAGS="${CPPFLAGS:-} -lgfortran ${LDFLAGS:-}"

# ---------------------------------------------------------------- 驗證
# 跟 Windows 版同一組煙霧測試，只差執行檔沒有 .exe 副檔名。
echo "=== 驗證 ==="
export OMP_STACKSIZE=128M
"$NBODY_DIR/install/bin/petar" -h > /dev/null && echo "petar: OK"
"$NBODY_DIR/mcluster/mcluster_sse" -N 10 -b 0.5 -C 5 -u 1 > /dev/null 2>&1 \
    && echo "mcluster_sse: OK"

echo
echo "=== 完成 ==="
echo "PeTar 安裝路徑： $NBODY_DIR/install/bin"
echo "mcluster 執行檔：$NBODY_DIR/mcluster/mcluster_sse"
echo
echo "提醒：環境能編譯 ≠ 正式模擬可以跑。正式模擬還需要正確的初始條件"
echo "參數與第 2 步的觀測基準線，見 nbody_setup/README.md 最後一節。"
