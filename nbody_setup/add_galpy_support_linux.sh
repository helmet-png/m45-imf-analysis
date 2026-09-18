#!/usr/bin/env bash
# 在已經跑過 setup_linux_nbody.sh 的機器上，額外加上 PeTar 的 Galpy
# （銀河系外部潮汐力）支援。
#
# **這不是給我們自己 M45 正式模擬用的**：PETAR_M45_EXPERIMENT.md 裡的
# 設計是刻意先不加銀河潮汐（Converse & Stahler 2010 說 125 Myr 內加不
# 加潮汐差異很小）。這支腳本是 2026-09-11 為了讓另一位協作者需要
# `--galpy-set MWPotential2014` 的訓練網格能在 senior24 上跑，另外
# 補上去的——原本 setup_linux_nbody.sh 編出來的 petar.omp.avx512.bse
# 完全沒有 galpy 支援（NO_GALPY），跑該協作者的網格會直接在潮汐力參數
# 上崩潰。
#
# 跑完這支腳本後，install/bin/ 底下會**同時保留**兩個執行檔：
#   petar.omp.avx512.bse         -> 沒有 galpy，我們自己 M45 正式模擬用這個
#   petar.omp.avx512.bse.galpy   -> 有 galpy，需要銀河潮汐的人用這個
# 通用符號連結 petar 會被改成指向新的 .galpy 版本（PeTar 官方 make
# install 的行為，不是我們自己選的），**呼叫時一律用完整檔名，不要
# 依賴裸的 petar，避免每次重跑這支腳本後行為悄悄改變**。
#
# 用法（先跑過 nbody_setup/setup_linux_nbody.sh 之後）：
#   micromamba run -n nbody bash nbody_setup/add_galpy_support_linux.sh
# 或先 micromamba activate nbody 再直接跑。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
NBODY_DIR="$(cd "$REPO_ROOT/.." && pwd)/nbody"

if [ ! -d "$NBODY_DIR/PeTar/.git" ]; then
    echo "找不到 $NBODY_DIR/PeTar，請先跑 nbody_setup/setup_linux_nbody.sh"
    exit 1
fi

: "${CC:=gcc}"
: "${CXX:=g++}"
: "${FC:=gfortran}"

# 跟 setup_linux_nbody.sh 同一套 conda include/lib 路徑與工具鏈符號連結
# 邏輯，這裡不重複解釋原因，見那支腳本裡的註解。
if [ -n "${CONDA_PREFIX:-}" ]; then
    export CPPFLAGS="-I$CONDA_PREFIX/include ${CPPFLAGS:-}"
    export LDFLAGS="-L$CONDA_PREFIX/lib -Wl,-rpath,$CONDA_PREFIX/lib ${LDFLAGS:-}"
    SHIM_DIR="$NBODY_DIR/.toolchain-shims"
    mkdir -p "$SHIM_DIR"
    for tool in ar ranlib nm ld as objcopy objdump strip gcc g++ gfortran cc c++; do
        src="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-$tool"
        if [ -x "$src" ]; then
            ln -sf "$src" "$SHIM_DIR/$tool"
        fi
    done
    export PATH="$SHIM_DIR:$PATH"
fi

# ---------------------------------------------------------------- 裝 Galpy
# **版本一定要 <=1.10.2**：Galpy 1.11.0 改了 PowerSphericalPotentialwCutoff
# 的實作，跟 PeTar 現有的 MWPotential2014 參數設定不相容（PeTar 官方
# README 自己這樣寫的，不是我們猜的）。
# 用 --user 裝，讓 PeTar 的 configure 預設搜尋路徑（$HOME/.local）直接
# 找得到，不用額外傳 --with-galpy-prefix。
echo "=== 安裝 Galpy (<=1.10.2) ==="
python3 -m pip install --user "galpy==1.10.2"
python3 -c "import galpy; print('galpy version:', galpy.__version__)"

# ---------------------------------------------------------------- 重新編譯 PeTar
# 保留 --with-interrupt=bse（跟原本一樣要恆星演化），額外加
# --with-external=galpy。configure 只需要重跑一次，不需要重新 clone。
echo "=== 重新 configure PeTar（加上 --with-external=galpy）==="
cd "$NBODY_DIR/PeTar"
make clean
CXX="$CXX" CC="$CC" FC="$FC" ./configure --prefix="$NBODY_DIR/install" \
    --with-mpi=no --with-interrupt=bse --with-external=galpy

