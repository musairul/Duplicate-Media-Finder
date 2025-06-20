# main.py
import os
import argparse
from PIL import Image
import imagehash
import cv2  # OpenCV for video processing
from tqdm import tqdm # For progress bars
import librosa
import numpy as np

# --- Configuration ---
# Supported file extensions for images and videos
IMAGE_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif', '.ico'
]
VIDEO_EXTENSIONS = [
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', 
    '.mpg', '.mpeg', '.mts'
]
# For videos, we sample one frame every N seconds to create a signature.
# A smaller number is more accurate but much slower. A larger number is faster.
VIDEO_FRAME_SAMPLE_RATE_SECONDS = 5

# Audio comparison settings
AUDIO_SIMILARITY_THRESHOLD = 0.85  # Threshold for considering two audio tracks similar (0-1)
AUDIO_SAMPLE_DURATION = 30  # Duration in seconds to sample for audio comparison

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


# --- Audio Comparison Functions ---

def extract_audio_features(filepath):
    """
    Extracts audio features from a video file for comparison.
    Returns MFCC features which are good for audio similarity comparison.
    Returns 'NO_AUDIO' string for videos with no audio track.
    """
    import warnings
    
    # Suppress librosa warnings about PySoundFile and audioread
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
        warnings.filterwarnings("ignore", category=FutureWarning, module="librosa")
        warnings.filterwarnings("ignore", message=".*PySoundFile failed.*")
        warnings.filterwarnings("ignore", message=".*audioread_load.*")
        
        try:
            # Load audio from video file, limit to sample duration
            y, sr = librosa.load(filepath, duration=AUDIO_SAMPLE_DURATION, sr=None)
            
            # Check if audio data was actually loaded
            if y is None or len(y) == 0:
                return 'NO_AUDIO'
            
            # Check if the audio is just silence (all zeros or very low amplitude)
            if np.max(np.abs(y)) < 1e-6:
                return 'NO_AUDIO'
            
            # Check if sample rate is valid
            if sr is None or sr <= 0:
                return 'NO_AUDIO'
            
            # Extract MFCC features (Mel-frequency cepstral coefficients)
            # These are commonly used for audio similarity comparison
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            
            # Check if MFCC extraction was successful
            if mfccs is None or mfccs.size == 0:
                return 'NO_AUDIO'
            
            # Calculate statistics to create a compact feature vector
            mfcc_mean = np.mean(mfccs, axis=1)
            mfcc_std = np.std(mfccs, axis=1)
            
            # Combine mean and std to create feature vector
            features = np.concatenate([mfcc_mean, mfcc_std])
            
            # Check if features are valid (not NaN or infinite)
            if np.any(np.isnan(features)) or np.any(np.isinf(features)):
                return 'NO_AUDIO'
            
            return features
            
        except Exception as e:
            # Handle specific common cases that indicate no audio
            error_msg = str(e).lower()
            if (len(error_msg.strip()) == 0 or  # Empty error message
                any(keyword in error_msg for keyword in [
                    'no audio', 'audio stream', 'stream', 'decoder', 
                    'could not find', 'no such file', 'input/output error',
                    'permission denied', 'invalid data', 'format not supported',
                    'no backend', 'failed to load', 'unknown format'
                ])):
                # Video has no audio track or unsupported audio format
                return 'NO_AUDIO'
            else:
                # Some other error occurred - only print if it's not an empty message
                if len(str(e).strip()) > 0:
                    print(f"Warning: Could not extract audio from {os.path.basename(filepath)}. Reason: {e}")
                return 'NO_AUDIO'  # Default to NO_AUDIO for any audio extraction failure

