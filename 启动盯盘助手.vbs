Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
strConfig = strDir & "\launch_config.txt"
strApp = strDir & "\app.py"

Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = strDir

If fso.FileExists(strConfig) Then
    Set f = fso.OpenTextFile(strConfig, 1)
    strPythonW = Trim(f.ReadAll())
    f.Close
    strPythonW = Replace(strPythonW, vbCrLf, "")
    strPythonW = Replace(strPythonW, vbCr, "")
    strPythonW = Replace(strPythonW, vbLf, "")
    If fso.FileExists(strPythonW) Then
        ws.Run """" & strPythonW & """ """ & strApp & """", 1, False
    Else
        ws.Run "pythonw """ & strApp & """", 1, False
    End If
Else
    ws.Run "pythonw """ & strApp & """", 1, False
End If