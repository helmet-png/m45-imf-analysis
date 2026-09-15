#!/usr/bin/env bash
# 在 Windows（MSYS2/MinGW-w64，不需要 WSL）重現 PDMF->IMF 第 5 步的
# N-body 編譯環境。前置條件：MSYS2 已裝好、mingw-w64-x86_64-toolchain/
# gcc-fortran/cmake/gsl/autoconf/automake/libtool 已裝好（見同資料夾
# README.md 的步驟 1-2）。
#
# 用法（在 MSYS2 的 bash 裡跑，不是一般 Windows Git Bash）：
#   bash nbody_setup/setup_windows_nbody.sh
#
# 冪等：外部專案 clone 到跟本 repo 平行的 nbody/ 目錄（不進版控），
# 已存在就跳過 clone，只重新套用 patch（patch 用 --forward 容忍
# 已套用過的情況）並重新 build。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
NBODY_DIR="$(cd "$REPO_ROOT/.." && pwd)/nbody"

FDPS_COMMIT=6fedb4b8bd7a504598e83a4189a7a83c533a0848
SDAR_COMMIT=f64f11801f494bdceda9f4c93dad71dd64c57278
PETAR_COMMIT=84b81a8c339c49291de53f7a72829dd80e188182
MCLUSTER_COMMIT=a147bb5f1c0186a2d2d5b513ed112992929dd12a

export PATH=/mingw64/bin:$PATH

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
clone_pinned FDPS      https://github.com/FDPS/FDPS.git          "$FDPS_COMMIT"
clone_pinned SDAR      https://github.com/lwang-astro/SDAR.git    "$SDAR_COMMIT"
clone_pinned PeTar     https://github.com/lwang-astro/PeTar.git   "$PETAR_COMMIT"
clone_pinned mcluster  https://github.com/lwang-astro/mcluster.git "$MCLUSTER_COMMIT"

echo "=== 套用 patch ==="
cd "$NBODY_DIR/PeTar"
patch -p1 --forward -r - < "$HERE/petar_configure_mingw.patch" || echo "  （PeTar configure patch 已套用過，跳過）"

cd "$NBODY_DIR/mcluster"
cp "$HERE/mingw_compat.c" "$HERE/mingw_compat.h" .
patch -p1 --forward -r - < "$HERE/mcluster_main_mingw.patch" || echo "  （mcluster main.c patch 已套用過，跳過）"

# galpy（可選，銀河潮汐場）——跟 setup_linux_nbody.sh 同一段邏輯與理由
# （H14／LIMITATIONS.md D19）：預設不裝（還沒有指令用得到），要裝一定
# 要鎖 <=1.10.2（PeTar 官方文件明講只支援到這個版本，1.11.0 改了
# PowerSphericalPotentialwCutoff，跟 PeTar 現在的 MWPotential2014 設定
# 不相容，不鎖版本會裝到不相容版、且不一定會直接報錯）。
if [ "${INSTALL_GALPY:-0}" = "1" ]; then
    echo "=== 安裝 galpy（銀河潮汐場，鎖版本 <=1.10.2）==="
    pip install "galpy<=1.10.2"
else
    echo "=== 跳過 galpy（未設 INSTALL_GALPY=1；銀河潮汐場尚未接上 PeTar，見 D19） ==="
fi

echo "=== 編譯 PeTar（含 BSE 恆星演化）==="
cd "$NBODY_DIR/PeTar"
CXX=g++ CC=gcc FC=gfortran ./configure --prefix="$NBODY_DIR/install" --with-mpi=no --with-interrupt=bse
make
make install

echo "=== 編譯 mcluster ==="
cd "$NBODY_DIR/mcluster"
gcc -O2 -c mingw_compat.c -o mingw_compat.o
make mcluster_sse CFLAGS='mingw_compat.o -lgfortran'

echo "=== 驗證 ==="
export OMP_STACKSIZE=128M
"$NBODY_DIR/install/bin/petar" -h > /dev/null && echo "petar: OK"
"$NBODY_DIR/mcluster/mcluster_sse.exe" -N 10 -b 0.5 -C 5 -u 1 > /dev/null 2>&1 && echo "mcluster_sse: OK"

echo "=== 完成。安裝路徑：$NBODY_DIR/install/bin ==="
