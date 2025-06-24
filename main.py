import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue

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
PREVIEW_PANE_WIDTH = 450  # Base minimum width

# --- Core Hashing Functions ---
def get_image_hash(filepath, hash_size=8):
    """
    Generate a perceptual hash for an image.
    Crucially, this function differentiates between animated and static images
    by prepending a prefix to the hash.
    """
    try:
        with Image.open(filepath) as img:
            # Check if the image is animated by checking the number of frames.
            # The 'n_frames' attribute is the most reliable way.
            is_animated = getattr(img, 'n_frames', 1) > 1
            
            # Calculate the standard average hash from the first frame.
            core_hash = imagehash.average_hash(img.convert('RGB'), hash_size=hash_size)

            # Return a hash prefixed to distinguish animated from static images.
            # This ensures they are never in the same duplicate group.
            if is_animated:
                return f"anim_{core_hash}"
            else:
                return f"static_{core_hash}"
    except Exception: 
        return None

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
            with VideoFileClip(filepath) as video_clip:
                if video_clip.audio is None:
                    result_queue.put(("success", "no_audio", None))  # No issue for missing audio
                    return
                
                # Get basic audio properties
                try:
                    duration = video_clip.audio.duration
                except Exception:
                    duration = 0
                
                try:
                    fps = video_clip.audio.fps if hasattr(video_clip.audio, 'fps') else 44100
                except Exception:
                    fps = 44100
                    
                try:
                    nchannels = video_clip.audio.nchannels if hasattr(video_clip.audio, 'nchannels') else 2
                except Exception:
                    nchannels = 2
                
                # Create a simple hash based on duration and basic properties
                audio_signature = f"{int(duration)}_{int(fps)}_{nchannels}"
                
                # Convert to a numeric hash for consistency
                hash_value = hash(audio_signature) % (10**8)
                result_queue.put(("success", str(hash_value), None))
                
        except Exception as e:
            result_queue.put(("error", str(e), f"MoviePy error: {type(e).__name__}"))
    
    try:
        # Create a queue for thread communication
        result_queue = queue.Queue()
        
        # Start the video loading in a separate thread
        thread = threading.Thread(target=load_video_clip, args=(filepath, result_queue), daemon=True)
        thread.start()
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            # Thread is still running, we'll abandon it and use fallback
            # Try alternative approach using OpenCV for basic file info
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
                    return str(fallback_hash), "Audio error"
                else:
                    return "opencv_error", "Audio error - OpenCV error"
            except Exception:
                return "fallback_error", "Audio error - fallback error"
        else:
            # Thread completed, get the result
            try:
                status, result, issue = result_queue.get_nowait()
                if status == "success":
                    return result, issue
                else:
                    # Fall back to OpenCV approach
                    try:
                        cap = cv2.VideoCapture(filepath)
                        if cap.isOpened():
                            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            duration = frame_count / fps if fps > 0 else 0
                            cap.release()
                            
                            fallback_signature = f"fallback_{int(duration)}_{int(fps)}_unknown"
                            fallback_hash = hash(fallback_signature) % (10**8)
                            return str(fallback_hash), f"Audio processing failed - used video metadata fallback ({issue})"
                        else:
                            return "opencv_error", "Audio error - OpenCV error"
                    except Exception:
                        return "fallback_error", "Audio error - fallback error"
            except queue.Empty:
                return "thread_error", "Audio processing failed - no result available"
            
    except Exception as e:
        return "audio_error", f"Audio processing error: {type(e).__name__}"

