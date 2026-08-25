Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir_ = fso.GetParentFolderName(WScript.ScriptFullName)

' CLOUD_QUEUE_ROOT: app.py 預設指向這個 repo 自己（多數情況下夠用），
' 但這台機器上 cloud_queue.py 目前活著在跑的工作目錄還是另一個
' worktree（cloud_queue.txt/logs/cloud_queue.lock 等檔案只在那裡）——
' 見 app.py 檔頭「已知的路徑落差」說明。worktree 收斂回 main 之後，
' 刪掉（或改指到這個 repo 自己）這一行即可，不用動其他程式碼。
Set env = sh.Environment("Process")
env("CLOUD_QUEUE_ROOT") = "C:\Users\Alber\Claude\m45_cloud_workers_wt"

sh.Run "pyw """ & dir_ & "\app.py""", 0, False
WScript.Sleep 1500
sh.Run "http://127.0.0.1:8866/", 1, False
