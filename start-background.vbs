Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir
pythonExe = currentDir & "\.venv\Scripts\python.exe"
WshShell.Run """" & pythonExe & """ server.py", 0, False
Set WshShell = Nothing
Set fso = Nothing