# --- UI Helper Functions ---
def truncate_filename_with_ext(filename, max_len=20):
    """Truncates a filename but always keeps the extension visible."""
    if len(filename) <= max_len:
        return filename
    
    name, ext = os.path.splitext(filename)

    # If the extension is too long, we can't do much.
    # Fallback to simple truncation from the end.
    if len(ext) >= max_len - 3:
        return filename[:max_len-3] + "..."

    # The length available for the name part
    name_len = max_len - len(ext) - 3
    
    # Ensure name_len is not negative
    if name_len < 0:
        return "..." + ext[-max_len+3:]

    return name[:name_len] + "..." + ext

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
        self.frames_to_compare = 10
        self.audio_processing_issues = {}
        self.files_selected_for_deletion = set() # Persistent selection state

        # --- Virtualized Scrolling State ---
        self.group_keys = []
        self.group_layout_info = []
        self.active_group_widgets = {}
        self.kept_files_layout_info = []
        self.active_kept_file_widgets = {}
        self.thumbnail_widgets = {}

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
            self.root.minsize(800, 600)
            self.root.resizable(True, True)
        elif screen_name in ["scanning", "deleting"]:
            self.root.geometry("500x220")
            self.root.minsize(500, 220)
            self.root.resizable(True, True)
        elif screen_name == "folder_selection":
            self.root.geometry("500x320")
            self.root.minsize(450, 320)
            self.root.resizable(True, True)
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
        
        settings_frame = ttk.LabelFrame(frame, text="Video Comparison Settings")
        settings_frame.pack(pady=20, padx=20, fill='x')
        
        frames_label_frame = ttk.Frame(settings_frame)
        frames_label_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(frames_label_frame, text="Frames to compare per video:", font=("Helvetica", 10)).pack(side=tk.LEFT)
        self.frames_value_label = ttk.Label(frames_label_frame, text=f"{self.frames_to_compare}", font=("Helvetica", 10, "bold"))
        self.frames_value_label.pack(side=tk.RIGHT)
        
        self.frames_slider = ttk.Scale(settings_frame, from_=3, to=50, orient=tk.HORIZONTAL, 
                                       command=self.on_frames_slider_change, length=300)
        self.frames_slider.set(self.frames_to_compare)
        self.frames_slider.pack(padx=10, pady=(0, 10))
        
        help_text = ttk.Label(settings_frame, 
                               text="More frames = more accurate detection but slower processing\n"
                                    "Fewer frames = faster processing but may miss some duplicates",
                               font=("Helvetica", 9), foreground="gray")
        help_text.pack(padx=10, pady=(0, 10))
        
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
        self._resize_folder_selection_window()
        self._update_folder_buttons()

    def _resize_folder_selection_window(self):
        self.root.update_idletasks()
        base_height = 320
        if len(self.scan_directories) > 0:
            list_height = len(self.scan_directories) * 20 + 60
            total_height = base_height + list_height
        else:
            total_height = base_height
        min_height = 320
        max_height = 500
        final_height = max(min_height, min(max_height, total_height))
        width = 500
        self.root.geometry(f"{width}x{final_height}")

    def _update_folder_buttons(self):
        if self.scan_directories:
            self.remove_folder_btn.pack(side=tk.LEFT, padx=10)
            self.start_scan_btn.pack(side=tk.LEFT, padx=20)
            self.remove_folder_btn.config(state=tk.NORMAL)
            self.start_scan_btn.config(state=tk.NORMAL)
        else:
            self.remove_folder_btn.pack_forget()
            self.start_scan_btn.pack_forget()

    def on_frames_slider_change(self, value):
        self.frames_to_compare = int(float(value))
        self.frames_value_label.config(text=f"{self.frames_to_compare}")

    def start_scan(self):
        if not self.scan_directories:
            messagebox.showwarning("No Folders", "Please add at least one folder to scan.")
            return

        # Reset selections from any previous scan
        self.files_selected_for_deletion.clear()
        self.checkbox_vars.clear()

        self.show_screen("scanning")
        threading.Thread(target=self.scan_thread, daemon=True).start()

    # --- Screen 2: Scanning ---
    def create_scanning_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Step 2: Scanning...", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        overall_label_frame = ttk.Frame(frame)
        overall_label_frame.pack(pady=5)
        ttk.Label(overall_label_frame, text="Overall Progress", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        self.scan_overall_percentage = ttk.Label(overall_label_frame, text="0%")
        self.scan_overall_percentage.pack(side=tk.RIGHT)
        
        self.scan_overall_progress_bar = ttk.Progressbar(frame, mode='determinate', length=400)
        self.scan_overall_progress_bar.pack(pady=(5, 15))
        
        self.scan_status_label = ttk.Label(frame, text="Gathering files...", wraplength=450, justify='center')
        self.scan_status_label.pack(pady=10)
        
        self.scan_audio_issues_label = ttk.Label(frame, text="", foreground="red", font=("Helvetica", 9))
        self.scan_audio_issues_label.pack(pady=5)
        
        return frame

    def scan_thread(self):
        self.duplicate_groups.clear()
        self.audio_processing_issues.clear()
        filepaths = [os.path.join(r, f) for d in self.scan_directories for r, _, fs in os.walk(d) for f in fs]
        total = len(filepaths)
        
        self.scan_overall_progress_bar['maximum'] = 100
        hashes = {}
        for i, path in enumerate(filepaths):
            overall_progress = (i / total) * 75
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
            
            overall_progress = ((i + 1) / total) * 75
            self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                self.update_scan_status(f"Completed visuals ({n+1}/{total}): {os.path.basename(p)}", op))
        
        visual_duplicate_groups = {k: v for k, v in hashes.items() if len(v) > 1}
        final_duplicate_groups = {}
        group_counter = 0
        total_video_files = sum(len(paths) for paths in visual_duplicate_groups.values() 
                                if any(os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS for p in paths))
        processed_video_files = 0
        
        for visual_hash, paths in visual_duplicate_groups.items():
            is_video_group = any(os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS for p in paths)

            if is_video_group:
                audio_groups = {}
                for i, path in enumerate(paths):
                    overall_progress = 75 + (processed_video_files / max(1, total_video_files)) * 25
                    self.root.after(0, lambda p=path, n=i, op=overall_progress: 
                        self.update_scan_status(f"Processing audio for group {group_counter+1} ({n+1}/{len(paths)}): {os.path.basename(p)}", op))
                    
                    audio_h, audio_issue = get_audio_hash(path)
                    if audio_issue:
                        self.audio_processing_issues[path] = audio_issue
                        issue_count = len(self.audio_processing_issues)
                        self.root.after(0, self.update_audio_issues_counter, issue_count)

                    if audio_h not in audio_groups:
                        audio_groups[audio_h] = []
                    audio_groups[audio_h].append(path)
                    
                    processed_video_files += 1

                for audio_hash, audio_paths in audio_groups.items():
                    if len(audio_paths) > 1:
                        final_group_key = f"{visual_hash}_{audio_hash}"
                        final_duplicate_groups[final_group_key] = audio_paths
            else:
                final_duplicate_groups[visual_hash] = paths
            group_counter += 1
            
        self.duplicate_groups = final_duplicate_groups
        for key in self.duplicate_groups:
            self.duplicate_groups[key].sort(key=lambda path: self.get_file_creation_time(path))

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
            
        self.prepare_virtualized_results()
        self.update_results_summary()
        self.show_screen("results")

    def update_results_summary(self):
        if self.audio_processing_issues:
            issue_count = len(self.audio_processing_issues)
            summary_text = f"Found {len(self.duplicate_groups)} duplicate groups.\nNote: {issue_count} file(s) had audio processing issues (marked with ⚠️)"
        else:
            summary_text = f"Found {len(self.duplicate_groups)} duplicate groups."
        
        if hasattr(self, 'results_status_label'):
            self.results_status_label.config(text=summary_text)

    # --- Screen 3: Results (VIRTUALIZED) ---
    def create_results_screen(self):
        frame = ttk.Frame(self.root)
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(header_frame, text="Step 3: Review Duplicates", font=("Helvetica", 16, "bold")).pack(side=tk.LEFT)
        
        main_content_frame = ttk.Frame(frame)
        main_content_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        main_content_frame.grid_columnconfigure(0, weight=1)
        main_content_frame.grid_columnconfigure(1, weight=0, minsize=PREVIEW_PANE_WIDTH)
        main_content_frame.grid_rowconfigure(0, weight=1)
        
        grid_container = ttk.Frame(main_content_frame)
        grid_container.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        self.results_preview_pane = self._create_preview_pane(main_content_frame)
        self.results_preview_pane['frame'].grid(row=0, column=1, sticky='nsew', padx=(5, 0))

        results_header = ttk.Frame(grid_container)
        results_header.pack(fill='x', pady=5, padx=5)
        ttk.Button(results_header, text="Select All Duplicates", command=lambda: self.set_all_checkboxes(True)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(results_header, text="Deselect All", command=lambda: self.set_all_checkboxes(False)).pack(side=tk.LEFT)
        self.results_status_label = ttk.Label(results_header, text=" ", foreground="blue")
        self.results_status_label.pack(side=tk.LEFT, padx=20)
        
        self.canvas_scroll_frame = tk.Canvas(grid_container, bg=self.bg_colour, highlightthickness=0)
        self.results_scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas_scroll_frame.yview)
        
        # This frame acts as a spacer to define the total scrollable height
        self.results_grid_frame = ttk.Frame(self.canvas_scroll_frame)
        self.canvas_scroll_frame.create_window((0, 0), window=self.results_grid_frame, anchor="nw")
        
        # Link scrollbar and canvas, and hook our update function into the scroll command
        self.canvas_scroll_frame.config(yscrollcommand=lambda *args: self.results_scrollbar.set(*args) or self._on_results_scroll())

        self.canvas_scroll_frame.pack(side="left", fill="both", expand=True)
        self.results_scrollbar.pack(side="right", fill="y")
        
        # Re-calculate layout on resize
        self.canvas_scroll_frame.bind("<Configure>", lambda e: self.root.after_idle(self.prepare_virtualized_results, True))
        self.canvas_scroll_frame.bind_all("<MouseWheel>", self._on_mousewheel)

        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=20, padx=20)
        ttk.Button(footer, text="Delete Selected Files 🗑️", style="Accent.TButton", command=self.start_deletion).pack(side=tk.RIGHT)
        
        return frame
        
    def _on_mousewheel(self, event):
        active_canvas = None
        scroll_func = None

        if self.current_screen == self.screens['results']:
            active_canvas = self.canvas_scroll_frame
            scroll_func = self._on_results_scroll
        elif self.current_screen == self.screens['final_report']:
            active_canvas = self.final_canvas
            scroll_func = self._on_final_report_scroll

        if active_canvas:
            active_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            if scroll_func:
                scroll_func()

    def _on_results_scroll(self, *args):
        """Called on any scroll action on the results canvas. Schedules a widget update."""
        self.root.after_idle(self._update_visible_groups)

    def prepare_virtualized_results(self, re_layout=False):
        """Pre-calculates the layout and height of all groups to set up the virtualized view."""
        if not re_layout:
            self.group_keys = list(self.duplicate_groups.keys())
            self.checkbox_vars.clear()

        for widget_id in self.active_group_widgets.values():
            self.canvas_scroll_frame.delete(widget_id)
        self.active_group_widgets.clear()
        
        self.group_layout_info.clear()
        current_y = 0
        
        container_width = self.canvas_scroll_frame.winfo_width()
        if container_width <= 1: container_width = 800
        
        # Fixed height for one row of items inside a group frame
        ITEM_ROW_HEIGHT = (THUMBNAIL_SIZE[1] + 80) + 10 # (Fixed Item Frame Height) + grid pady
        
        # Width of one item including padding
        ITEM_WIDTH = (THUMBNAIL_SIZE[0] + 10) + 10 # (Fixed Item Frame width) + grid padx

        max_cols = max(1, container_width // ITEM_WIDTH)
        
        GROUP_HEADER_HEIGHT = 40 # Estimated height for the LabelFrame border and text
        GROUP_MARGIN = 15 # Consistent margin between groups

        for key in self.group_keys:
            paths = self.duplicate_groups[key]
            num_rows = (len(paths) + max_cols - 1) // max_cols
            group_height = (num_rows * ITEM_ROW_HEIGHT) + GROUP_HEADER_HEIGHT
            
            # The 'y' position is the running total before adding the current group
            self.group_layout_info.append({'y': current_y, 'height': group_height, 'key': key})
            
            # Increment the running total for the *next* group's position
            current_y += group_height + GROUP_MARGIN

        total_height = current_y
        self.results_grid_frame.config(height=total_height, width=1)
        self.canvas_scroll_frame.config(scrollregion=(0, 0, container_width, total_height))
        self._update_visible_groups()

    def _update_visible_groups(self):
        """The core of virtualization: creates/destroys widgets based on scroll position."""
        canvas_height = self.canvas_scroll_frame.winfo_height()
        scroll_region = self.canvas_scroll_frame.cget('scrollregion')
        if not scroll_region: return
        
        try:
            total_height = int(scroll_region.split(' ')[3])
        except (ValueError, IndexError):
            total_height = 0

        if total_height == 0: return

        view_top = self.canvas_scroll_frame.yview()[0] * total_height
        view_bottom = view_top + canvas_height
        
        buffer = canvas_height
        render_top = max(0, view_top - buffer)
        render_bottom = min(total_height, view_bottom + buffer)
        
        visible_keys = {
            info['key'] for info in self.group_layout_info 
            if info['y'] + info['height'] > render_top and info['y'] < render_bottom
        }
        
        rendered_keys = set(self.active_group_widgets.keys())
        to_create = visible_keys - rendered_keys
        to_destroy = rendered_keys - visible_keys

        for key in to_destroy:
            widget_id = self.active_group_widgets.pop(key, None)
            if widget_id:
                try:
                    # Retrieve the widget's path name from the canvas item
                    win_path = self.canvas_scroll_frame.itemcget(widget_id, "-window")
                    # First, remove the item from the canvas
                    self.canvas_scroll_frame.delete(widget_id)
                    if win_path:
                        # Then, destroy the actual widget
                        self.canvas_scroll_frame.nametowidget(win_path).destroy()
                except tk.TclError:
                    # This can happen if the widget is already gone, which is fine.
                    pass

            for path in self.duplicate_groups.get(key, [])[1:]:
                 self.checkbox_vars.pop(path, None)
            for path in self.duplicate_groups.get(key, []):
                 self.thumbnail_widgets.pop(path, None)

        for key in to_create:
            info = next((i for i in self.group_layout_info if i['key'] == key), None)
            if info:
                group_widget = self._create_group_widget(key)
                widget_id = self.canvas_scroll_frame.create_window(0, info['y'], window=group_widget, anchor="nw")
                self.active_group_widgets[key] = widget_id

    def _create_group_widget(self, key):
        """Creates the widget for a single duplicate group with a fixed, predictable layout."""
        paths = self.duplicate_groups[key]
        group_index = self.group_keys.index(key)
        
        group_frame = ttk.LabelFrame(self.canvas_scroll_frame, text=f"Group {group_index + 1} ({len(paths)} items)")

        container_width = self.canvas_scroll_frame.winfo_width()
        if container_width <= 1: container_width = 800

        ITEM_WIDTH = (THUMBNAIL_SIZE[0] + 10) + 10
        max_cols = max(1, container_width // ITEM_WIDTH)

        for j, filepath in enumerate(paths):
            row, col = divmod(j, max_cols)
            
            # This frame has a fixed size to ensure consistent row heights
            item_frame = ttk.Frame(group_frame, padding=5)
            item_frame.config(width=THUMBNAIL_SIZE[0] + 10, height=THUMBNAIL_SIZE[1] + 80)
            item_frame.pack_propagate(False) # Prevent children from changing the frame's size
            item_frame.grid(row=row, column=col, padx=5, pady=5, sticky='n')
            
            is_original = (j == 0)
            
            if is_original:
                tk.Label(item_frame, text="Original", fg='black', font=('Arial', 9)).pack(pady=2)
            else:
                # The checkbox state is now determined by our persistent set
                is_selected = filepath in self.files_selected_for_deletion
                var = tk.BooleanVar(value=is_selected)
                # The command updates the persistent set when the checkbox is toggled
                cb = ttk.Checkbutton(item_frame, variable=var, 
                                     command=lambda p=filepath, v=var: self.on_checkbox_toggle(p, v))
                cb.pack()
                self.checkbox_vars[filepath] = var
            
            thumb_label = tk.Label(item_frame, bg='gray', relief='raised', width=THUMBNAIL_SIZE[0], height=THUMBNAIL_SIZE[1])
            thumb_label.pack(pady=5)
            thumb_label.bind("<Button-1>", lambda e, p=filepath: self.on_thumbnail_click(p))
            self.thumbnail_widgets[filepath] = thumb_label

            # Truncate long filenames, keeping the extension visible
            filename = truncate_filename_with_ext(os.path.basename(filepath))
            filename_label = ttk.Label(item_frame, text=filename, anchor="center")
            filename_label.pack(fill='x', expand=True, pady=2)
            
            if filepath in self.audio_processing_issues:
                issue_text = self.audio_processing_issues[filepath]
                # Truncate issue text as well
                if len(issue_text) > 20: issue_text = issue_text[:17] + "..."
                issue_label = tk.Label(item_frame, text=f"⚠️ {issue_text}", fg='orange', font=('Arial', 8))
                issue_label.pack(pady=(0, 2))
            
            threading.Thread(target=self.load_thumbnail, args=(filepath, thumb_label), daemon=True).start()
        
        return group_frame

    def on_checkbox_toggle(self, filepath, var):
        """Callback to update the selection set when a checkbox is clicked."""
        if var.get():
            self.files_selected_for_deletion.add(filepath)
        else:
            self.files_selected_for_deletion.discard(filepath)

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
            self.active_media_player.toggle_play_pause()
        elif ext in VIDEO_EXTENSIONS:
            preview_widgets['video_controls'].pack(fill='x', pady=5)
            preview_widgets['seek'].set(0)
            self.active_media_player = VideoPlayerCV(filepath, preview_widgets)
            self.active_media_player.toggle_play_pause()
        elif ext in IMAGE_EXTENSIONS:
            self.display_image_preview(filepath, preview_widgets['canvas'])

    def display_image_preview(self, filepath, canvas):
        try:
            img = Image.open(filepath)
            canvas.update_idletasks()
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            max_size = (canvas_width - 20, canvas_height - 20) if canvas_width > 1 and canvas_height > 1 else PREVIEW_SIZE
            
            img.thumbnail(max_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            canvas.delete("all")
            canvas.create_image(canvas.winfo_width()/2, canvas.winfo_height()/2, anchor='center', image=photo)
            canvas.image = photo
        except Exception:
            canvas.delete("all")
            canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2, text="Preview not available", fill="red")

    def is_solid_color_image(self, img, threshold=0.85):
        try:
            img_array = np.array(img)
            height, width = img_array.shape[:2]
            total_pixels = height * width
            
            if len(img_array.shape) == 2:
                unique_values, counts = np.unique(img_array, return_counts=True)
            elif img_array.shape[-1] >= 3:
                gray = np.dot(img_array[...,:3], [0.2989, 0.5870, 0.1140])
                unique_values, counts = np.unique(gray.astype(np.uint8), return_counts=True)
            else:
                unique_values, counts = np.unique(img_array, return_counts=True)
                
            max_count = np.max(counts)
            dominant_ratio = max_count / total_pixels
            
            if len(unique_values) > 0:
                most_common_value = unique_values[np.argmax(counts)]
                if most_common_value <= 30:
                    return dominant_ratio > 0.75
            
            return dominant_ratio > threshold
        except Exception:
            return False

    def load_thumbnail(self, filepath, label):
        try:
            # Check if the widget still exists before processing
            if not label.winfo_exists():
                return
                
            ext = os.path.splitext(filepath)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                img = Image.open(filepath)
            elif ext in VIDEO_EXTENSIONS:
                cv2.setLogLevel(0)
                cap = cv2.VideoCapture(filepath)
                if not cap.isOpened(): raise Exception("Could not open video file")
                
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames <= 0:
                    cap.release()
                    raise Exception("Video has no frames")
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    raise Exception("Could not read first video frame")
                
                first_frame_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                
                if self.is_solid_color_image(first_frame_img) and total_frames > 1:
                    frame_positions = [total_frames // 4, total_frames // 2, total_frames * 3 // 4]
                    best_frame = first_frame_img
                    for pos in frame_positions:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                        ret, frame = cap.read()
                        if ret:
                            candidate_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                            if not self.is_solid_color_image(candidate_img):
                                best_frame = candidate_img
                                break
                    img = best_frame
                else:
                    img = first_frame_img
                
                cap.release()
            
            img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            # Check widget existence again before updating UI from thread
            if label.winfo_exists():
                self.root.after(0, lambda: label.config(image=photo, width=0, height=0))
                label.image = photo 
        except Exception:
            if label.winfo_exists():
                self.root.after(0, lambda: label.config(text="Error", bg="red"))

    def set_all_checkboxes(self, select_all):
        """Updates the master selection set and all visible checkboxes."""
        if select_all:
            all_duplicates = {
                path
                for group in self.duplicate_groups.values()
                for path in group[1:]  # only duplicates, not originals
            }
            self.files_selected_for_deletion.update(all_duplicates)
        else:
            self.files_selected_for_deletion.clear()

        # Update the currently visible checkboxes to reflect the change
        for path, var in self.checkbox_vars.items():
            var.set(path in self.files_selected_for_deletion)

    def start_deletion(self):
        """Starts the deletion process using the persistent selection set."""
        # The set is now the single source of truth.
        self.files_to_delete = list(self.files_selected_for_deletion)
        
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
        
        overall_label_frame = ttk.Frame(frame)
        overall_label_frame.pack(pady=5)
        ttk.Label(overall_label_frame, text="Overall Progress", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        self.delete_overall_percentage = ttk.Label(overall_label_frame, text="0%")
        self.delete_overall_percentage.pack(side=tk.RIGHT)
        
        self.delete_overall_progress_bar = ttk.Progressbar(frame, mode='determinate', length=400)
        self.delete_overall_progress_bar.pack(pady=(5, 15))
        
        self.delete_status_label = ttk.Label(frame, text="Preparing to delete...")
        self.delete_status_label.pack(pady=5)
        return frame

    def delete_thread(self):
        all_files = [p for group in self.duplicate_groups.values() for p in group]
        self.kept_files = [p for p in all_files if p not in self.files_to_delete]
        self.kept_files.sort(key=lambda path: self.get_file_creation_time(path))


        total = len(self.files_to_delete)
        self.delete_overall_progress_bar['maximum'] = 100
        
        for i, path in enumerate(self.files_to_delete):
            overall_percentage = (i / max(1, total)) * 100
            
            self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                self.update_delete_status(f"Deleting ({n+1}/{total}): {os.path.basename(p)}", op))
            
            try:
                os.remove(path)
                overall_percentage = ((i + 1) / max(1, total)) * 100
                self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                    self.update_delete_status(f"Deleted ({n+1}/{total}): {os.path.basename(p)}", op))
            except OSError:
                overall_percentage = ((i + 1) / max(1, total)) * 100
                self.root.after(0, lambda p=path, n=i, op=overall_percentage: 
                    self.update_delete_status(f"Failed to delete ({n+1}/{total}): {os.path.basename(p)}", op))
                                
        self.root.after(0, self.on_delete_complete)

    def update_delete_status(self, text, overall_percentage):
        self.delete_status_label.config(text=text)
        self.delete_overall_progress_bar['value'] = overall_percentage
        self.delete_overall_percentage.config(text=f"{overall_percentage:.1f}%")

    def on_delete_complete(self):
        self.prepare_virtualized_final_report()
        self.show_screen("final_report")

    # --- Screen 5: Final Report (VIRTUALIZED) ---
    def _create_preview_pane(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="Preview (no audio)")
        preview_frame.configure(width=PREVIEW_PANE_WIDTH)
        preview_frame.pack_propagate(False)

        preview_canvas = tk.Canvas(preview_frame, bg="black", width=PREVIEW_PANE_WIDTH, height=200,)
        preview_canvas.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        vid_controls = ttk.Frame(preview_frame)
        vid_play_btn = ttk.Button(vid_controls, text="▶", command=self.toggle_play_pause)
        vid_time_label = ttk.Label(vid_controls, text="00:00 / 00:00")
        vid_seek_bar = ttk.Scale(vid_controls, from_=0, to=1000, orient=tk.HORIZONTAL, command=self.seek_video)
        vid_play_btn.pack(side=tk.LEFT, padx=5)
        vid_time_label.pack(side=tk.RIGHT, padx=5)
        vid_seek_bar.pack(side=tk.LEFT, expand=True, fill='x')
        
        gif_controls = ttk.Frame(preview_frame)
        gif_play_btn = ttk.Button(gif_controls, text="❚❚ Pause", command=self.toggle_play_pause)
        gif_play_btn.pack()

        return {"frame": preview_frame, "canvas": preview_canvas, "video_controls": vid_controls,
                "gif_controls": gif_controls, "play": vid_play_btn, "seek": vid_seek_bar,
                "time_label": vid_time_label, "gif_play": gif_play_btn}

    def create_final_report_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Deletion Complete: Kept Items", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        main_content_frame = ttk.Frame(frame)
        main_content_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        main_content_frame.grid_columnconfigure(0, weight=1)
        main_content_frame.grid_columnconfigure(1, weight=0, minsize=PREVIEW_PANE_WIDTH)
        main_content_frame.grid_rowconfigure(0, weight=1)
        
        grid_container = ttk.Frame(main_content_frame)
        grid_container.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        self.final_report_preview_pane = self._create_preview_pane(main_content_frame)
        self.final_report_preview_pane['frame'].grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        self.final_canvas = tk.Canvas(grid_container, bg=self.bg_colour, highlightthickness=0)
        self.final_scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.final_canvas.yview)
        self.final_grid_frame = ttk.Frame(self.final_canvas)
        self.final_canvas.create_window((0, 0), window=self.final_grid_frame, anchor="nw")
        
        self.final_canvas.config(yscrollcommand=lambda *args: self.final_scrollbar.set(*args) or self._on_final_report_scroll())

        self.final_canvas.pack(side="left", fill="both", expand=True)
        self.final_scrollbar.pack(side="right", fill="y")
        self.final_canvas.bind("<Configure>", lambda e: self.root.after_idle(self.prepare_virtualized_final_report, True))
        
        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=20, padx=20)
        ttk.Button(footer, text="Done ✔", style="Accent.TButton", command=self.close_app).pack(side=tk.RIGHT)
        
        return frame

    def _on_final_report_scroll(self, *args):
        self.root.after_idle(self._update_visible_kept_files)

    def prepare_virtualized_final_report(self, re_layout=False):
        """Pre-calculates the layout for the final report's virtualized grid view."""
        for widget_id in self.active_kept_file_widgets.values():
            self.final_canvas.delete(widget_id)
        self.active_kept_file_widgets.clear()
        
        self.kept_files_layout_info.clear()
        
        container_width = self.final_canvas.winfo_width()
        if container_width <= 1: container_width = 800
        
        # Calculate sizes based on the fixed-size widgets we will create
        ITEM_WIDTH = (THUMBNAIL_SIZE[0] + 10) + 10  # Frame width + grid padx
        ITEM_HEIGHT = (THUMBNAIL_SIZE[1] + 50) + 10 # Frame height + grid pady
        max_cols = max(1, container_width // ITEM_WIDTH)
        
        # Calculate position for each item
        for i, filepath in enumerate(self.kept_files):
            row = i // max_cols
            col = i % max_cols
            item_x = col * ITEM_WIDTH
            item_y = row * ITEM_HEIGHT
            self.kept_files_layout_info.append({'x': item_x, 'y': item_y, 'path': filepath})
        
        # Calculate total height for the scroll region
        num_rows = (len(self.kept_files) + max_cols - 1) // max_cols
        total_height = num_rows * ITEM_HEIGHT

        self.final_grid_frame.config(height=total_height, width=1)
        self.final_canvas.config(scrollregion=(0, 0, container_width, total_height))
        self._update_visible_kept_files()

    def _update_visible_kept_files(self):
        """Creates/destroys kept file widgets based on scroll position."""
        canvas_height = self.final_canvas.winfo_height()
        scroll_region = self.final_canvas.cget('scrollregion')
        if not scroll_region: return
        
        try:
            total_height = int(scroll_region.split(' ')[3])
        except (ValueError, IndexError):
            total_height = 0
            
        if total_height == 0: return

        view_top = self.final_canvas.yview()[0] * total_height
        view_bottom = view_top + canvas_height
        
        buffer = canvas_height
        render_top = max(0, view_top - buffer)
        render_bottom = min(total_height, view_bottom + buffer)

        ITEM_HEIGHT = (THUMBNAIL_SIZE[1] + 50) + 10
        visible_paths = {
            info['path'] for info in self.kept_files_layout_info 
            if info['y'] + ITEM_HEIGHT > render_top and info['y'] < render_bottom
        }

        rendered_paths = set(self.active_kept_file_widgets.keys())
        to_create = visible_paths - rendered_paths
        to_destroy = rendered_paths - visible_paths

        for path in to_destroy:
            widget_id = self.active_kept_file_widgets.pop(path, None)
            if widget_id:
                try:
                    win_path = self.final_canvas.itemcget(widget_id, "-window")
                    self.final_canvas.delete(widget_id)
                    if win_path:
                        self.final_canvas.nametowidget(win_path).destroy()
                except tk.TclError:
                    pass

            self.thumbnail_widgets.pop(path, None)

        for path in to_create:
            info = next((i for i in self.kept_files_layout_info if i['path'] == path), None)
            if info:
                item_widget = self._create_kept_file_widget(path)
                widget_id = self.final_canvas.create_window(info['x'], info['y'], window=item_widget, anchor="nw")
                self.active_kept_file_widgets[path] = widget_id

    def _create_kept_file_widget(self, filepath):
        """Creates a single item widget for the final report with a fixed size."""
        item_frame = ttk.Frame(self.final_canvas, padding=5)
        item_frame.config(width=THUMBNAIL_SIZE[0] + 10, height=THUMBNAIL_SIZE[1] + 50)
        item_frame.pack_propagate(False) # Enforce the fixed size
        
        thumb_label = tk.Label(item_frame, bg='gray', relief='raised', width=THUMBNAIL_SIZE[0], height=THUMBNAIL_SIZE[1])
        thumb_label.pack(pady=5)
        thumb_label.bind("<Button-1>", lambda e, p=filepath: self.on_thumbnail_click(p))
        self.thumbnail_widgets[filepath] = thumb_label
        
        # Truncate filename to fit, keeping the extension visible
        filename = truncate_filename_with_ext(os.path.basename(filepath))
        ttk.Label(item_frame, text=filename, anchor="center").pack(fill='x', expand=True, pady=2)
        threading.Thread(target=self.load_thumbnail, args=(filepath, thumb_label), daemon=True).start()

        return item_frame
        
    def close_app(self):
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
        
    def get_file_creation_time(self, filepath):
        try:
            stat = os.stat(filepath)
            if os.name == 'nt':
                return stat.st_ctime
            else:
                return min(getattr(stat, 'st_birthtime', stat.st_mtime), stat.st_mtime)
        except (OSError, AttributeError):
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
                canvas.update_idletasks()
                canvas_width = canvas.winfo_width()
                canvas_height = canvas.winfo_height()
                
                max_size = (canvas_width - 20, canvas_height - 20) if canvas_width > 1 and canvas_height > 1 else PREVIEW_SIZE
                
                resized_frame.thumbnail(max_size, Image.LANCZOS)
                self.frames.append((ImageTk.PhotoImage(resized_frame), duration))
            self.frame_index = 0
            self.show_frame()
        except Exception:
            self.frames = []

    def show_frame(self):
        if not self.frames or not self.canvas.winfo_exists(): return
        photo = self.frames[self.frame_index][0]
        self.canvas.delete("all")
        self.canvas.create_image(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, anchor='center', image=photo)
        
    def play_loop(self):
        while not self.is_stopped:
            if self.is_playing and self.frames:
                self.frame_index = (self.frame_index + 1) % len(self.frames)
                photo, delay = self.frames[self.frame_index]
                if self.canvas.winfo_exists():
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
        if not self.canvas.winfo_exists(): return
        try:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            self.canvas.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            max_size = (canvas_width - 20, canvas_height - 20) if canvas_width > 1 and canvas_height > 1 else PREVIEW_SIZE
            
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
                if self.canvas.winfo_exists():
                    self.canvas.after(0, self.show_frame, frame)
                time.sleep(delay)
            else:
                time.sleep(0.1)

    def update_loop(self):
        if self.is_stopped or not self.canvas.winfo_exists(): return
        current_frame = 0
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
        if hasattr(self, 'play_button') and self.play_button.winfo_exists(): self.play_button.config(text="▶")
        with self.lock:
            if self.cap.isOpened(): self.cap.release()

    def ensure_capture_open(self):
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.filepath)
            return self.cap.isOpened()
        return True

# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    
    # Configure a modern theme
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    
    # Custom styling
    style.configure("Accent.TButton", font=("Helvetica", 12, "bold"), foreground="white", background="#0078D7")
    style.map("Accent.TButton",
              background=[('active', '#005a9e')],
              foreground=[('active', 'white')])
    style.configure("TLabelFrame.Label", font=("Helvetica", 11, "bold"))
    
    app = DuplicateFinderWizard(root)
    
    # Handle window close gracefully
    def on_closing():
        app.close_app()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()