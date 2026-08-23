#!/bin/bash
# CodeRabbit 對某個 PR「是不是真的審過目前這次 push」的判定工具。
#
# 動機（2026-08-22）：CodeRabbit 在 repo 的 commit status 永遠顯示
# context=CodeRabbit / description="Review completed" / state=success，
# 即使它因為額度用完（"Review rate limited"）根本沒有送出正式 Review。
# 這個 status 只代表「CodeRabbit 的自動化跑完了」，不代表「有審查結果」，
# 兩者被混在同一個綠燈裡，肉眼從 PR 頁面或 `gh pr checks` 完全分不出來。
#
# 唯一可靠的判定：正式 Review（Approve/Request changes/Comment）物件上
# 帶的 commit_id，是不是等於 PR 目前的 head SHA。
#   - 相等 -> 這次 push 真的被審過，review 的 state 可信
#   - 不相等（或完全沒有 review）-> commit status 說完成，但其實沒有
#     針對目前這個 commit 的審查結果，多半是額度用完，不能當「通過」
#
# 用法：
#   scripts/tools/coderabbit_status.sh 98          # 查單一 PR
#   scripts/tools/coderabbit_status.sh              # 查目前所有 open PR
#
# 需要 gh CLI 已登入，repo 由目前所在目錄的 git remote 決定。
set -euo pipefail
cd "$(dirname "$0")/../.."

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)

check_one() {
  local n="$1"
  local head_sha status_desc status_state review_json review_state review_commit review_at title

  title=$(gh api "repos/$REPO/pulls/$n" --jq '.title' 2>/dev/null) || {
    echo "PR #$n：查不到（可能已關閉或合併）"
    return
  }
  head_sha=$(gh api "repos/$REPO/pulls/$n" --jq '.head.sha')

  # commit status：CodeRabbit 自動化本身有沒有跑完（不代表有審查結果）
  status_state=$(gh api "repos/$REPO/commits/$head_sha/status" \
    --jq '[.statuses[] | select(.context=="CodeRabbit")] | last | .state // "無"')

  # 真正的審查結果：最後一則 coderabbitai review，帶著它對應的 commit
  review_json=$(gh api "repos/$REPO/pulls/$n/reviews" \
    --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last')

  if [ "$review_json" = "null" ] || [ -z "$review_json" ]; then
    echo "PR #$n  $title"
    echo "    HEAD ${head_sha:0:7} ｜ CodeRabbit 自動化狀態=$status_state ｜ ⚠ 從來沒有任何正式 review，不能當已審過"
    return
  fi

  review_state=$(gh api "repos/$REPO/pulls/$n/reviews" --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last | .state')
  review_commit=$(gh api "repos/$REPO/pulls/$n/reviews" --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last | .commit_id')
  review_at=$(gh api "repos/$REPO/pulls/$n/reviews" --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last | .submitted_at')

  echo "PR #$n  $title"
  if [ "$review_commit" = "$head_sha" ]; then
    case "$review_state" in
      APPROVED)          badge="✅ APPROVED（已審過目前這次 push，意見都解決了）" ;;
      CHANGES_REQUESTED)  badge="🔴 CHANGES_REQUESTED（已審過目前這次 push，還有意見沒解決）" ;;
      COMMENTED)          badge="💬 COMMENTED（已審過目前這次 push，是留言型審查，不算正式核准）" ;;
      *)                  badge="$review_state" ;;
    esac
    echo "    HEAD ${head_sha:0:7} ｜ 自動化狀態=$status_state ｜ $badge"
  else
    echo "    HEAD ${head_sha:0:7} ｜ 自動化狀態=$status_state ｜ ⚠ 還沒有針對目前這個 commit 的正式 review（上一則 review 是 ${review_commit:0:7}、$review_at，多半是額度用完被跳過，不是「審過沒問題」）"
  fi
}

if [ $# -ge 1 ]; then
  for n in "$@"; do
    check_one "$n"
  done
else
  for n in $(gh pr list --state open --repo "$REPO" --json number --jq '.[].number'); do
    check_one "$n"
  done
fi
