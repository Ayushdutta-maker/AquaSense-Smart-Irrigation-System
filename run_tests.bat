@echo off
title AquaSense Automated Test Runner
echo ===================================================
echo   Running AquaSense Automated API ^& Safety Tests
echo ===================================================
echo.

python tests\run_tests.py
if %errorlevel% equ 0 (
    echo.
    echo [PASS] All automated tests passed successfully!
) else (
    echo.
    echo [FAIL] Some tests encountered errors.
)
pause
