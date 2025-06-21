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

## License

This project is open source. Feel free to modify and distribute.
