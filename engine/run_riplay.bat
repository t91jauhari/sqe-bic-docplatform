@echo off
call "%~dp0run_sample.bat" --document-type riplay %*
exit /b %errorlevel%
