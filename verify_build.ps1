# Verify the build was successful
$exePath = "dist\DuplicateMediaFinder.exe"

if (Test-Path $exePath) {
    $fileInfo = Get-Item $exePath
    $sizeInMB = [math]::Round($fileInfo.Length / 1MB, 2)
    
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "File: $exePath" -ForegroundColor Cyan
    Write-Host "Size: $sizeInMB MB" -ForegroundColor Cyan
    Write-Host "Created: $($fileInfo.LastWriteTime)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "You can now run the executable by double-clicking it or using:" -ForegroundColor Yellow
    Write-Host "   .\dist\DuplicateMediaFinder.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "To test the executable, run:" -ForegroundColor Yellow
    Write-Host "   .\test_exe.bat" -ForegroundColor White
} else {
    Write-Host "Build failed - executable not found!" -ForegroundColor Red
    Write-Host "Expected location: $exePath" -ForegroundColor Red
}
