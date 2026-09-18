#!/usr/bin/env bash
# 一次性設定：在雲端 worker（Linux）上裝出「跟本機這份能跑」的 pyUPMASK。
#
# 為什麼需要這支腳本：本機的 pyUPMASK/ 是獨立 clone 自
# https://github.com/msolpera/pyUPMASK，釘在 commit 3602293，但有三處
# 本機修改（見 setup/pyupmask_local.patch），從未進過任何版控——包括
# distutils.strtobool 的 Python 3.12+ 相容性補丁。**沒有這個補丁，
# 任何跑 Python 3.12 以上的 worker 直接 clone 原版都會在第一步匯入就
# 崩潰**（distutils 在 3.12 被移除），不是機率性失敗。這支腳本把 clone
# 跟套 patch 這兩步固定下來，避免每個 worker 各自重新摸索。
#
# 用法（在目標 worker 上，repo 根目錄執行）：
#   bash setup/setup_pyupmask.sh
#
# 前置：worker 已經照 docs/reference/CLOUD_WORKERS.md 第 2 節裝好
# Python、python3-venv 與 git。pyUPMASK 使用 repo 內的獨立 venv；
# 不改系統 Python（Ubuntu/Debian 的 PEP 668 會拒絕直接安裝套件）。

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIN_COMMIT="3602293059f42141b402215525d1d408c3360487"
TARGET="$HERE/pyUPMASK"
PYTHON_BIN="${1:-python3}"
VENV="$HERE/.venv_pyupmask"
VENV_PY="$VENV/bin/python3"

if [ -d "$TARGET" ]; then
    echo "pyUPMASK/ 已存在（$TARGET），不重新 clone。"
    echo "如果要重來，先手動刪除這個目錄再重跑本腳本。"
else
    echo "Clone pyUPMASK @ $PIN_COMMIT ..."
    git clone https://github.com/msolpera/pyUPMASK.git "$TARGET"
    git -C "$TARGET" checkout "$PIN_COMMIT"
fi

if [ "$(git -C "$TARGET" rev-parse HEAD)" != "$PIN_COMMIT" ]; then
    echo "錯誤：pyUPMASK/ 不在釘選的 commit $PIN_COMMIT，拒絕套用 patch。" >&2
    exit 1
fi

echo "套用本機程式碼 patch（Python 3.12+ 相容性）..."
# run_variant.py 會在每次執行時改寫 params.ini 的 OL_runs 等參數；把它
# 排除在 patch 的冪等檢查外，避免前一次成功執行反而讓下一次 setup 失敗。
if git -C "$TARGET" apply --exclude=params.ini --check \
    "$HERE/setup/pyupmask_local.patch" 2>/dev/null; then
    git -C "$TARGET" apply --exclude=params.ini "$HERE/setup/pyupmask_local.patch"
    echo "patch 套用成功。"
elif git -C "$TARGET" apply --exclude=params.ini --reverse --check \
    "$HERE/setup/pyupmask_local.patch" 2>/dev/null; then
    echo "patch 已經套用過（reverse-apply 檢查通過），跳過。"
else
    echo "錯誤：patch 套不上去（既不是全新也不是已套用狀態）。" >&2
    echo "可能是 pyUPMASK 上游更新過，pin 的 commit 需要跟著換。" >&2
    exit 1
fi

ensure_ini_value() {
    local key="$1" value="$2"
    local ini="$TARGET/params.ini"
    if ! grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$ini"; then
        echo "錯誤：params.ini 找不到 ${key}，拒絕猜測設定格式。" >&2
        exit 1
    fi
    sed -i -E "s|^([[:space:]]*${key}[[:space:]]*=[[:space:]]*).*|\\1${value}|" "$ini"
}

# 這兩項不由 run_variant.py 覆寫，故每次 setup 都明確恢復成產線設定。
ensure_ini_value "rnd_seed" "99"
ensure_ini_value "ID" "source_id"

if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    if [ -e "$VENV" ]; then
        echo "既有 pyUPMASK venv 不完整，重新建立..."
    else
        echo "建立 pyUPMASK 專用 venv（沿用 worker 既有科學套件）..."
    fi
    "$PYTHON_BIN" -m venv --clear --system-site-packages "$VENV"
fi
if ! "$VENV_PY" -c 'import numpy, scipy, astropy, sklearn' 2>/dev/null; then
    echo "在 pyUPMASK 專用 venv 補齊科學套件（僅接受 wheel）..."
    "$VENV_PY" -m pip install --only-binary=:all: numpy scipy astropy scikit-learn
fi

echo ""
echo "驗證：匯入 dataIO/outer 兩個模組（不執行 pyUPMASK 本體）..."
"$VENV_PY" -c "
import sys
sys.path.insert(0, '$TARGET')
from modules import dataIO, outer
print('  dataIO.strtobool(\"True\") =', dataIO.strtobool('True'))
print('  outer 模組匯入成功')
"
echo ""
echo "完成。接著可以用 scripts/drivers/run_variant.py 跑實際的聚類。"
