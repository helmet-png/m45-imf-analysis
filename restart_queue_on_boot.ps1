# 開機／登入自動重啟本機運算佇列（2026-08-13 新增，2026-08-13 CodeRabbit review 後修正）
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
# 這支腳本的「先查行程再啟動」只是快速路徑、不是防重複的最後防線——
# 兩個觸發可能都通過檢查、各自啟動一個 runner。真正防止兩個
# run_queue.py 同時搶佇列的單例鎖在 run_queue.py 自己身上
# （acquire_lock()，PID 檔案 + tasklist 探測），這支腳本只是避免
# 沒必要地一直呼叫 Start-Process。
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
# 3. 用 Start-ScheduledTask 手動觸發測試時，行程會卡住不執行到底，
#    懷疑是這個工具執行環境本身的 session 限制，沒能實測到真正的
#    開機/登入觸發是否成功——這件事本身就是 CodeRabbit review 指出的
#    「失敗路徑可能被靜默吞掉」風險的活生生案例，所以這次補上
#    -ErrorAction Stop + exit 1，讓失敗至少能被工作排程器看到。

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$selfLog = Join-Path $repo "logs\autorestart.log"
$scriptPath = Join-Path $repo "run_queue.py"

function Write-SelfLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        Add-Content -Path $selfLog -Value "[$stamp] $Message" -ErrorAction Stop
    } catch {
        # log 本身寫失敗不該讓腳本連帶被視為失敗——這是輔助訊息，
        # 不是核心邏輯（CodeRabbit review：logger 要 best-effort）。
    }
}

Write-SelfLog "腳本開始執行"

try {
    Set-Location -Path $repo -ErrorAction Stop

    # 只比對這個 repo 自己的 run_queue.py 完整路徑，不是裸的
    # "run_queue.py" 片段——避免別的 checkout、備份檔
    # （run_queue.py.bak）之類的命令列片段誤判成「已經在跑」，
    # 導致該重啟的時候被誤判成略過（CodeRabbit review 指出的問題）。
    $escapedPath = [regex]::Escape($scriptPath)
    $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -match $escapedPath }

    if ($existing) {
        $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
        Write-SelfLog "run_queue.py 已在跑（PID $pids），略過重複啟動"
        exit 0
    }

    Write-SelfLog "偵測到佇列執行器沒在跑，自動重啟"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c python -u `"$scriptPath`" >> logs\queue_runner8.log 2>&1" -WorkingDirectory $repo -WindowStyle Hidden -ErrorAction Stop
    Write-SelfLog "已呼叫 Start-Process 重啟 run_queue.py"
}
catch {
    Write-SelfLog "例外，重啟失敗：$($_.Exception.Message)"
    exit 1
}
