Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir_ = fso.GetParentFolderName(WScript.ScriptFullName)

' Temporary override until the worktree is folded back into main;
' see app.py header comment for the full explanation (kept out of
' this file because non-ASCII text here breaks cscript/wscript on
' a Chinese-codepage Windows system).
Set env = sh.Environment("Process")
env("CLOUD_QUEUE_ROOT") = "C:\Users\Alber\Claude\m45_cloud_workers_wt"

sh.Run "pyw """ & dir_ & "\app.py""", 0, False
WScript.Sleep 1500
sh.Run "http://127.0.0.1:8866/", 1, False
