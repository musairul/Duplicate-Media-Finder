# Duplicate Media Finder

A desktop application for finding and removing duplicate images and videos using advanced hashing techniques.

## Features

- **Image Duplicate Detection**: Uses perceptual hashing to find visually similar images
- **Video Duplicate Detection**: Analyzes multiple frames and audio tracks to identify duplicate videos
- **Smart Thumbnail Generation**: Automatically selects the best frame for video thumbnails (avoids black/solid color frames)
- **Wizard-Style Interface**: Easy-to-use step-by-step process
- **Media Preview**: Built-in image and video player for reviewing files before deletion
- **Batch Operations**: Select all duplicates or review individually
- **Safe Deletion**: Always preserves the original (oldest) file in each duplicate group

## Supported Formats

### Images
- JPEG, PNG, BMP, TIFF, WebP, GIF, ICO

### Videos  
- MP4, AVI, MKV, MOV, WMV, WebM, M4V, FLV, MPG, MPEG, MTS

## Building the Executable

### Prerequisites
- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Build Steps

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Build the executable (choose one method):**

   **Option A - Using PowerShell (Recommended):**
   ```powershell
   .\build_exe.ps1
   ```

   **Option B - Using Command Prompt:**
   ```cmd
   build_exe.bat
   ```

   **Option C - Manual build:**
   ```bash
   uv run pyinstaller DuplicateMediaFinder.spec
   ```

3. **Find your executable:**
   The built executable will be located at `dist\DuplicateMediaFinder.exe`

## Usage

1. **Run the executable** - Double-click `DuplicateMediaFinder.exe`
2. **Add folders** - Select directories containing images/videos to scan
3. **Configure settings** - Adjust the number of frames to compare for videos (more frames = more accurate but slower)
4. **Start scan** - The app will analyze all media files and group duplicates
5. **Review results** - Preview files and select which duplicates to delete
6. **Delete safely** - The app automatically preserves the original (oldest) file in each group

## Technical Details

### Image Hashing
- Uses average hashing (aHash) algorithm via ImageHash library
- Resistant to minor edits, compression, and format changes
- Configurable hash size for precision vs speed trade-offs

### Video Analysis
- **Visual Analysis**: Samples frames evenly throughout the video duration
- **Audio Analysis**: Extracts audio track and generates MFCC-based fingerprint
- **Smart Frame Selection**: Automatically avoids black/solid color frames for thumbnails
- **Dual-stage Process**: Groups by visual similarity first, then refines using audio analysis

### Dependencies
- **OpenCV**: Video frame extraction and processing
- **Librosa**: Audio analysis and MFCC generation  
- **MoviePy**: Video/audio file handling
- **ImageHash**: Perceptual image hashing
- **Pillow**: Image processing and format support
- **NumPy**: Numerical operations
- **Tkinter**: GUI framework

## Performance Tips

- **Fewer frames per video** (3-10): Faster scanning, may miss some duplicates
- **More frames per video** (20-50): More accurate detection, slower scanning
- **Large collections**: Consider scanning subfolders separately for better progress tracking

## Troubleshooting

### Build Issues
- Ensure uv is installed and updated: `uv self update`
- Check Python version: `python --version` (should be 3.12+)
- For missing libraries, run: `uv sync --force`

### Runtime Issues
- **Video codec errors**: Install K-Lite Codec Pack or VLC media player
- **Large file hangs**: Try reducing frames-to-compare setting
- **Memory issues**: Close other applications, scan smaller folders

## License

This project is open source. Feel free to modify and distribute.
