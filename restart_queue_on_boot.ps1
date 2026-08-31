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
# 重跑那一項。
#
# **2026-08-15/16 更新，上面兩句已經過期**：
# 1. fit_real.py 不再是「全部算完才一次性 np.savez」——2026-08-15 改成
#    每算完一次 repeat 就存一次（atomic_savez），中途被砍會保留已完成
#    的部分結果，重啟後 load_partial() 會讀回來接著跑，不是從頭重算。
# 2. run_queue.py 新增卡死偵測（見該檔開頭 STALL_* 常數說明），連續卡死
#    達上限會標記 stalled_giveup 並放棄「這一輪」重試，但這個狀態
#    **不算真正完成**——read_done() 特別把它排除在外，下次像這支腳本
#    觸發的重啟會自動再給它一次機會，不需要人工介入清理。
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

# **2026-08-18 擴充，同一支腳本一併顧 kaggle_queue.py**：這台機器（Acer
# AI 16）連續遇到兩次非預期重開機（8/16、8/18），第二次連 kaggle_queue.py
# 這支輪詢器也一起被砍了——雖然 Kaggle 端的 kernel 不受影響（本機重開機
# 砍不到遠端），但本機沒有輪詢器就沒人去 pull 結果、也沒人往下派剩下的
# 待辦項目。kaggle_queue.py 已經加了 recover_running_slots()（開機時
# 掃描接回已在跑的 kernel，不會重推打斷進度），重啟這支跟重啟
# run_queue.py 一樣安全，一併加進來顧。
#
# **2026-08-23 換成顧 cloud_queue.py，不再顧 kaggle_queue.py**：
# cloud_queue.py 是 kaggle_queue.py 的上位替代——同一份 kaggle_accounts.json
# 底下的所有帳號、加上新的 SSH worker，都由它透過同一份佇列檔
# （cloud_queue.txt）統一派工，功能上完全涵蓋 kaggle_queue.py。**不能
# 兩支同時開機自動跑**：兩支腳本的單例鎖各自獨立、互相不認得對方，
# 若都自動重啟，可能同時對同一個 Kaggle 帳號各自派一個工作，在 Kaggle
# 那端互相打架（例如同時 push 不同 kernel 到同一個帳號的同一個 dataset
# slug）。cloud_queue.py 另外支援團隊集中式派工（自動從 origin/main
# 同步 cloud_queue.txt，隊員不用碰真實憑證就能加工作，見該檔案開頭
# 說明），是接下來唯一該常駐的派工器。若還有工作卡在 `kaggle_queue.txt`
# 裡沒排完，先手動搬進 `cloud_queue.txt`（格式完全相同）再交給
# cloud_queue.py，不要讓兩份佇列檔各自派工。

# **2026-08-24 補充**：工作排程器的兩個工作（M45-QueueWatchdog-15min、
# M45-QueueRunner-AutoRestart）先前設過 Hidden=true，但那只影響「工作
# 排程器清單裡看不看得到這個工作」，跟啟動出來的 powershell.exe 主控台
# 視窗會不會在螢幕上閃一下完全無關，所以每次觸發還是會跳出視窗。改成
# 由 run_hidden.vbs（同目錄）透過 wscript.exe + WshShell.Run(...,0,False)
# 呼叫這支腳本，才是真正零閃現的做法；本檔內容不受影響，只是啟動方式
# 換了一層。

$repo = $PSScriptRoot
$selfLog = Join-Path $repo "logs\autorestart.log"

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

