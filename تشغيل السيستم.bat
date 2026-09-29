@echo off
chcp 65001 >nul
title نكست جين للمحاسبة - NextGenCoders
cd /d "%~dp0"
echo.
echo   ============================================
echo    نكست جين للمحاسبة - NextGen Accounting
echo    NextGenCoders - nextgen-coders.dev
echo   ============================================
echo.
python app.py
pause
