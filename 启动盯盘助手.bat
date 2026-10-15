@echo off
cd /d "%~dp0"

set PYTHONW_EXE=
if exist "launch_config.txt" (
    set /p PYTHONW_EXE=<launch_config.txt
)

if exist "%PYTHONW_EXE%" (
    start "" "%PYTHONW_EXE%" "%~dp0app.py"
) else (
    start "" pythonw "%~dp0app.py"
)

exit
