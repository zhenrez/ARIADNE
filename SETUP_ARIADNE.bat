@echo off
call "%~dp0START-ARIADNE.cmd" -VerifyOnly
exit /b %ERRORLEVEL%
