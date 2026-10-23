@echo off
call "%~dp0run_sample.bat" --document-type lld %*
exit /b %errorlevel%
