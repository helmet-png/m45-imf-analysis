#!/usr/bin/env bash
# ============================================================================
# 功能：在 Linux（含 WSL2 Ubuntu、24 核工作站、GCP e2-highcpu VM）建出含 BSE
# 恆星演化與 galpy 銀河潮汐的 PeTar，並跑三關驗收（S0，見
# docs/planning/NBODY_PREREGISTRATION.md 的 smoke test 分級）。這是
# scripts/nbody_petar/run_nbody_case.py 實際呼叫的 mcluster_sse/petar.init/
# petar/petar.data.process 這幾支二進位執行檔的來源。
#
# 方法：改寫姊妹腳本 nbody_setup/setup_windows_nbody.sh（那份是 MSYS2/
# MinGW-w64 專用，繼續保留給 Windows 協作機用，不要刪）。步驟：
#   1. 用同一組已驗證過的 commit（見下方 *_COMMIT 變數）clone 並釘選
#      FDPS／SDAR／PeTar／mcluster 四個外部專案到與本 repo 平行的
#      ../nbody/ 目錄（跟 Windows 版一樣不進版控）。
#   2. 建一個獨立 venv 裝 galpy==1.10.2（PeTar 官方 README 明講只支援到
#      這個版本，1.11+ 因為 galpy 自己改了 PowerSphericalPotentialwCutoff
#      的參數簽章而不相容）。
#   3. 用 --with-interrupt=bse --with-external=galpy 編譯 PeTar（Linux
#      原生不需要 Windows 版那兩個 MinGW patch——srand48/drand48/
#      feenableexcept 都是 glibc 原生函式，mcluster 不用改一行就能編）。
#   4. 跑三關驗收並印出結果：
#        (a) `petar -h` 的輸出含 `--galpy-set`
#        (b) venv 裡 `python -c "import galpy; print(galpy.__version__)"`
#            印出 1.10.2
#        (c) `petar.data.process -h` 可執行（exit 0）
#      三關對應計劃裡的 S0；S1-S4（管線通暢、能量守恆、實際計時）由
#      run_nbody_case.py --smoke 接手，不在這支腳本的範圍內。
#
# 冪等：外部專案已 clone 就跳過、只重新 checkout 到釘選 commit 再 build；
# venv 已存在就跳過建立、只重新 pip install。
#
# 用法：
#   bash nbody_setup/setup_linux_nbody.sh
#
# 前置需求（Ubuntu/Debian 系）：
#   sudo apt-get install -y build-essential gfortran cmake libgsl-dev \
#       autoconf automake libtool git python3 python3-venv python3-pip
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
NBODY_DIR="$(cd "$REPO_ROOT/.." && pwd)/nbody"
VENV_DIR="$NBODY_DIR/venv_galpy"

# 與 nbody_setup/README.md、setup_windows_nbody.sh 完全同一組 commit——
# 兩邊各自驗證過可用，故意不共用同一份腳本邏輯（Linux 與 Windows 的
# 編譯步驟差異太大，硬共用只會讓兩邊都難讀），但這四個 commit 常數
# 一定要保持一致，改一邊要記得改另一邊。
FDPS_COMMIT=6fedb4b8bd7a504598e83a4189a7a83c533a0848
SDAR_COMMIT=f64f11801f494bdceda9f4c93dad71dd64c57278
PETAR_COMMIT=84b81a8c339c49291de53f7a72829dd80e188182
MCLUSTER_COMMIT=a147bb5f1c0186a2d2d5b513ed112992929dd12a
GALPY_VERSION=1.10.2

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

echo "=== 1/4　Clone 並釘選 commit ==="
clone_pinned FDPS      https://github.com/FDPS/FDPS.git           "$FDPS_COMMIT"
clone_pinned SDAR      https://github.com/lwang-astro/SDAR.git    "$SDAR_COMMIT"
clone_pinned PeTar     https://github.com/lwang-astro/PeTar.git   "$PETAR_COMMIT"
clone_pinned mcluster  https://github.com/lwang-astro/mcluster.git "$MCLUSTER_COMMIT"

