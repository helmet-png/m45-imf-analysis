' 2026-08-24 新增：Windows 工作排程器直接呼叫 powershell.exe 時，即使工作
' 本身的 Hidden 屬性設 true，Conhost 還是會在螢幕上短暫閃出一個主控台視窗
' 再消失（Hidden 只控制工作排程器「工作清單」裡看不看得到這個工作，跟
' 啟動出來的行程視窗是否可見完全是兩回事）。改用 wscript.exe 執行這支
' VBScript，用 WshShell.Run 的第二個參數 0（=隱藏視窗）啟動 powershell，
' 這是 Windows 上真正能做到「零閃現」的標準做法。
Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\yutun\Documents\m45-imf-analysis\restart_queue_on_boot.ps1""", 0, False
