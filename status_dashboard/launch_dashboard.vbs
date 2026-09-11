Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir_ = fso.GetParentFolderName(WScript.ScriptFullName)

' 2026-09-02: main board now runs on the coordinator VM (see
' docs/reference/CLOUD_WORKERS_IAP_SETUP.md), not locally. This just
' opens an IAP tunnel (if not already open) and the browser; see
' open_dashboard.py for the full explanation. Non-ASCII text kept out
' of this file because it breaks cscript/wscript on a Chinese-codepage
' Windows system.
sh.Run "pyw """ & dir_ & "\open_dashboard.py""", 0, False
