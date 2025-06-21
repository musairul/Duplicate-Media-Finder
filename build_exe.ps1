# PowerShell script to build the executable
Write-Host "Building Duplicate Media Finder executable..." -ForegroundColor Green

# Sync dependencies using uv
Write-Host "Installing dependencies with uv..." -ForegroundColor Yellow
uv sync

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies!" -ForegroundColor Red
    exit 1
}

# Run PyInstaller to create the executable
Write-Host "Creating executable with PyInstaller..." -ForegroundColor Yellow
uv run pyinstaller `
    --onefile `
    --windowed `
    --name "DuplicateMediaFinder" `
    --add-data "*.py;." `
    --hidden-import=cv2 `
    --hidden-import=moviepy `
    --hidden-import=imagehash `
    --hidden-import=PIL `
    --hidden-import=numpy `
    --hidden-import=tkinter `
    --hidden-import=scipy.signal `
    --clean `
    app.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete! Executable can be found in the dist folder." -ForegroundColor Green
    Write-Host "File location: dist\DuplicateMediaFinder.exe" -ForegroundColor Cyan
} else {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Read-Host "Press Enter to continue..."
