@echo off
echo Testing DuplicateMediaFinder.exe...
echo.
echo Starting the application...
dist\DuplicateMediaFinder.exe

if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Application failed to start properly.
    pause
) else (
    echo.
    echo Application closed successfully.
)