def compare_audio_similarity(features1, features2):
    """
    Computes similarity between two audio feature vectors.
    Returns a similarity score between 0 and 1 (1 being identical).
    Special handling for videos with no audio.
    """
    # Handle None values (failed to extract features)
    if features1 is None or features2 is None:
        return 0.0
    
    # Handle videos with no audio - they are considered identical to each other
    # Use isinstance to safely check for string type
    if isinstance(features1, str) and isinstance(features2, str):
        if features1 == 'NO_AUDIO' and features2 == 'NO_AUDIO':
            return 1.0
    
    # If one has audio and the other doesn't, they're not similar
    if isinstance(features1, str) and features1 == 'NO_AUDIO':
        return 0.0
    if isinstance(features2, str) and features2 == 'NO_AUDIO':
        return 0.0
    
    # At this point, both should be numpy arrays with actual audio features
    if not isinstance(features1, np.ndarray) or not isinstance(features2, np.ndarray):
        return 0.0
    
    # Calculate cosine similarity for normal audio features
    dot_product = np.dot(features1, features2)
    norm1 = np.linalg.norm(features1)
    norm2 = np.linalg.norm(features2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    # Convert to 0-1 range (cosine similarity is -1 to 1)
    return (similarity + 1) / 2

def filter_duplicates_by_audio(duplicate_groups):
    """
    Takes groups of visual duplicates and filters them based on audio similarity.
    Returns updated duplicate groups where audio is also similar.
    """
    if not duplicate_groups:
        return duplicate_groups
    
    print("\nComparing audio tracks between visual duplicates...")
    filtered_groups = {}
    
    for visual_hash, filepaths in tqdm(duplicate_groups.items(), desc="Audio comparison"):
        # Only compare audio for video files
        video_files = [fp for fp in filepaths if os.path.splitext(fp)[1].lower() in VIDEO_EXTENSIONS]
        
        if len(video_files) < 2:
            # If there are fewer than 2 video files in the group, keep the original group
            filtered_groups[visual_hash] = filepaths
            continue
          # Extract audio features for all video files in the group
        audio_features = {}
        for filepath in video_files:
            features = extract_audio_features(filepath)
            # Include all results: numpy arrays, 'NO_AUDIO', or None
            audio_features[filepath] = features
          # Group files by audio similarity
        audio_groups = []
        processed_files = set()
        
        for filepath1, features1 in audio_features.items():
            if filepath1 in processed_files or features1 is None:
                continue
            
            # Start a new audio group with this file
            current_group = [filepath1]
            processed_files.add(filepath1)
            
            # Find all other files with similar audio
            for filepath2, features2 in audio_features.items():
                if filepath2 in processed_files or features2 is None:
                    continue
                
                similarity = compare_audio_similarity(features1, features2)
                if similarity >= AUDIO_SIMILARITY_THRESHOLD:
                    current_group.append(filepath2)
                    processed_files.add(filepath2)
            
            # Only add groups with multiple files (duplicates)
            if len(current_group) > 1:
                audio_groups.append(current_group)
        
        # Add non-video files to each audio group (they were visual duplicates)
        non_video_files = [fp for fp in filepaths if fp not in video_files]
        
        # Create new hash keys for each audio group
        for i, audio_group in enumerate(audio_groups):
            new_hash = f"{visual_hash}_audio_{i}"
            filtered_groups[new_hash] = audio_group + non_video_files
    
    return filtered_groups


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
        help="One or more directories to scan for duplicates. \nExample: -d C:\\Users\\User\\Pictures D:\\Videos"    )
    
    args = parser.parse_args()
    
    print("--- Starting Duplicate Media Finder ---")
    duplicate_groups = find_duplicates(args.directories)
    
    print("\n--- Visual Scan Complete ---")
    
    if not duplicate_groups:
        print("No visually duplicate files found.")
    else:        # Filter duplicates by audio similarity
        print(f"Found {len(duplicate_groups)} groups of visually similar files.")
        duplicate_groups = filter_duplicates_by_audio(duplicate_groups)
        
        print(f"\nAfter audio comparison: {len(duplicate_groups)} groups of true duplicates.")
        
        if not duplicate_groups:
            print("No true duplicate files found after audio comparison.")
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
