' 2026-08-24 新增：Windows 工作排程器直接呼叫 powershell.exe 時，即使工作
' 本身的 Hidden 屬性設 true，Conhost 還是會在螢幕上短暫閃出一個主控台視窗
' 再消失（Hidden 只控制工作排程器「工作清單」裡看不看得到這個工作，跟
' 啟動出來的行程視窗是否可見完全是兩回事）。改用 wscript.exe 執行這支
' VBScript，用 WshShell.Run 的第二個參數 0（=隱藏視窗）啟動 powershell，
' 這是 Windows 上真正能做到「零閃現」的標準做法。
'
' 路徑用 WScript.ScriptFullName 動態算出，不寫死使用者名稱——這支腳本
' 之後如果換一台機器或換 checkout 路徑，不用跟著改這個檔案（2026-08-23
' CodeRabbit review 抓到寫死路徑的問題）。
'
' bWaitOnReturn 用 True（等 restart_queue_on_boot.ps1 執行完才返回）：這
' 支腳本本身只做「查鎖檔/查行程 -> 視情況 Start-Process detached 啟動」，
' Start-Process 沒有帶 -Wait，所以 restart_queue_on_boot.ps1 本身幾秒內就
' 會執行完畢，不會因為 run_queue.py／cloud_queue.py 要跑好幾天而被卡住；
' 等它跑完才能透過 WScript.Quit 把真正的 exit code 往外傳，PowerShell 端
' 若失敗（-ErrorAction Stop 觸發的例外）才不會被吞掉、工作排程器才看得到
' 失敗紀錄（2026-08-23 CodeRabbit review 抓到 bWaitOnReturn=False 會吞掉
' exit code 的問題）。
Dim objFSO, objShell, scriptDir, ps1Path, cmd, exitCode
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
ps1Path = objFSO.BuildPath(scriptDir, "restart_queue_on_boot.ps1")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1Path & """"
exitCode = objShell.Run(cmd, 0, True)
WScript.Quit exitCode
