# main_wizard_gui.py
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
import imagehash
import numpy as np
from moviepy.editor import VideoFileClip
from PIL import Image, ImageTk, ImageSequence

# --- Configuration ---
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif', '.ico']
VIDEO_EXTENSIONS = ['.mp4', '.avi', 'mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', '.mpg', '.mpeg', '.mts']
THUMBNAIL_SIZE = (128, 128)
# New preview size to better accommodate widescreen video
PREVIEW_SIZE = (640, 480)
# Preview pane will be calculated as 1/3 of window width
PREVIEW_PANE_WIDTH = 400  # Base minimum width

# --- Core Hashing Functions ---
def get_image_hash(filepath, hash_size=8):
    try:
        with Image.open(filepath) as img:
            return imagehash.average_hash(img.convert('RGB'), hash_size=hash_size)
    except Exception: return None

def get_video_signature(filepath, hash_size=8, frames_to_compare=10):
    """Generate a signature for a video by sampling frames evenly throughout the video"""
    try:
        # Suppress OpenCV error messages
        cv2.setLogLevel(0)
        
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened(): 
            return None
            
        # Get total frame count and FPS
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        if total_frames <= 0 or not fps or fps == 0:
            cap.release()
            return None
        
        # If video has fewer frames than requested, use all frames
        actual_frames_to_sample = min(frames_to_compare, total_frames)
        
        # Calculate frame indices to sample evenly throughout the video
        if actual_frames_to_sample == 1:
            frame_indices = [total_frames // 2]  # Middle frame
        else:
            frame_indices = [int(i * (total_frames - 1) / (actual_frames_to_sample - 1)) 
                           for i in range(actual_frames_to_sample)]
        
        hashes = []
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                try:
                    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    hashes.append(str(imagehash.average_hash(img, hash_size=hash_size)))
                except Exception:
                    continue  # Skip corrupted frames
        
        cap.release()
        
        if not hashes: 
            return None
            
        # Sort hashes to ensure consistent signatures regardless of frame order
        hashes.sort()
        return "".join(hashes)
        
    except Exception:
        return None

def get_audio_hash(filepath, hash_size=8):
    """Extracts audio properties and returns a tuple of (hash, issue_description).
    issue_description is None if no issues, otherwise describes the fallback used."""
    import threading
    import queue
    
    def load_video_clip(filepath, result_queue):
        """Load VideoFileClip in a separate thread"""
        try:
            print(f"[DEBUG] Thread: Attempting to load VideoFileClip...")
            with VideoFileClip(filepath) as video_clip:
                print(f"[DEBUG] Thread: Video clip loaded successfully")
                print(f"[DEBUG] Thread: Video duration: {video_clip.duration}")
                print(f"[DEBUG] Thread: Video fps: {video_clip.fps}")
                
                if video_clip.audio is None:
                    print(f"[DEBUG] Thread: No audio track found in video")
                    result_queue.put(("success", "no_audio", None))  # No issue for missing audio
                    return
                
                print(f"[DEBUG] Thread: Audio track found")
                
                # Get basic audio properties
                try:
                    duration = video_clip.audio.duration
                    print(f"[DEBUG] Thread: Audio duration: {duration}")
                except Exception as e:
                    print(f"[DEBUG] Thread: Error getting audio duration: {e}")
                    duration = 0
                
                try:
                    fps = video_clip.audio.fps if hasattr(video_clip.audio, 'fps') else 44100
                    print(f"[DEBUG] Thread: Audio fps: {fps}")
                except Exception as e:
                    print(f"[DEBUG] Thread: Error getting audio fps: {e}")
                    fps = 44100
                    
                try:
                    nchannels = video_clip.audio.nchannels if hasattr(video_clip.audio, 'nchannels') else 2
                    print(f"[DEBUG] Thread: Audio channels: {nchannels}")
                except Exception as e:
                    print(f"[DEBUG] Thread: Error getting audio channels: {e}")
                    nchannels = 2
                
                # Create a simple hash based on duration and basic properties
                audio_signature = f"{int(duration)}_{int(fps)}_{nchannels}"
                print(f"[DEBUG] Thread: Audio signature: {audio_signature}")
                
                # Convert to a numeric hash for consistency
                hash_value = hash(audio_signature) % (10**8)
                print(f"[DEBUG] Thread: Generated hash: {hash_value}")
                result_queue.put(("success", str(hash_value), None))
                
        except Exception as e:
            print(f"[DEBUG] Thread: Exception during VideoFileClip processing: {type(e).__name__}: {e}")
            result_queue.put(("error", str(e), f"MoviePy error: {type(e).__name__}"))
    
    try:
        print(f"[DEBUG] Processing audio for: {os.path.basename(filepath)}")
        
        # Create a queue for thread communication
        result_queue = queue.Queue()
        
        # Start the video loading in a separate thread
        thread = threading.Thread(target=load_video_clip, args=(filepath, result_queue), daemon=True)
        thread.start()
          # Wait for the thread with a timeout
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            print(f"[DEBUG] VideoFileClip loading timed out after 30 seconds")
            # Thread is still running, we'll abandon it and use fallback
            
            # Try alternative approach using OpenCV for basic file info
            print(f"[DEBUG] Attempting fallback with OpenCV...")
            try:
                cap = cv2.VideoCapture(filepath)
                if cap.isOpened():
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    duration = frame_count / fps if fps > 0 else 0
                    cap.release()
                    
                    # Create a basic signature from video properties
                    fallback_signature = f"fallback_{int(duration)}_{int(fps)}_unknown"
                    fallback_hash = hash(fallback_signature) % (10**8)
                    print(f"[DEBUG] Fallback signature: {fallback_signature}")
                    print(f"[DEBUG] Fallback hash: {fallback_hash}")
                    return str(fallback_hash), "Failed to process audio"
                else:
                    print(f"[DEBUG] OpenCV fallback also failed")
                    return "opencv_error", "Failed to process audio - OpenCV error"
            except Exception as cv_exception:
                print(f"[DEBUG] OpenCV fallback exception: {type(cv_exception).__name__}: {cv_exception}")
                return "fallback_error", "Failed to process audio - fallback error"
        else:
            # Thread completed, get the result
            try:
                status, result, issue = result_queue.get_nowait()
                if status == "success":
                    print(f"[DEBUG] Successfully got result: {result}")
                    return result, issue
                else:
                    print(f"[DEBUG] Thread returned error: {result}")
                    # Fall back to OpenCV approach
                    print(f"[DEBUG] Attempting fallback with OpenCV...")
                    try:
                        cap = cv2.VideoCapture(filepath)
                        if cap.isOpened():
                            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            duration = frame_count / fps if fps > 0 else 0
                            cap.release()
                            
                            fallback_signature = f"fallback_{int(duration)}_{int(fps)}_unknown"
                            fallback_hash = hash(fallback_signature) % (10**8)
                            print(f"[DEBUG] Fallback signature: {fallback_signature}")
                            print(f"[DEBUG] Fallback hash: {fallback_hash}")
                            return str(fallback_hash), f"Audio processing failed - used video metadata fallback ({issue})"
                        else:
                            return "opencv_error", "Failed to process audio - OpenCV error"
                    except Exception:
                        return "fallback_error", "Failed to process audio - fallback error"
            except queue.Empty:
                print(f"[DEBUG] Thread completed but no result available")
                return "thread_error", "Audio processing failed - no result available"
            
    except Exception as e:
        print(f"[DEBUG] Outer exception in get_audio_hash for {os.path.basename(filepath)}: {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG] Full traceback:")
        traceback.print_exc()
        return "audio_error", f"Audio processing error: {type(e).__name__}"  # Generic hash for any processing error

# --- Main Application Class (Wizard Style) ---
class DuplicateFinderWizard:
    def __init__(self, root):
        self.root = root
        self.root.title("Duplicate Media Finder Wizard")
        self.style = ttk.Style()
        self.bg_colour = self.style.lookup('TFrame', 'background')

          # --- State ---
        self.current_screen = None
        self.scan_directories = set()
        self.duplicate_groups = {}
        self.kept_files = []
        self.checkbox_vars = {}
        self.active_media_player = None
        self.frames_to_compare = 10  # Default number of frames to compare per video
        self.audio_processing_issues = {}  # Track files with audio processing problems

        # --- Screens ---
        self.screens = {
            "folder_selection": self.create_folder_selection_screen(),
            "scanning": self.create_scanning_screen(),
            "results": self.create_results_screen(),
            "deleting": self.create_deleting_screen(),
            "final_report": self.create_final_report_screen(),
        }
        self.show_screen("folder_selection")

    def show_screen(self, screen_name):
        if self.current_screen:
            self.current_screen.pack_forget()
        
        if self.active_media_player:
            self.active_media_player.stop()
            self.active_media_player = None
            
        # --- Dynamic Window Sizing ---
        if screen_name in ["results", "final_report"]:
            self.root.geometry("1280x720")
            self.root.minsize(800, 600)  # Increased minimum to accommodate both sections properly
            self.root.resizable(True, True)  # Allow resizing in case user has many folders
        elif screen_name in ["scanning", "deleting"]:
            self.root.geometry("500x220")  # Reduced height since we only have one progress bar
            self.root.minsize(500, 220)
            self.root.resizable(True, True)
        elif screen_name == "folder_selection":
            self.root.geometry("500x320")  # Increased height to show header, settings, and buttons properly
            self.root.minsize(450, 320)
            self.root.resizable(True, True)  # Allow resizing in case user has many folders
        else:
            self.root.geometry("600x400")
            self.root.minsize(600, 350)
            self.root.resizable(False, False)
            
        self.current_screen = self.screens[screen_name]
        self.current_screen.pack(expand=True, fill=tk.BOTH)

    # --- Screen 1: Folder Selection ---
    def create_folder_selection_screen(self):
        frame = ttk.Frame(self.root)
        
        header = ttk.Label(frame, text="Step 1: Select Folders to Scan", font=("Helvetica", 16, "bold"))
        header.pack(pady=20, anchor='center')

        self.list_frame = ttk.LabelFrame(frame, text="Folders to Scan")
        
        self.folder_listbox = tk.Listbox(self.list_frame, selectmode=tk.MULTIPLE, bg="#f0f0f0", borderwidth=0, highlightthickness=0)
        self.folder_scrollbar = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.folder_listbox.yview)
        self.folder_listbox.config(yscrollcommand=self.folder_scrollbar.set)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20, anchor='center')
        ttk.Button(btn_frame, text="Add Folder...", command=self.add_folder).pack(side=tk.LEFT, padx=10)
        self.remove_folder_btn = ttk.Button(btn_frame, text="Remove Selected", command=self.remove_folder, state=tk.DISABLED)
        self.start_scan_btn = ttk.Button(btn_frame, text="Start Scan ➤", style="Accent.TButton", command=self.start_scan, state=tk.DISABLED)
        
        # Video comparison settings frame
        settings_frame = ttk.LabelFrame(frame, text="Video Comparison Settings")
        settings_frame.pack(pady=20, padx=20, fill='x')
        
        # Frames to compare slider
        frames_label_frame = ttk.Frame(settings_frame)
        frames_label_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(frames_label_frame, text="Frames to compare per video:", font=("Helvetica", 10)).pack(side=tk.LEFT)
        self.frames_value_label = ttk.Label(frames_label_frame, text=f"{self.frames_to_compare}", font=("Helvetica", 10, "bold"))
        self.frames_value_label.pack(side=tk.RIGHT)
        
        self.frames_slider = ttk.Scale(settings_frame, from_=3, to=50, orient=tk.HORIZONTAL, 
                                      command=self.on_frames_slider_change, length=300)
        self.frames_slider.set(self.frames_to_compare)
        self.frames_slider.pack(padx=10, pady=(0, 10))
        
        # Help text
        help_text = ttk.Label(settings_frame, 
                             text="More frames = more accurate detection but slower processing\n"
                                  "Fewer frames = faster processing but may miss some duplicates",
                             font=("Helvetica", 9), foreground="gray")
        help_text.pack(padx=10, pady=(0, 10))
        
        # Initially hide the remove and scan buttons - they'll be shown when folders are added
        # Don't pack them initially
        
        return frame

    def add_folder(self):
        dir_path = filedialog.askdirectory()
        if dir_path and dir_path not in self.scan_directories:
            if not self.scan_directories:
                self.list_frame.pack(pady=10, padx=20, fill='x', before=self.start_scan_btn.master)
                self.folder_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
                self.folder_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            self.scan_directories.add(dir_path)
            self.folder_listbox.insert(tk.END, dir_path)
            self.folder_listbox.config(height=len(self.scan_directories))
            # Resize window to fit content
            self._resize_folder_selection_window()
            self._update_folder_buttons()

    def remove_folder(self):
        selected_indices = self.folder_listbox.curselection()
        for i in sorted(selected_indices, reverse=True):
            self.scan_directories.remove(self.folder_listbox.get(i))
            self.folder_listbox.delete(i)
        
        list_size = len(self.scan_directories)
        self.folder_listbox.config(height=list_size)
        
        if list_size == 0:
            self.list_frame.pack_forget()
        # Resize window to fit content
        self._resize_folder_selection_window()
        self._update_folder_buttons()

    def _resize_folder_selection_window(self):
        """Resize the window to fit the folder list content"""
        # Update the UI to ensure proper sizing calculations        self.root.update_idletasks()
        
        # Calculate required height based on content
        base_height = 320  # Header + settings frame + button frame + padding (increased to account for slider)
        if len(self.scan_directories) > 0:
            # Add height for the list frame (approximately 20px per item + frame padding)
            list_height = len(self.scan_directories) * 20 + 60  # 60 for frame and padding
            total_height = base_height + list_height
        else:
            total_height = base_height
          # Set reasonable bounds
        min_height = 320  # Increased minimum height to account for slider
        max_height = 500  # Don't make it too tall
        final_height = max(min_height, min(max_height, total_height))
        
        # Keep width reasonable
        width = 500
        
        # Apply the new geometry
        self.root.geometry(f"{width}x{final_height}")

    def _update_folder_buttons(self):
        """Update button visibility based on folder selection"""
        if self.scan_directories:
            # Show buttons when folders are selected
            self.remove_folder_btn.pack(side=tk.LEFT, padx=10)
            self.start_scan_btn.pack(side=tk.LEFT, padx=20)
            self.remove_folder_btn.config(state=tk.NORMAL)
            self.start_scan_btn.config(state=tk.NORMAL)
        else:
            # Hide buttons when no folders are selected
            self.remove_folder_btn.pack_forget()
            self.start_scan_btn.pack_forget()

    def on_frames_slider_change(self, value):
        """Callback for when the frames slider value changes"""
        self.frames_to_compare = int(float(value))
        self.frames_value_label.config(text=f"{self.frames_to_compare}")

    def start_scan(self):
        if not self.scan_directories:
            messagebox.showwarning("No Folders", "Please add at least one folder to scan.")
            return
        self.show_screen("scanning")
        threading.Thread(target=self.scan_thread, daemon=True).start()

    # --- Screen 2: Scanning ---
    def create_scanning_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Step 2: Scanning...", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        # Overall progress section
        overall_label_frame = ttk.Frame(frame)
        overall_label_frame.pack(pady=5)
        ttk.Label(overall_label_frame, text="Overall Progress", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        self.scan_overall_percentage = ttk.Label(overall_label_frame, text="0%")
        self.scan_overall_percentage.pack(side=tk.RIGHT)
        
        self.scan_overall_progress_bar = ttk.Progressbar(frame, mode='determinate', length=400)
        self.scan_overall_progress_bar.pack(pady=(5, 15))
        
        self.scan_status_label = ttk.Label(frame, text="Gathering files...", wraplength=450, justify='center')
        self.scan_status_label.pack(pady=10)
        
        # Audio issues counter
        self.scan_audio_issues_label = ttk.Label(frame, text="", foreground="orange", font=("Helvetica", 9))
        self.scan_audio_issues_label.pack(pady=5)
        
        return frame

    def scan_thread(self):
        self.duplicate_groups.clear()
        self.audio_processing_issues.clear()  # Clear previous issues
        filepaths = [os.path.join(r, f) for d in self.scan_directories for r, _, fs in os.walk(d) for f in fs]
        total = len(filepaths)
        
        # Initialize progress bar
        self.scan_overall_progress_bar['maximum'] = 100  # Overall progress in percentage
        hashes = {}
        
        # Step 1: Initial scan for images and visual hash for videos (50% of overall progress)
        for i, path in enumerate(filepaths):
            # Show current file starting to be processed
            overall_progress = (i / total) * 50  # First half of overall progress
            self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                          self.update_scan_status(f"Processing visuals ({n+1}/{total}): {os.path.basename(p)}", op))
            
            ext = os.path.splitext(path)[1].lower()
            h = None
            if ext in IMAGE_EXTENSIONS:
                h = get_image_hash(path)
            elif ext in VIDEO_EXTENSIONS:
                h = get_video_signature(path, frames_to_compare=self.frames_to_compare)
            
            if h:
                if h not in hashes: hashes[h] = []
                hashes[h].append(path)
            
            # Update overall progress after completing this file
            overall_progress = ((i + 1) / total) * 50
            self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                          self.update_scan_status(f"Completed visuals ({n+1}/{total}): {os.path.basename(p)}", op))
        
        # Initial duplicate groups based on visual similarity
        visual_duplicate_groups = {k: v for k, v in hashes.items() if len(v) > 1}
        final_duplicate_groups = {}
        
        # Step 2: Refine video groups with audio hashing (remaining 50% of overall progress)
        group_counter = 0
        total_video_files = sum(len(paths) for paths in visual_duplicate_groups.values() 
                               if any(os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS for p in paths))
        processed_video_files = 0
        
        for visual_hash, paths in visual_duplicate_groups.items():
            is_video_group = any(os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS for p in paths)

            if is_video_group:
                audio_groups = {}
                for i, path in enumerate(paths):
                    # Show current file starting to be processed for audio
                    overall_progress = 50 + (processed_video_files / total_video_files) * 50
                    self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                                  self.update_scan_status(f"Processing audio for group {group_counter+1} ({n+1}/{len(paths)}): {os.path.basename(p)}", op))
                    
                    print(f"\n[SCAN DEBUG] Starting audio processing for: {path}")
                    print(f"[SCAN DEBUG] File extension: {os.path.splitext(path)[1].lower()}")
                    print(f"[SCAN DEBUG] File size: {os.path.getsize(path) / (1024*1024):.2f} MB")
                    
                    audio_h, audio_issue = get_audio_hash(path)
                    print(f"[SCAN DEBUG] Audio hash result: {audio_h}")
                      # Track audio processing issues
                    if audio_issue:
                        self.audio_processing_issues[path] = audio_issue
                        print(f"[SCAN DEBUG] Audio issue tracked: {audio_issue}")
                        # Update status to show audio issue
                        self.root.after(0, lambda p=path, n=i, op=overall_progress, issue=audio_issue: 
                                      self.update_scan_status(f"Audio issue for group {group_counter+1} ({n+1}/{len(paths)}): {os.path.basename(p)} - {issue}", op))
                        # Update audio issues counter
                        issue_count = len(self.audio_processing_issues)
                        self.root.after(0, lambda count=issue_count: 
                                      self.update_audio_issues_counter(count))
                    else:
                        # Complete audio processing for this file
                        self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                                      self.update_scan_status(f"Completed audio for group {group_counter+1} ({n+1}/{len(paths)}): {os.path.basename(p)}", op))
                    
                    if audio_h not in audio_groups:
                        audio_groups[audio_h] = []
                    audio_groups[audio_h].append(path)
                    
                    processed_video_files += 1

                # Add subgroups that are actual duplicates (more than one item)
                for audio_hash, audio_paths in audio_groups.items():
                    if len(audio_paths) > 1:
                        # Create a unique key for the final group
                        final_group_key = f"{visual_hash}_{audio_hash}"
                        final_duplicate_groups[final_group_key] = audio_paths
            else:
                # This is an image group, add it directly
                final_duplicate_groups[visual_hash] = paths
            group_counter += 1
            
        self.duplicate_groups = final_duplicate_groups
          # Sort each group by creation date (oldest first) so the original is typically the oldest
        for key in self.duplicate_groups:
            self.duplicate_groups[key].sort(key=lambda path: self.get_file_creation_time(path))
          # Set to 100% completion
        final_status = "Scan complete!"
        if self.audio_processing_issues:
            issue_count = len(self.audio_processing_issues)
            final_status += f" (Note: {issue_count} file(s) had audio processing issues)"
        
        self.root.after(0, lambda: self.update_scan_status(final_status, 100))
        self.root.after(0, self.on_scan_complete)

    def update_scan_status(self, text, overall_percentage):
        self.scan_status_label.config(text=text)
        self.scan_overall_progress_bar['value'] = overall_percentage
        self.scan_overall_percentage.config(text=f"{overall_percentage:.1f}%")

    def update_audio_issues_counter(self, count):
        """Update the audio issues counter during scanning"""
        if count > 0:
            text = f"⚠️ {count} file(s) with audio processing issues"
            self.scan_audio_issues_label.config(text=text)
        else:
            self.scan_audio_issues_label.config(text="")

    def on_scan_complete(self):
        if not self.duplicate_groups:
            messagebox.showinfo("Scan Complete", "No duplicate files were found.")
            self.close_app()
            return
        self.build_results_grid()
        self.update_results_summary()  # Update the summary with audio issues
        self.show_screen("results")

    def update_results_summary(self):
        """Update the results screen summary to show audio processing issues"""
        if self.audio_processing_issues:
            issue_count = len(self.audio_processing_issues)
            summary_text = f"Found {len(self.duplicate_groups)} duplicate groups.\nNote: {issue_count} file(s) had audio processing issues (marked with ⚠️)"
        else:
            summary_text = f"Found {len(self.duplicate_groups)} duplicate groups."
        
        if hasattr(self, 'results_status_label'):
            self.results_status_label.config(text=summary_text)

    # --- Screen 3: Results ---
    def create_results_screen(self):
        frame = ttk.Frame(self.root)
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(header_frame, text="Step 3: Review Duplicates", font=("Helvetica", 16, "bold")).pack(side=tk.LEFT)
        
        # Use Frame with grid layout for fixed sections (non-resizable)
        main_content_frame = ttk.Frame(frame)
        main_content_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        
        # Configure grid layout with fixed proportions
        main_content_frame.grid_columnconfigure(0, weight=2)  # 2/3 for duplicates, min 500px
        main_content_frame.grid_columnconfigure(1, weight=1)  # Fixed width for preview
        main_content_frame.grid_rowconfigure(0, weight=1)
        
        # Left section for duplicates grid
        grid_container = ttk.Frame(main_content_frame)
        grid_container.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        # Right section for preview - fixed width
        self.results_preview_pane = self._create_preview_pane(main_content_frame)
        self.results_preview_pane['frame'].grid(row=0, column=1, sticky='nsew', padx=(5, 0))

        results_header = ttk.Frame(grid_container)
        results_header.pack(fill='x', pady=5, padx=5)
        ttk.Button(results_header, text="Select All Duplicates", command=self.select_all_duplicates).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(results_header, text="Deselect All", command=lambda: self.set_all_checkboxes(0)).pack(side=tk.LEFT)
        self.results_status_label = ttk.Label(results_header, text=" ", foreground="blue") # Use a space to reserve height
        self.results_status_label.pack(side=tk.LEFT, padx=20)
        
        self.canvas_scroll_frame = tk.Canvas(grid_container, bg=self.bg_colour, highlightthickness=0)
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas_scroll_frame.yview)
        self.results_grid_frame = ttk.Frame(self.canvas_scroll_frame)
        self.canvas_scroll_frame.create_window((0, 0), window=self.results_grid_frame, anchor="nw")
        self.canvas_scroll_frame.configure(yscrollcommand=scrollbar.set)
        
        self.canvas_scroll_frame.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.results_grid_frame.bind("<Configure>", lambda e: self.canvas_scroll_frame.configure(scrollregion=self.canvas_scroll_frame.bbox("all")))
        self.canvas_scroll_frame.bind_all("<MouseWheel>", self._on_mousewheel)
        
        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=20, padx=20)
        ttk.Button(footer, text="Delete Selected Files 🗑️", style="Accent.TButton", command=self.start_deletion).pack(side=tk.RIGHT)
        
        return frame
        
    def _on_mousewheel(self, event):
        active_canvas = None
        if self.current_screen == self.screens['results']:
            active_canvas = self.canvas_scroll_frame
        elif self.current_screen == self.screens['final_report']:
            active_canvas = self.final_canvas

        # For results screen, allow scrolling anywhere on the page
        if self.current_screen == self.screens['results'] and active_canvas:
            active_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        # For other screens, check if mouse is over the specific canvas
        elif active_canvas and hasattr(active_canvas, 'winfo_containing') and active_canvas.winfo_containing(event.x_root, event.y_root) == active_canvas:
            active_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def build_results_grid(self):
        # This function is now only for building the grid, not reloading it.
        # Store thumbnail widgets to prevent reloading
        self.thumbnail_widgets = {} 
        for widget in self.results_grid_frame.winfo_children():
            widget.destroy()
        self.checkbox_vars.clear()

        # Iterate through groups to create a grouped layout
        for i, (hash_val, paths) in enumerate(self.duplicate_groups.items()):
            group_frame = ttk.LabelFrame(self.results_grid_frame, text=f"Group {i+1} ({len(paths)} items)")
            group_frame.pack(fill='x', expand=True, padx=10, pady=10)

            container_width = group_frame.winfo_width()
            if container_width <= 1: container_width = self.results_grid_frame.winfo_width()
            if container_width <= 1: container_width = 800 # Fallback
            max_cols = max(1, container_width // (THUMBNAIL_SIZE[0] + 20))

            for j, filepath in enumerate(paths):
                row, col = divmod(j, max_cols)
                
                item_frame = ttk.Frame(group_frame, padding=5)
                item_frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                
                is_original = (j == 0)  # First item in each group is the original
                
                if is_original:
                    # Original - cannot be selected for deletion
                    # Don't create a checkbox for originals
                    
                    # Add simple "Original" label
                    original_label = tk.Label(item_frame, text="Original", fg='black', font=('Arial', 9))
                    original_label.pack(pady=2)
                    
                    # Standard thumbnail styling
                    thumb_bg = 'gray'
                    thumb_relief = 'raised'
                    
                    # Don't add to checkbox_vars since there's no checkbox
                else:
                    # Duplicate - can be selected for deletion
                    var = tk.BooleanVar(value=False)
                    checkbox = ttk.Checkbutton(item_frame, variable=var)
                    checkbox.pack()
                    
                    thumb_bg = 'gray'
                    thumb_relief = 'raised'
                    
                    self.checkbox_vars[filepath] = var
                
                thumb_label = tk.Label(item_frame, bg=thumb_bg, relief=thumb_relief, width=THUMBNAIL_SIZE[0], height=THUMBNAIL_SIZE[1])
                thumb_label.pack(pady=5)
                thumb_label.bind("<Button-1>", lambda e, p=filepath: self.on_thumbnail_click(p))
                self.thumbnail_widgets[filepath] = thumb_label # Store reference

                # Show filename
                filename_label = ttk.Label(item_frame, text=os.path.basename(filepath), wraplength=THUMBNAIL_SIZE[0])
                filename_label.pack()
                
                # Show audio processing issue if any
                if filepath in self.audio_processing_issues:
                    issue_text = self.audio_processing_issues[filepath]
                    # Truncate long error messages
                    if len(issue_text) > 50:
                        issue_text = issue_text[:47] + "..."
                    
                    issue_label = tk.Label(item_frame, text=f"⚠️ {issue_text}", 
                                         fg='orange', font=('Arial', 8), 
                                         wraplength=THUMBNAIL_SIZE[0])
                    issue_label.pack(pady=(2, 0))
                
                threading.Thread(target=self.load_thumbnail, args=(filepath, thumb_label), daemon=True).start()

    def on_thumbnail_click(self, filepath):
        if self.active_media_player:
            self.active_media_player.stop()
            self.active_media_player = None

        preview_widgets = None
        if self.current_screen == self.screens['results']:
            preview_widgets = self.results_preview_pane
        elif self.current_screen == self.screens['final_report']:
            preview_widgets = self.final_report_preview_pane
        
        if not preview_widgets: return
        
        preview_widgets['video_controls'].pack_forget()
        preview_widgets['gif_controls'].pack_forget()

        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.gif':
            preview_widgets['gif_controls'].pack(fill='x', pady=5)
            self.active_media_player = GifPlayer(filepath, preview_widgets['canvas'], preview_widgets['gif_play'])
            # Autoplay GIF
            self.active_media_player.toggle_play_pause()
        elif ext in VIDEO_EXTENSIONS:
            preview_widgets['video_controls'].pack(fill='x', pady=5)
            preview_widgets['seek'].set(0)
            self.active_media_player = VideoPlayerCV(filepath, preview_widgets)
            # Autoplay video
            self.active_media_player.toggle_play_pause()
        elif ext in IMAGE_EXTENSIONS:
            self.display_image_preview(filepath, preview_widgets['canvas'])

    def display_image_preview(self, filepath, canvas):
        try:
            img = Image.open(filepath)
            # Get canvas dimensions for responsive sizing
            canvas.update_idletasks()  # Ensure canvas dimensions are updated
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            # Use canvas dimensions if available, otherwise fallback to PREVIEW_SIZE
            if canvas_width > 1 and canvas_height > 1:
                # Add some padding to ensure image fits well within canvas
                max_size = (canvas_width - 20, canvas_height - 20)
            else:
                max_size = PREVIEW_SIZE
                
            img.thumbnail(max_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            canvas.delete("all")
            canvas.create_image(canvas.winfo_width()/2, canvas.winfo_height()/2, anchor='center', image=photo)
            canvas.image = photo
        except Exception:
            canvas.delete("all")
            canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2, text="Preview not available", fill="red")

    def is_solid_color_image(self, img, threshold=0.85):
        """
        Check if an image is mostly a solid color (like all black).
        Returns True if more than threshold% of pixels are the same color.
        Optimized for thumbnail-sized images.
        
        Args:
            img: PIL Image object
            threshold: Float between 0-1. Default 0.85 means 85% of pixels must be same color
        """
        try:
            # Convert to numpy array for faster processing
            img_array = np.array(img)
            
            # For very small images (thumbnails), check all pixels
            height, width = img_array.shape[:2]
            total_pixels = height * width
            
            # Simple approach: check if image is mostly one color
            if len(img_array.shape) == 2:  # Grayscale
                unique_values, counts = np.unique(img_array, return_counts=True)
                max_count = np.max(counts)
            else:  # Color image (RGB/RGBA)
                # Convert to grayscale to simplify detection of "black" or solid colors
                if img_array.shape[-1] >= 3:  # RGB or RGBA
                    # Convert to grayscale using standard weights
                    gray = np.dot(img_array[...,:3], [0.2989, 0.5870, 0.1140])
                    unique_values, counts = np.unique(gray.astype(np.uint8), return_counts=True)
                    max_count = np.max(counts)
                else:
                    # Single channel, treat as grayscale
                    unique_values, counts = np.unique(img_array, return_counts=True)
                    max_count = np.max(counts)
            
            # Check if the most common color takes up more than threshold% of the image
            dominant_ratio = max_count / total_pixels
            
            # Additional check: if the most common color is very dark (likely black/near-black)
            # be more aggressive in detecting it as solid color
            if len(unique_values) > 0:
                most_common_idx = np.argmax(counts)
                most_common_value = unique_values[most_common_idx]
                
                # If most common color is very dark (0-30 on 0-255 scale), lower the threshold
                if most_common_value <= 30:  # Very dark colors
                    return dominant_ratio > 0.75  # Lower threshold for dark colors
                else:
                    return dominant_ratio > threshold
            
            return dominant_ratio > threshold
            
        except Exception:            # If analysis fails, assume it's not solid color (safer default)
            return False

    def load_thumbnail(self, filepath, label):
        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                img = Image.open(filepath)
            elif ext in VIDEO_EXTENSIONS:
                # Suppress OpenCV error messages
                cv2.setLogLevel(0)
                
                cap = cv2.VideoCapture(filepath)
                if not cap.isOpened():
                    raise Exception("Could not open video file")
                
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames <= 0:
                    cap.release()
                    raise Exception("Video has no frames")
                
                # Try to get the first frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    raise Exception("Could not read first video frame")
                
                # Convert frame to PIL Image for solid color checking
                first_frame_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                
                # Check if the first frame is mostly solid color
                is_solid = self.is_solid_color_image(first_frame_img)
                
                if is_solid and total_frames > 1:
                    # Try multiple positions to find a better frame
                    frame_positions = [
                        total_frames // 4,      # 25% into video
                        total_frames // 2,      # 50% into video  
                        total_frames * 3 // 4,  # 75% into video
                    ]
                    
                    best_frame = first_frame_img
                    
                    for pos in frame_positions:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                        ret, frame = cap.read()
                        if ret:
                            candidate_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                            # Use the first frame that's not solid color
                            if not self.is_solid_color_image(candidate_img):
                                best_frame = candidate_img
                                break
                    
                    img = best_frame
                else:
                    # First frame is fine, use it
                    img = first_frame_img
                
                cap.release()
            
            img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, lambda: label.config(image=photo, width=0, height=0))
            label.image = photo 
        except Exception as e:
            # For debugging, you can uncomment the next line to see errors
            # print(f"Thumbnail error for {os.path.basename(filepath)}: {e}")
            self.root.after(0, lambda: label.config(text="Error", bg="red"))

    def select_all_duplicates(self):
        # This function no longer reloads thumbnails. It only sets checkbox states.
        self.set_all_checkboxes(0)
        self.root.after(100, self._select_duplicates_worker)

    def _select_duplicates_worker(self):
        for group in self.duplicate_groups.values():
            for path in group[1:]:
                if path in self.checkbox_vars:
                    self.checkbox_vars[path].set(True)

    def set_all_checkboxes(self, value):
        # Only duplicates have checkboxes, originals are excluded from checkbox_vars
        for var in self.checkbox_vars.values():
            var.set(value)

    def start_deletion(self):
        self.files_to_delete = [path for path, var in self.checkbox_vars.items() if var.get()]
        if not self.files_to_delete:
            messagebox.showwarning("No Selection", "No files selected for deletion.")
            return
        
        if messagebox.askyesno("Confirm Deletion", f"Permanently delete {len(self.files_to_delete)} selected files?"):
            self.show_screen("deleting")
            threading.Thread(target=self.delete_thread, daemon=True).start()

    # --- Screen 4: Deleting ---
    def create_deleting_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Step 4: Deleting Files...", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        # Overall progress section
        overall_label_frame = ttk.Frame(frame)
        overall_label_frame.pack(pady=5)
        ttk.Label(overall_label_frame, text="Overall Progress", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        self.delete_overall_percentage = ttk.Label(overall_label_frame, text="0%")
        self.delete_overall_percentage.pack(side=tk.RIGHT)
        
        self.delete_overall_progress_bar = ttk.Progressbar(frame, mode='determinate', length=600)
        self.delete_overall_progress_bar.pack(pady=(5, 15))
        
        self.delete_status_label = ttk.Label(frame, text="Preparing to delete...")
        self.delete_status_label.pack(pady=5)
        return frame

    def delete_thread(self):
        all_files = [p for group in self.duplicate_groups.values() for p in group]
        self.kept_files = [p for p in all_files if p not in self.files_to_delete]

        total = len(self.files_to_delete)
        self.delete_overall_progress_bar['maximum'] = 100
        
        for i, path in enumerate(self.files_to_delete):
            overall_percentage = (i / total) * 100
            
            # Show file starting to be deleted
            self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                          self.update_delete_status(f"Deleting ({n+1}/{total}): {os.path.basename(p)}", op))
            
            try:
                os.remove(path)
                # Show successful deletion
                overall_percentage = ((i + 1) / total) * 100
                self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                              self.update_delete_status(f"Deleted ({n+1}/{total}): {os.path.basename(p)}", op))
            except OSError:
                # Show failed deletion (still counts as complete)
                overall_percentage = ((i + 1) / total) * 100
                self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                              self.update_delete_status(f"Failed to delete ({n+1}/{total}): {os.path.basename(p)}", op))
                          
        self.root.after(0, self.on_delete_complete)

    def update_delete_status(self, text, overall_percentage):
        self.delete_status_label.config(text=text)
        self.delete_overall_progress_bar['value'] = overall_percentage
        self.delete_overall_percentage.config(text=f"{overall_percentage:.1f}%")

    def on_delete_complete(self):
        self.build_final_report_grid()
        self.show_screen("final_report")

    # --- Screen 5: Final Report ---
    def _create_preview_pane(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="Preview (no audio)")
        # Set smaller constraints to prevent overlap with duplicates area
        preview_frame.configure(width=255)  # Further reduced width to avoid overlap
        preview_frame.pack_propagate(False)  # Maintain size constraints

        preview_canvas = tk.Canvas(preview_frame, bg="black", width=255, height=200,)
        preview_canvas.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        # Video controls
        vid_controls = ttk.Frame(preview_frame)
        vid_play_btn = ttk.Button(vid_controls, text="▶", command=self.toggle_play_pause)
        vid_time_label = ttk.Label(vid_controls, text="00:00 / 00:00")
        vid_seek_bar = ttk.Scale(vid_controls, from_=0, to=1000, orient=tk.HORIZONTAL, command=self.seek_video)
        vid_play_btn.pack(side=tk.LEFT, padx=5)
        vid_time_label.pack(side=tk.RIGHT, padx=5)
        vid_seek_bar.pack(side=tk.LEFT, expand=True, fill='x')
        
        # GIF controls
        gif_controls = ttk.Frame(preview_frame)
        gif_play_btn = ttk.Button(gif_controls, text="❚❚ Pause", command=self.toggle_play_pause)
        gif_play_btn.pack()

        return {
            "frame": preview_frame,
            "canvas": preview_canvas,
            "video_controls": vid_controls,
            "gif_controls": gif_controls,
            "play": vid_play_btn,
            "seek": vid_seek_bar,
            "time_label": vid_time_label,
            "gif_play": gif_play_btn
        }

    def create_final_report_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Deletion Complete: Kept Items", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        # Use Frame with grid layout for fixed sections (non-resizable)
        main_content_frame = ttk.Frame(frame)
        main_content_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
          # Configure grid layout with fixed proportions
        main_content_frame.grid_columnconfigure(0, weight=2)  # 2/3 for kept items
        main_content_frame.grid_columnconfigure(1, weight=1)  # 1/3 for preview
        main_content_frame.grid_rowconfigure(0, weight=1)
        
        # Left section for kept items grid
        grid_container = ttk.Frame(main_content_frame)
        grid_container.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        # Right section for preview - fixed width
        self.final_report_preview_pane = self._create_preview_pane(main_content_frame)
        self.final_report_preview_pane['frame'].grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        self.final_canvas = tk.Canvas(grid_container, bg=self.bg_colour, highlightthickness=0)
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.final_canvas.yview)
        self.final_grid_frame = ttk.Frame(self.final_canvas)
        self.final_canvas.create_window((0, 0), window=self.final_grid_frame, anchor="nw")
        self.final_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.final_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.final_grid_frame.bind("<Configure>", lambda e: self.final_canvas.configure(scrollregion=self.final_canvas.bbox("all")))
        
        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=20, padx=20)
        ttk.Button(footer, text="Done ✔", style="Accent.TButton", command=self.close_app).pack(side=tk.RIGHT)
        
        return frame

    def build_final_report_grid(self):
        self.thumbnail_widgets = {} 
        for widget in self.final_grid_frame.winfo_children():
            widget.destroy()
        
        container_width = self.final_grid_frame.winfo_width()
        if container_width <= 1: container_width = 800
        max_cols = max(1, container_width // (THUMBNAIL_SIZE[0] + 20))
        
        for i, filepath in enumerate(self.kept_files):
            row, col = divmod(i, max_cols)
            item_frame = ttk.Frame(self.final_grid_frame, padding=5)
            item_frame.grid(row=row, column=col, padx=5, pady=5)
            thumb_label = tk.Label(item_frame, bg='gray', relief='raised', width=THUMBNAIL_SIZE[0], height=THUMBNAIL_SIZE[1])
            thumb_label.pack(pady=5)
            thumb_label.bind("<Button-1>", lambda e, p=filepath: self.on_thumbnail_click(p))
            self.thumbnail_widgets[filepath] = thumb_label # Store reference
            ttk.Label(item_frame, text=os.path.basename(filepath), wraplength=THUMBNAIL_SIZE[0]).pack()
            threading.Thread(target=self.load_thumbnail, args=(filepath, thumb_label), daemon=True).start()

    def close_app(self):
        """Close the application"""
        if self.active_media_player:
            self.active_media_player.stop()
        self.root.quit()
        self.root.destroy()

    def reset_app(self):
        self.scan_directories.clear()
        self.folder_listbox.delete(0, tk.END)
        self.list_frame.pack_forget()
        self._update_folder_buttons()
        self.show_screen("folder_selection")

    # --- Media Player Controls ---
    def toggle_play_pause(self):
        if self.active_media_player: self.active_media_player.toggle_play_pause()
    def seek_video(self, value):
        if isinstance(self.active_media_player, VideoPlayerCV): self.active_media_player.seek(float(value))
            
    # --- UI Helpers ---
    def show_transient_message(self, text):
        self.results_status_label.config(text=text)

    def hide_transient_message(self):
        self.results_status_label.config(text=" ")

    def get_file_creation_time(self, filepath):
        """Get file creation time, fallback to modification time if creation time is not available"""
        try:
            # On Windows, st_ctime is creation time; on Unix, it's last metadata change time
            # st_mtime is modification time on all platforms
            stat = os.stat(filepath)
            if os.name == 'nt':  # Windows
                return stat.st_ctime
            else:  # Unix-like systems
                # Use the earlier of creation time (if available) or modification time
                return min(getattr(stat, 'st_birthtime', stat.st_mtime), stat.st_mtime)
        except (OSError, AttributeError):
            # If we can't get the creation time, return a default value (current time)
            # This ensures the sorting still works even if there are file access issues
            return time.time()


# --- Media Player Classes ---
class GifPlayer:
    def __init__(self, filepath, canvas, play_button):
        self.filepath = filepath
        self.canvas = canvas
        self.play_button = play_button
        self.is_playing = False
        self.is_stopped = False
        self.photo_img = None
        self.thread = None
        
        try:
            self.image = Image.open(filepath)
            self.frames = []
            for frame in ImageSequence.Iterator(self.image):
                duration = frame.info.get('duration', 100) / 1000.0
                resized_frame = frame.copy()
                # Get canvas dimensions for responsive sizing
                canvas.update_idletasks()
                canvas_width = canvas.winfo_width()
                canvas_height = canvas.winfo_height()
                
                # Use canvas dimensions if available, otherwise fallback to PREVIEW_SIZE
                if canvas_width > 1 and canvas_height > 1:
                    max_size = (canvas_width - 20, canvas_height - 20)
                else:
                    max_size = PREVIEW_SIZE
                    
                resized_frame.thumbnail(max_size, Image.LANCZOS)
                self.frames.append((ImageTk.PhotoImage(resized_frame), duration))
            self.frame_index = 0
            self.show_frame()
        except Exception:
            self.frames = []

    def show_frame(self):
        if not self.frames: return
        photo = self.frames[self.frame_index][0]
        self.canvas.delete("all")
        self.canvas.create_image(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, anchor='center', image=photo)
        
    def play_loop(self):
        while not self.is_stopped:
            if self.is_playing and self.frames:
                self.frame_index = (self.frame_index + 1) % len(self.frames)
                photo, delay = self.frames[self.frame_index]
                self.canvas.after(0, self.show_frame)
                time.sleep(delay)
            else:
                time.sleep(0.1)

    def toggle_play_pause(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_button.config(text="❚❚ Pause")
            if not self.thread or not self.thread.is_alive():
                self.is_stopped = False
                self.thread = threading.Thread(target=self.play_loop, daemon=True)
                self.thread.start()
        else:
            self.play_button.config(text="▶ Play")

    def stop(self):
        self.is_stopped = True

class VideoPlayerCV:
    def __init__(self, filepath, widgets):
        self.filepath = filepath
        self.canvas = widgets['canvas']
        self.seek_bar = widgets['seek']
        self.play_button = widgets['play']
        self.time_label = widgets['time_label']
        
        self.cap = cv2.VideoCapture(filepath)
        self.lock = threading.Lock()
        self.is_playing = False
        self.is_stopped = False
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.frame_count > 0: self.seek_bar.config(to=self.frame_count - 1)
        self.photo_img = None
        self.thread = None
        self.update_first_frame()

    def format_time(self, frame_number):
        if self.fps > 0:
            total_seconds = frame_number / self.fps
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            return f"{minutes:02d}:{seconds:02d}"
        return "00:00"

    def update_first_frame(self):
        with self.lock:
            ret, frame = self.cap.read()
        if ret: self.show_frame(frame)
        with self.lock:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def show_frame(self, frame):
        try:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            # Get canvas dimensions for responsive sizing
            self.canvas.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # Use canvas dimensions if available, otherwise fallback to PREVIEW_SIZE
            if canvas_width > 1 and canvas_height > 1:
                max_size = (canvas_width - 20, canvas_height - 20)
            else:
                max_size = PREVIEW_SIZE
                
            img.thumbnail(max_size, Image.LANCZOS)
            self.photo_img = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, anchor='center', image=self.photo_img)
        except Exception: pass

    def play_loop(self):
        delay = 1.0 / self.fps if self.fps > 0 else 0.04
        while not self.is_stopped:
            if self.is_playing:
                with self.lock:
                    if not self.ensure_capture_open(): break
                    ret, frame = self.cap.read()
                if not ret:
                    self.stop()
                    break
                self.canvas.after(0, self.show_frame, frame)
                time.sleep(delay)
            else:
                time.sleep(0.1)

    def update_loop(self):
        if self.is_stopped: return
        current_frame = 0  # Initialize with default value
        with self.lock:
            if self.ensure_capture_open():
                current_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        
        self.seek_bar.set(current_frame)
        total_time_str = self.format_time(self.frame_count)
        current_time_str = self.format_time(current_frame)
        self.time_label.config(text=f"{current_time_str} / {total_time_str}")
        
        if self.is_playing:
            self.canvas.after(500, self.update_loop)

    def toggle_play_pause(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            # Ensure capture is open before starting playback
            with self.lock:
                if not self.ensure_capture_open():
                    self.is_playing = False
                    return
            self.play_button.config(text="❚❚")
            if not self.thread or not self.thread.is_alive():
                self.is_stopped = False
                self.thread = threading.Thread(target=self.play_loop, daemon=True)
                self.thread.start()
                self.update_loop()
        else:
            self.play_button.config(text="▶")

    def seek(self, frame_num_str):
        with self.lock:
            if not self.ensure_capture_open(): return
            frame_num = int(float(frame_num_str))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            if not self.is_playing:
                ret, frame = self.cap.read()
                if ret: self.canvas.after(0, self.show_frame, frame)
    def stop(self):
        self.is_stopped = True
        self.is_playing = False
        if hasattr(self, 'play_button'): self.play_button.config(text="▶")
        with self.lock:
            if self.cap.isOpened(): self.cap.release()

    def ensure_capture_open(self):
        """Ensure video capture is open, reopen if necessary"""
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.filepath)
            if not self.cap.isOpened():
                return False
        return True
