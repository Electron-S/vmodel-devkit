@echo off
rem VModel DevKit validator launcher for cmd.exe / PowerShell
if defined VMODEL_PYTHON (
  "%VMODEL_PYTHON%" -I -B "%~dp0..\validator\vmodel.py" %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>nul && (py -3 -I -B "%~dp0..\validator\vmodel.py" %* & exit /b %ERRORLEVEL%)
python -I -B "%~dp0..\validator\vmodel.py" %*
exit /b %ERRORLEVEL%