FCLIBS_FIX=""
if [ -n "${CONDA_PREFIX:-}" ]; then
    FCLIBS_FIX="-L$CONDA_PREFIX/lib -Wl,-rpath,$CONDA_PREFIX/lib -lgfortran -lm"
fi

# **已知問題（2026-09-11 實測）**：`galpy-interface/Makefile` 的
# `petar.galpy` 這個附屬診斷工具，用 conda 很新版的 GCC（16.2.0 實測）
# 編譯時會炸兩層錯：
#   1. Galpy 自己的標頭檔 `integrateFullOrbit.h` 把 `#include <omp.h>`
#      包在 `extern "C" { ... }` 裡；conda 新版 GCC 的 omp.h 裡有 C++
#      樣板宣告（給 typed reduction 用），樣板不能有 C linkage，直接
#      編譯失敗（"template with C linkage"）。
#   2. 修法是用 `-include omp.h` 強制編譯器提前正常（非 extern "C"）
#      引入一次 omp.h，靠 include guard 擋掉後面那次有問題的引入——但
#      這樣做完，Galpy 標頭檔裡「沒偵測到 _OPENMP 時自己定義的
#      omp_get_thread_num／omp_get_max_threads 替代版本」會跟真正
#      omp.h 的宣告衝突（extern vs static，-fpermissive 錯誤）。
#      同時加上 `-fopenmp`（讓 `_OPENMP` 被定義，Galpy 標頭檔改用真正
#      omp.h 那條路徑，不再自己定義替代版本）才會兩個問題一起解掉。
# 主程式本身的原始碼（FDPS／petar.hpp 等）不會踩到這個問題，因為 FDPS
# 自己的標頭檔本來就會在正常（非 extern "C"）情境下先引入一次 omp.h，
# 等於天然做到跟我們手動加 `-include omp.h` 一樣的效果——只有這個獨立
# 的 petar.galpy 小工具，因為它的原始碼沒有透過 FDPS，才需要我們手動
# 補這兩個旗標。
#
# 這是針對 galpy-interface 這個子目錄單獨覆寫 CXXFLAGS，不是全域改
# PeTar 的編譯選項；如果以後升級 Galpy 或 PeTar commit 版本後這個問題
# 消失了，這段可以拿掉，不影響其他部分。
echo "=== 編譯 PeTar（含 Galpy）==="
make -j"$(nproc)" ${FCLIBS_FIX:+FCLIBS="$FCLIBS_FIX"} || {
    echo "主要編譯步驟回報錯誤，嘗試套用 petar.galpy 的已知修正..."
    (
        cd galpy-interface
        rm -f petar.galpy
        make petar.galpy CXXFLAGS="-fvisibility-inlines-hidden -fmessage-length=0 \
-march=nocona -mtune=haswell -ftree-vectorize -fPIC -fstack-protector-strong \
-fno-plt -O2 -ffunction-sections -pipe -isystem ${CONDA_PREFIX:-/usr}/include \
-O3 -Wall -std=c++17 -fopenmp -include omp.h"
    )
    echo "petar.galpy 修好了，重新跑上層 make..."
    make -j"$(nproc)" ${FCLIBS_FIX:+FCLIBS="$FCLIBS_FIX"}
}
make install ${FCLIBS_FIX:+FCLIBS="$FCLIBS_FIX"}

# ---------------------------------------------------------------- 驗證
echo "=== 驗證 ==="
"$NBODY_DIR/install/bin/petar.omp.avx512.bse.galpy" -h 2>&1 \
    | grep -q -- "--galpy-set" \
    && echo "galpy 支援: HAS_GALPY" \
    || { echo "galpy 支援: NO_GALPY（有問題，不要當作已經修好）"; exit 1; }

if [ -x "$NBODY_DIR/install/bin/petar.omp.avx512.bse" ]; then
    echo "確認沒有 galpy 的舊版本仍在：petar.omp.avx512.bse（我們自己 M45 正式模擬用這個）"
fi

echo
echo "=== 完成 ==="
echo "有 galpy 的執行檔：$NBODY_DIR/install/bin/petar.omp.avx512.bse.galpy"
echo "沒有 galpy 的執行檔（M45 正式模擬用）：$NBODY_DIR/install/bin/petar.omp.avx512.bse"
echo
echo "提醒：實際使用 --galpy-set 時，petar.init 要加 -t（並視需要用 -c"
echo "指定星團在銀河座標系統裡真正的位置/速度偏移，不要用預設的 0,0,0,0,0,0"
echo "——那代表把星團放在銀河系正中心，會得到完全不合理的能量誤差。"
