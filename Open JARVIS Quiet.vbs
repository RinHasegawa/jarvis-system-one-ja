Option Explicit
Dim shell, fs, folder, python, program
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(folder, ".venv\Scripts\pythonw.exe")
program = fs.BuildPath(folder, "jarvis_event_actions.py")
If Not fs.FileExists(python) Or Not fs.FileExists(program) Then
  MsgBox "JARVIS could not find its Python environment or program.", 16, "JARVIS"
Else
  shell.CurrentDirectory = folder
  shell.Run """" & python & """ """ & program & """", 0, False
End If
