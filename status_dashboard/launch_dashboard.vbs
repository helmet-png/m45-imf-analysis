Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir_ = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "pyw """ & dir_ & "\app.py""", 0, False
WScript.Sleep 1500
sh.Run "http://127.0.0.1:8866/", 1, False
