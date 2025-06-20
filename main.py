# main_wizard_gui.py
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageSequence
import imagehash
import cv2

# --- Configuration ---
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif', '.ico']
VIDEO_EXTENSIONS = ['.mp4', '.avi', 'mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', '.mpg', '.mpeg', '.mts']
THUMBNAIL_SIZE = (128, 128)
# New preview size to better accommodate widescreen video
PREVIEW_SIZE = (640, 480)
VIDEO_FRAME_SAMPLE_RATE_SECONDS = 5
# Preview pane will be calculated as 1/3 of window width
PREVIEW_PANE_WIDTH = 400  # Base minimum width

# --- Core Hashing Functions ---
def get_image_hash(filepath, hash_size=8):
    try:
        with Image.open(filepath) as img:
            return imagehash.average_hash(img.convert('RGB'), hash_size=hash_size)
    except Exception: return None

def get_video_signature(filepath, hash_size=8):
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened(): return None
        hashes, fps = [], cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps == 0:
            cap.release()
            return None
        interval = int(fps * VIDEO_FRAME_SAMPLE_RATE_SECONDS)
        if interval == 0: interval = 1
        count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            if count % interval == 0:
                try:
                    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    hashes.append(str(imagehash.average_hash(img, hash_size=hash_size)))
                except Exception: pass
            count += 1
        cap.release()
        if not hashes: return None
        hashes.sort()
        return "".join(hashes)
    except Exception: return None