echo "=== 2/4　建 galpy venv（釘 $GALPY_VERSION）==="
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install "galpy==$GALPY_VERSION" "numpy" "astropy"
# PeTar 的 configure 用 pip 安裝路徑自動偵測 galpy 的 C 標頭與函式庫
# （README「Code path」一節）；只有這個 venv 的 python 在 PATH 最前面時
# 才找得到，所以編譯 PeTar 前把它排到最前面。
export PATH="$VENV_DIR/bin:$PATH"

echo "=== 3/4　編譯 PeTar（BSE 恆星演化 + galpy 銀河潮汐）==="
cd "$NBODY_DIR/PeTar"
# Linux 原生不需要 Windows 版的 MinGW uname 判斷 patch（那個 patch 只解決
# MSYS2 的 uname 回傳全大寫 MINGW64_NT-... 的問題，Linux 的 configure
# case 判斷式本來就吃得到 Linux*）。
#
# --with-galpy-prefix 明確指定（2026-09 實測踩到的坑）：PeTar 的
# configure.ac 自動偵測只找 $HOME/.local、$VIRTUAL_ENV、或跟 PeTar
# 同一層、名字剛好叫 galpy 的資料夾——這裡的 venv 只是把
# $VENV_DIR/bin 塞進 PATH 最前面（沒有 `source activate`），不會設定
# $VIRTUAL_ENV 這個環境變數，三個自動偵測路徑全部落空，會安靜地退回
# 檢查 PeTar 自己的目錄，報一個誤導性的「找不到 Galpy library」錯誤
# ——即使 headers（potential/potential_c_ext/galpy_potentials.h）明明
# 就在 pip 裝好的套件裡。直接用 python 問 galpy 自己裝在哪裡，不依賴
# 自動偵測。
GALPY_PREFIX="$("$VENV_DIR/bin/python" -c 'import galpy, os; print(os.path.dirname(galpy.__file__))')"
echo "galpy_prefix=$GALPY_PREFIX"
CXX=g++ CC=gcc FC=gfortran ./configure \
    --prefix="$NBODY_DIR/install" \
    --with-mpi=no \
    --with-interrupt=bse \
    --with-external=galpy \
    --with-galpy-prefix="$GALPY_PREFIX"
make -j"$(nproc)"
make install

echo "=== 4/4　編譯 mcluster（Linux 原生，不需要 Windows 版的相容層）==="
cd "$NBODY_DIR/mcluster"
make mcluster_sse CFLAGS='-lgfortran'

echo ""
echo "=== 驗收（S0，三關）==="
export OMP_STACKSIZE=128M
export PATH="$NBODY_DIR/install/bin:$PATH"

pass=0
total=3

echo "--- (a) petar -h 是否含 --galpy-set ---"
if petar -h 2>&1 | grep -q -- "--galpy-set"; then
    echo "PASS：--galpy-set 存在"
    pass=$((pass + 1))
else
    echo "FAIL：--galpy-set 不在 petar -h 輸出裡（galpy 編譯選項可能沒生效）"
fi

echo "--- (b) galpy 版本 ---"
galpy_version="$("$VENV_DIR/bin/python" -c 'import galpy; print(galpy.__version__)' 2>&1 || true)"
if [ "$galpy_version" = "$GALPY_VERSION" ]; then
    echo "PASS：galpy $galpy_version"
    pass=$((pass + 1))
else
    echo "FAIL：預期 $GALPY_VERSION，實際得到「$galpy_version」"
fi

echo "--- (c) petar.data.process -h ---"
if petar.data.process -h > /dev/null 2>&1; then
    echo "PASS：petar.data.process 可執行"
    pass=$((pass + 1))
else
    echo "FAIL：petar.data.process -h 非零結束"
fi

echo ""
echo "=== S0 結果：$pass / $total 關通過 ==="
echo "安裝路徑：$NBODY_DIR/install/bin"
echo "galpy venv：$VENV_DIR"
if [ "$pass" -ne "$total" ]; then
    echo "有關卡沒過，不要繼續跑 S1-S4——先查上面的 FAIL 訊息。"
    exit 1
fi
