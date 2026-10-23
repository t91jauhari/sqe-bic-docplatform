@echo off
call "%~dp0run_sample.bat" --document-type invoice %*
exit /b %errorlevel%
