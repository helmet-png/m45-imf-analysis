# 開機／登入自動重啟本機運算佇列（2026-08-13 新增）
#
# 起因：2026-08-12 21:54 這台機器重開機，直接砍掉了 detached 的
# run_queue.py 整棵行程樹（p2_free_lowmass 正在跑到一半），一路閒置到
# 隔天 02:24 才被使用者發現——浪費了 8.5 小時的算力時間，且沒有任何
# 崩潰訊息可查（run_queue.py 的 log 就是安靜停在那裡，行程列表裡完全
# 找不到）。這支腳本讓「重開機/斷電恢復後沒人管也會自動接續」成立。
#
# 由 Windows 工作排程器在使用者登入時觸發（不是純系統開機），
# 因為 run_queue.py 需要正常的使用者 PATH（Python Manager 裝的
# python.exe）才能跑得起來，用 SYSTEM 層級開機觸發器可能拿不到。
#
# 防重複啟動：如果 run_queue.py 已經在跑（例如使用者自己手動重啟過），
# 這支腳本什麼都不做，不會產生兩個佇列執行器互搶佇列。
#
# queue.txt 本身的設計已經保證安全：任務只有整批跑完才會被
# mark_done()，中途被砍掉的任務不會被誤判成已完成，重啟後會從頭
# 重跑那一項，不會用到殘缺輸出（fit_real.py 等腳本都是全部算完才
# 一次性 np.savez，不會有部分寫入的檔案）。
#
# 走過的錯路（2026-08-13，三個）：
# 1. 第一版檔案用 UTF-8 無 BOM 存檔，Windows PowerShell 5.1 在中文
#    系統預設用 ANSI 編碼讀 .ps1，把多位元組的中文字誤判成語法字元，
#    導致「字串缺少結束符號」這種看起來毫無關聯的解析錯誤。
#    改用帶 BOM 的 UTF-8 存檔解決。
# 2. 原本把「偵測到已在跑，略過」的訊息也寫進 logs\queue_runner8.log，
#    但那個檔案這時正被 cmd.exe 的 >> 重導向獨占寫入中，Add-Content
#    會撞鎖噴 IOException。改寫進獨立的 logs\autorestart.log。
# 3. 用 Start-ScheduledTask 手動觸發測試時，LastTaskResult 回報
#    0xC000013A（STATUS_CONTROL_C_EXIT），且 autorestart.log 完全沒有
#    新的一行——代表腳本在寫入第一行 log 之前就已經整個中止，不是
#    邏輯錯誤。原因未完全查清（懷疑是工作排程器的服務層級 session 對
#    Get-CimInstance/WMI 呼叫的限制或逾時），所以把整個主體包進
#    try/catch，任何例外都先落地寫進 log 再說，不要讓錯誤憑空消失。

$repo = "C:\Users\Alber\Claude\m45_membership"
$queueLog = Join-Path $repo "logs\queue_runner8.log"
$selfLog = Join-Path $repo "logs\autorestart.log"

function Write-SelfLog($msg) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $selfLog -Value "[$stamp] $msg"
}

Write-SelfLog "腳本開始執行（診斷用：確認腳本至少有被觸發到）"

try {
    Set-Location $repo

    $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match "run_queue\.py" }

    if ($existing) {
        $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
        Write-SelfLog "run_queue.py 已在跑（PID $pids），略過重複啟動"
        exit 0
    }

    Write-SelfLog "偵測到佇列執行器沒在跑，自動重啟"
    Start-Process -FilePath "cmd.exe" -ArgumentList '/c python -u run_queue.py >> logs\queue_runner8.log 2>&1' -WorkingDirectory $repo -WindowStyle Hidden
    Write-SelfLog "已呼叫 Start-Process 重啟 run_queue.py"
}
catch {
    Write-SelfLog "例外：$($_.Exception.Message)"
}