# --- Main Application Class (Wizard Style) ---
class DuplicateFinderWizard:
    def __init__(self, root):
        self.root = root
        self.root.title("Duplicate Media Finder Wizard")

        # --- State ---
        self.current_screen = None
        self.scan_directories = set()
        self.duplicate_groups = {}
        self.kept_files = []
        self.checkbox_vars = {}
        self.active_media_player = None

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
            self.active_media_player = None        # --- Dynamic Window Sizing ---
        if screen_name in ["results", "final_report"]:
            self.root.geometry("1280x720")
            self.root.minsize(800, 600)  # Increased minimum to accommodate both sections properly
            self.root.resizable(True, True)
        elif screen_name in ["scanning", "deleting"]:
            self.root.geometry("700x220")  # Increased size to show full scanning status
            self.root.minsize(700, 220)
            self.root.resizable(False, False)
        elif screen_name == "folder_selection":
            self.root.geometry("500x150")  # Increased height to show header and buttons properly
            self.root.minsize(450, 150)
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
        # Update the UI to ensure proper sizing calculations
        self.root.update_idletasks()
          # Calculate required height based on content
        base_height = 150  # Header + button frame + padding (increased from 120)
        if len(self.scan_directories) > 0:
            # Add height for the list frame (approximately 20px per item + frame padding)
            list_height = len(self.scan_directories) * 20 + 60  # 60 for frame and padding
            total_height = base_height + list_height
        else:
            total_height = base_height
        
        # Set reasonable bounds
        min_height = 150  # Increased minimum height
        max_height = 400  # Don't make it too tall
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

    def start_scan(self):
        if not self.scan_directories:
            messagebox.showwarning("No Folders", "Please add at least one folder to scan.")
            return
        self.show_screen("scanning")
        threading.Thread(target=self.scan_thread, daemon=True).start()    # --- Screen 2: Scanning ---
    def create_scanning_screen(self):
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Step 2: Scanning...", font=("Helvetica", 16, "bold")).pack(pady=30)
        self.scan_progress_bar = ttk.Progressbar(frame, mode='determinate', length=650)
        self.scan_progress_bar.pack(pady=15)
        self.scan_status_label = ttk.Label(frame, text="Gathering files...", wraplength=650, justify='center')
        self.scan_status_label.pack(pady=10)
        return frame

    def scan_thread(self):
        self.duplicate_groups.clear()
        filepaths = [os.path.join(r, f) for d in self.scan_directories for r, _, fs in os.walk(d) for f in fs]
        total = len(filepaths)
        self.scan_progress_bar['maximum'] = total
        hashes = {}
        for i, path in enumerate(filepaths):
            self.root.after(0, lambda p=path, n=i: self.update_scan_status(f"Processing ({n+1}/{total}): {os.path.basename(p)}", n+1))
            ext = os.path.splitext(path)[1].lower()
            h = None
            if ext in IMAGE_EXTENSIONS: h = get_image_hash(path)
            elif ext in VIDEO_EXTENSIONS: h = get_video_signature(path)
            if h:
                if h not in hashes: hashes[h] = []
                hashes[h].append(path)
        
        self.duplicate_groups = {k: v for k, v in hashes.items() if len(v) > 1}
        for key in self.duplicate_groups:
            self.duplicate_groups[key].sort()
        
        self.root.after(0, self.on_scan_complete)

    def update_scan_status(self, text, value):
        self.scan_status_label.config(text=text)
        self.scan_progress_bar['value'] = value

    def on_scan_complete(self):
        if not self.duplicate_groups:
            messagebox.showinfo("Scan Complete", "No duplicate files were found.")
            self.show_screen("folder_selection")
            return
        self.build_results_grid()
        self.show_screen("results")

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
        
        self.canvas_scroll_frame = tk.Canvas(grid_container, bg="#f0f0f0", highlightthickness=0)
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

                ttk.Label(item_frame, text=os.path.basename(filepath), wraplength=THUMBNAIL_SIZE[0]).pack()
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

    def load_thumbnail(self, filepath, label):
        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                img = Image.open(filepath)
            elif ext in VIDEO_EXTENSIONS:
                cap = cv2.VideoCapture(filepath)
                ret, frame = cap.read()
                cap.release()
                if not ret: raise Exception("Could not read video frame")
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            
            img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, lambda: label.config(image=photo, width=0, height=0))
            label.image = photo 
        except Exception:
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
        ttk.Label(frame, text="Step 4: Deleting Files...", font=("Helvetica", 16, "bold")).pack(pady=50)
        self.delete_progress_bar = ttk.Progressbar(frame, mode='determinate', length=600)
        self.delete_progress_bar.pack(pady=10)
        self.delete_status_label = ttk.Label(frame, text="Preparing to delete...")
        self.delete_status_label.pack(pady=5)
        return frame

    def delete_thread(self):
        all_files = [p for group in self.duplicate_groups.values() for p in group]
        self.kept_files = [p for p in all_files if p not in self.files_to_delete]

        total = len(self.files_to_delete)
        self.delete_progress_bar['maximum'] = total
        for i, path in enumerate(self.files_to_delete):
            self.root.after(0, lambda p=path, n=i: self.update_delete_status(f"Deleting ({n+1}/{total}): {os.path.basename(p)}", n+1))
            try:
                os.remove(path)
            except OSError:
                pass 
        self.root.after(0, self.on_delete_complete)

    def update_delete_status(self, text, value):
        self.delete_status_label.config(text=text)
        self.delete_progress_bar['value'] = value

    def on_delete_complete(self):
        self.build_final_report_grid()
        self.show_screen("final_report")

    # --- Screen 5: Final Report ---
    def _create_preview_pane(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="Preview")
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
        main_content_frame.grid_columnconfigure(0, weight=2, minsize=500)  # 2/3 for kept items, min 500px
        main_content_frame.grid_columnconfigure(1, weight=0, minsize=280)  # Fixed width for preview
        main_content_frame.grid_rowconfigure(0, weight=1)
        
        # Left section for kept items grid
        grid_container = ttk.Frame(main_content_frame)
        grid_container.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        # Right section for preview - fixed width
        self.final_report_preview_pane = self._create_preview_pane(main_content_frame)
        self.final_report_preview_pane['frame'].grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        self.final_canvas = tk.Canvas(grid_container, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.final_canvas.yview)
        self.final_grid_frame = ttk.Frame(self.final_canvas)
        self.final_canvas.create_window((0, 0), window=self.final_grid_frame, anchor="nw")
        self.final_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.final_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.final_grid_frame.bind("<Configure>", lambda e: self.final_canvas.configure(scrollregion=self.final_canvas.bbox("all")))
        
        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=20, padx=20)
        ttk.Button(footer, text="Done ✔", style="Accent.TButton", command=self.reset_app).pack(side=tk.RIGHT)
        
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


if __name__ == "__main__":
    root = tk.Tk()
    
    style = ttk.Style(root)
    style.theme_use('clam')
    
    # Configure standard button style for better visibility on hover
    style.configure("TButton", padding=6, relief="flat", background="#f0f0f0")
    style.map("TButton",
        foreground=[('active', 'black'), ('disabled', 'gray')],
        background=[('active', '#e0e0e0')]
    )

    # Configure accent button style
    style.configure("Accent.TButton", foreground="white", background="#0078D7")
    style.map("Accent.TButton",
        background=[('active', '#005a9e')]
    )
    
    app = DuplicateFinderWizard(root)
    root.mainloop()
