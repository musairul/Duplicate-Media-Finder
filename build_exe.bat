@echo off
echo Building Duplicate Media Finder executable...

:: Sync dependencies using uv
echo Installing dependencies with uv...
uv sync

:: Run PyInstaller to create the executable
echo Creating executable with PyInstaller...
uv run pyinstaller ^
    --onefile ^
    --windowed ^
    --name "DuplicateMediaFinder" ^
    --add-data "*.py;." ^
    --hidden-import=cv2 ^
    --hidden-import=moviepy ^
    --hidden-import=imagehash ^
    --hidden-import=PIL ^
    --hidden-import=numpy ^
    --hidden-import=tkinter ^
    --hidden-import=scipy.signal ^
    --clean ^
    main.py

echo Build complete! Executable can be found in the dist folder.
pause
