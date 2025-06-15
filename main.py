# main.py
import os
import argparse
from PIL import Image
import imagehash
import cv2  # OpenCV for video processing
from tqdm import tqdm # For progress bars

# --- Configuration ---
# Supported file extensions for images and videos
IMAGE_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif', '.ico'
]
VIDEO_EXTENSIONS = [
    '.mp4', '.avi', 'mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', 
    '.mpg', '.mpeg', '.mts'
]
# For videos, we sample one frame every N seconds to create a signature.
# A smaller number is more accurate but much slower. A larger number is faster.
VIDEO_FRAME_SAMPLE_RATE_SECONDS = 5

# --- Core Hashing Functions ---

def get_image_hash(filepath, hash_size=8):
    """
    Computes the perceptual hash of an image file.
    Uses average hashing by default.
    """
    try:
        # For GIFs, Pillow opens the first frame by default, which is sufficient for a hash.
        with Image.open(filepath) as img:
            # Convert to a standard mode like RGB to handle formats like GIFs with palettes.
            img = img.convert('RGB')
            return imagehash.average_hash(img, hash_size=hash_size)
    except Exception as e:
        # print(f"Warning: Could not process image {filepath}. Reason: {e}")
        return None

def get_video_signature(filepath, hash_size=8):
    """
    Creates a signature for a video by hashing a sample of its frames.
    The signature is a sorted tuple of individual frame hashes.
    """
    try:
        video = cv2.VideoCapture(filepath)
        if not video.isOpened():
            # print(f"Warning: Could not open video file {filepath}.")
            return None

        frame_hashes = []
        fps = video.get(cv2.CAP_PROP_FPS)
        
        # Ensure FPS is valid to prevent division by zero
        if fps is None or fps == 0:
            # print(f"Warning: Could not read FPS from video {filepath}. Skipping.")
            return None
        
        frame_interval = int(fps * VIDEO_FRAME_SAMPLE_RATE_SECONDS)

        frame_count = 0
        while video.isOpened():
            success, frame = video.read()
            if not success:
                break

            # Sample the frame at the specified interval
            if frame_count % frame_interval == 0:
                # Convert the frame (which is a NumPy array) to a PIL Image
                try:
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    frame_hash = imagehash.average_hash(pil_img, hash_size=hash_size)
                    frame_hashes.append(str(frame_hash))
                except Exception as e:
                    # print(f"Warning: Could not process a frame from {filepath}. Reason: {e}")
                    pass # Continue to the next frame

            frame_count += 1
        
        video.release()

        if not frame_hashes:
            return None
        
        # Sort the hashes to make the signature independent of frame order
        frame_hashes.sort()
        # Join into a single string to act as a unique key
        return "".join(frame_hashes)

    except Exception as e:
        # print(f"Warning: A critical error occurred while processing video {filepath}. Reason: {e}")
        return None


# --- Main Logic ---

def find_duplicates(directories):
    """
    Scans directories, hashes all media files, and finds duplicates.
    """
    hashes = {} # Dictionary to store hashes and the file paths that match them
    
    # 1. Gather all files to be processed
    filepaths_to_scan = []
    print("Gathering files to scan...")
    for directory in directories:
        if not os.path.isdir(directory):
            print(f"Warning: '{directory}' is not a valid directory. Skipping.")
            continue
        for root, _, files in os.walk(directory):
            for filename in files:
                filepaths_to_scan.append(os.path.join(root, filename))

    # 2. Process each file with a progress bar
    print(f"\nFound {len(filepaths_to_scan)} files. Processing and hashing...")
    pbar = tqdm(filepaths_to_scan, unit="file")
    for filepath in pbar:
        pbar.set_description(f"Processing {os.path.basename(filepath)}")
        
        # Get the file extension
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        media_hash = None
        if ext in IMAGE_EXTENSIONS:
            media_hash = get_image_hash(filepath)
        elif ext in VIDEO_EXTENSIONS:
            media_hash = get_video_signature(filepath)
        
        if media_hash:
            # If the hash is not yet in our dictionary, add it.
            if media_hash not in hashes:
                hashes[media_hash] = []
            # Append the current file path to the list for this hash.
            hashes[media_hash].append(filepath)
    
    # 3. Filter for duplicates
    # A duplicate is any hash that has more than one file path associated with it.
    duplicates = {key: value for key, value in hashes.items() if len(value) > 1}
    return duplicates

def delete_duplicates(duplicate_groups):
    """
    Deletes duplicate files, keeping one original file from each group.
    """
    if not duplicate_groups:
        return # Nothing to do

    print("\n--- Deletion Preview ---")
    total_to_delete = 0
    for group_num, (media_hash, filepaths) in enumerate(duplicate_groups.items(), 1):
        # The first file in the list is kept, the rest are marked for deletion.
        print(f"Group {group_num}:")
        print(f"  [KEEPING] {filepaths[0]}")
        for path_to_delete in filepaths[1:]:
            print(f"  [DELETING] {path_to_delete}")
            total_to_delete += 1
        print("")

    if total_to_delete == 0:
        print("No files to delete.")
        return

    print(f"WARNING: You are about to permanently delete {total_to_delete} file(s).")
    
    # Ask for user confirmation
    try:
        confirm = input("Are you sure you want to proceed? (y/n): ")
    except EOFError:
        # This can happen if the script is run in a non-interactive environment
        print("\nNon-interactive mode detected. Aborting deletion.")
        return
        
    if confirm.lower() != 'y':
        print("Deletion cancelled by user.")
        return

    print("\n--- Starting Deletion ---")
    deleted_count = 0
    for filepaths in duplicate_groups.values():
        # The logic is to keep the first file (at index 0) and delete the rest.
        for file_to_delete in filepaths[1:]:
            try:
                os.remove(file_to_delete)
                print(f"Deleted: {file_to_delete}")
                deleted_count += 1
            except OSError as e:
                print(f"Error deleting {file_to_delete}: {e}")
    print(f"\nDeletion complete. Successfully deleted {deleted_count} file(s).")


def main():
    """Main function to parse arguments and run the duplicate finder."""
    parser = argparse.ArgumentParser(
        description="Finds and optionally deletes duplicate photos and videos based on visual similarity.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-d', '--directories',
        nargs='+',  # This allows specifying one or more directories
        required=True,
        help="One or more directories to scan for duplicates. \nExample: -d C:\\Users\\User\\Pictures D:\\Videos"
    )
    
    args = parser.parse_args()
    
    print("--- Starting Duplicate Media Finder ---")
    duplicate_groups = find_duplicates(args.directories)
    
    print("\n--- Scan Complete ---")
    
    if not duplicate_groups:
        print("No duplicate files found.")
    else:
        # First, print the report of found duplicates
        print(f"Found {len(duplicate_groups)} groups of duplicate files.\n")
        group_num = 1
        for media_hash, filepaths in duplicate_groups.items():
            print(f"--- Group {group_num} ---")
            for path in filepaths:
                print(f"  - {path}")
            print("") # Newline for spacing
            group_num += 1
        
        # Now, ask the user if they want to proceed with deletion
        print("--------------------------------------------------")
        try:
            prompt_delete = input("Would you like to proceed with deleting the duplicate files? (y/n): ")
        except EOFError:
            prompt_delete = 'n'
        
        if prompt_delete.lower() == 'y':
            delete_duplicates(duplicate_groups)
        else:
            print("\nDeletion skipped. No files were changed.")
            
    print("\n--- End of Report ---")

if __name__ == "__main__":
    main()
