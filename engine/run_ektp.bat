@echo off
call "%~dp0run_sample.bat" --document-type ektp %*
exit /b %errorlevel%