function Restart-QueueIfNotRunning {
    param(
        [string]$ScriptName,   # 例如 "run_queue.py"
        [string]$LogFile       # 對應的輸出 log 檔名
    )
    $scriptPath = Join-Path $repo $ScriptName
    $queueLog = Join-Path $repo "logs\$LogFile"

    # 第一優先：看單例鎖檔。這是跟 Python 端同一個真相來源——run_queue.py
    # 與 kaggle_queue.py 的 acquire_lock() 就是用這個檔案判斷「有沒有另一
    # 份在跑」，兩邊用同一個判準才不會各說各話。
    #
    # **為什麼不能只靠命令列比對**（2026-08-21 實測到的問題）：下面那段
    # 比對要求命令列裡出現腳本的**完整絕對路徑**，但用相對路徑啟動
    # （`Set-Location $repo; python -u kaggle_queue.py`）時命令列裡只有
    # 裸檔名，比對不到，於是這支腳本每 15 分鐘都誤判成「沒在跑」而多開
    # 一份。那些多開的行程雖然一啟動就被 Python 端的單例鎖擋掉、自己
    # 退出（所以沒造成真正的傷害），但等於每輪都白開一個行程、還把
    # autorestart.log 灌滿假的「自動重啟」紀錄，真的出事時反而看不出來。
    # 這正是 acquire_lock() 註解裡記的 2026-08-18 那次「相對路徑啟動
    # 導致漏配」的同一個坑，只是這次是持續每 15 分鐘重演。
    $lockFile = Join-Path $repo ("logs\" + [IO.Path]::GetFileNameWithoutExtension($ScriptName) + ".lock")
    if (Test-Path $lockFile) {
        $lockPid = $null
        try { $lockPid = [int]((Get-Content $lockFile -Raw).Trim()) } catch { $lockPid = $null }
        if ($lockPid) {
            $alive = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
            if ($alive) {
                Write-SelfLog "$ScriptName 已在跑（鎖檔 PID $lockPid），略過重複啟動"
                return
            }
            # 鎖檔在、PID 卻不在 = 上次沒清乾淨。**不在這裡刪**：Python 端的
            # acquire_lock() 自己會偵測殘留鎖並清掉重搶，由它處理才不會跟
            # 正在啟動中的行程搶。這裡只當作「沒在跑」，往下走重啟流程。
            Write-SelfLog "$ScriptName 的鎖檔殘留（PID $lockPid 已不存在），視為沒在跑"
        }
    }

    # 第二道：命令列比對。鎖檔不存在時（例如還沒跑過任何一次）才用得上。
    # 只比對這個 repo 自己的腳本完整路徑，不是裸的檔名片段——避免別的
    # checkout、備份檔（例如 run_queue.py.bak）之類的命令列片段誤判成
    # 「已經在跑」，導致該重啟的時候被誤判成略過（CodeRabbit review
    # 指出的問題）。光是比對完整路徑還不夠：路徑本身也只是子字串，
    # "run_queue.py.bak" 一樣會匹配到 "run_queue.py" 這個前綴。加邊界
    # 要求——前面不能接非空白字元（排除更長檔名的一部分），後面要接
    # 空白或字串結尾，且允許路徑前後可能有的雙引號（Start-Process
    # 組出的命令行會加）。
    $pattern = '(?<!\S)"?' + [regex]::Escape($scriptPath) + '"?(?=\s|$)'
    $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -match $pattern }

    if ($existing) {
        $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
        Write-SelfLog "$ScriptName 已在跑（PID $pids），略過重複啟動"
        return
    }

    Write-SelfLog "偵測到 $ScriptName 沒在跑，自動重啟"
    $command = '/c python -u "{0}" >> "{1}" 2>&1' -f $scriptPath, $queueLog
    Start-Process -FilePath "cmd.exe" -ArgumentList $command -WorkingDirectory $repo -WindowStyle Hidden -ErrorAction Stop
    Write-SelfLog "已呼叫 Start-Process 重啟 $ScriptName"
}

Write-SelfLog "腳本開始執行"

try {
    Set-Location -Path $repo -ErrorAction Stop
    # **2026-08-23 起使用者決定：本機不再跑計算，全部排到雲端**——
    # 不再自動重啟 run_queue.py（讀 queue.txt 那支本機 8 核佇列）。
    # 新工作一律排 cloud_queue.txt 交給 cloud_queue.py（GCP/Kaggle）。
    # 若之後要恢復本機運算，把下面這行的註解拿掉即可，不用改別的地方。
    # Restart-QueueIfNotRunning -ScriptName "run_queue.py" -LogFile "queue_runner8.log"
    # **2026-08-27 起停用**：協調角色（cloud_queue.py + iap_tunnel_manager.py）
    # 已經整組遷移到雲端協調 VM（instance-20260827-035250，e2-micro，
    # us-central1，systemd 常駐，見 docs/reference/CLOUD_WORKERS_IAP_SETUP.md
    # 「給協調 VM 操作者做一次」一節）。這台筆電不再需要、也不應該自動
    # 重啟這兩支——兩邊同時跑會對同一批 cloud_queue.txt／Kaggle 帳號搶著
    # 派工，可能造成同一個工作被重複提交，IAP tunnel 也會被兩邊各自搶著
    # 建立。若之後真的要把協調角色搬回本機（例如雲端 VM 停用），把下面
    # 兩行的註解拿掉即可，不用改別的地方。
    # Restart-QueueIfNotRunning -ScriptName "cloud_queue.py" -LogFile "cloud_queue_runner.log"
    # Restart-QueueIfNotRunning -ScriptName "iap_tunnel_manager.py" -LogFile "iap_tunnel_manager_runner.log"
}
catch {
    Write-SelfLog "例外，重啟失敗：$($_.Exception.Message)"
    exit 1
}
