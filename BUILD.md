# Build Instructions for Duplicate Media Finder

## Quick Start

The easiest way to build the executable is to run one of the provided build scripts:

### Option 1: PowerShell (Recommended)
```powershell
.\build_exe.ps1
```

### Option 2: Command Prompt
```cmd
build_exe.bat
```

## Manual Build Process

If you prefer to build manually:

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Build executable:**
   ```bash
   uv run pyinstaller --onefile --windowed --name "DuplicateMediaFinder" --clean main.py
   ```

## Output

- **Executable location:** `dist\DuplicateMediaFinder.exe`
- **Size:** ~125MB (includes all dependencies)
- **Type:** Standalone executable (no installation required)

## Verification

To verify the build was successful:
```powershell
.\verify_build.ps1
```

## Testing

To test the executable:
```cmd
.\test_exe.bat
```
or simply double-click `dist\DuplicateMediaFinder.exe`

## Distribution

The `DuplicateMediaFinder.exe` file in the `dist` folder is completely standalone and can be:
- Copied to any Windows computer
- Run without installing Python or any dependencies
- Distributed to end users

## File Structure

```
img-video-dup-finder/
├── main.py                    # Entry point for the application
├── pyproject.toml           # Project configuration and dependencies
├── build_exe.ps1            # PowerShell build script
├── build_exe.bat            # Batch build script
├── verify_build.ps1         # Build verification script
├── test_exe.bat             # Test script for the executable
├── README.md                # Documentation
├── .gitignore               # Git ignore file
├── dist/                    # Output directory (created after build)
│   └── DuplicateMediaFinder.exe
└── build/                   # Temporary build files (created during build)
```

## Troubleshooting

### Common Issues

1. **Build fails with missing modules:**
   - Run `uv sync` to ensure all dependencies are installed
   - Check Python version compatibility (requires Python 3.9+)

2. **Large executable size:**
   - This is normal for PyInstaller builds with scientific libraries
   - The size includes OpenCV, NumPy, MoviePy, and other dependencies

3. **Antivirus false positives:**
   - Some antivirus software may flag PyInstaller executables
   - This is a known issue with PyInstaller-generated executables
   - The executable is safe if built from this source code

### Performance Notes

- First startup may be slightly slower as the executable unpacks dependencies
- Subsequent runs will be faster
- The executable is optimized for distribution, not development

## Dependencies Included

The executable includes all necessary dependencies:
- Python runtime
- OpenCV for video processing
- NumPy for numerical operations
- Pillow for image processing
- MoviePy for video/audio handling
- ImageHash for perceptual hashing
- Tkinter for the GUI
- All other required libraries

No additional software installation is required on the target machine.
