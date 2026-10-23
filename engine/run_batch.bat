@echo off
call "%~dp0run_sample.bat" --batch %*
exit /b %errorlevel%
