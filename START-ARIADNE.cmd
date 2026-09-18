@echo off
setlocal
cd /d "%~dp0"
title ARIADNE One-Click Launcher

rem Prefer Windows' own PowerShell by absolute path so unrelated PATH entries
rem cannot redirect the launcher into Conda/NVIDIA/other toolchains.
set "ARIADNE_PS="
if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
  set "ARIADNE_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
)
if not defined ARIADNE_PS if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
  set "ARIADNE_PS=%ProgramFiles%\PowerShell\7\pwsh.exe"
)
if not defined ARIADNE_PS (
  where powershell.exe >nul 2>nul
  if not errorlevel 1 set "ARIADNE_PS=powershell.exe"
)
if not defined ARIADNE_PS (
  where pwsh.exe >nul 2>nul
  if not errorlevel 1 set "ARIADNE_PS=pwsh.exe"
)

if not defined ARIADNE_PS (
  echo.
  echo ARIADNE could not find PowerShell.
  echo Windows 11 normally includes Windows PowerShell.
  echo No system settings were changed.
  pause
  exit /b 1
)

"%ARIADNE_PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1" %*
set "ARIADNE_EXIT=%ERRORLEVEL%"
if not "%ARIADNE_EXIT%"=="0" pause
exit /b %ARIADNE_EXIT%
