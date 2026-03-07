import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import sqlite3
import subprocess
import sys
from datetime import datetime

from database import init_db, get_connection
from logger import start_file_session, end_file_session, remove_file_session
from ml.filename_cluster import run_filename_clustering
from ml.recommendation import get_smart_priority_files

from config import DB_PATH

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='file_organizer.log')

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

try:
    init_db()
except Exception as e:
    logging.error(f"Failed to initialize database: {e}")
    import sys
    sys.exit(1)

# Material Design 3 - Ocean Theme (Dark)
SURFACE = "#0B141A"           # Deep Ocean Background
SURFACE_CONTAINER = "#15202B"  # Tonal Indigo Sidebar/Cards
SURFACE_CONTAINER_HIGH = "#1E2D3D" 
PRIMARY = "#4FD1C5"            # Vibrant Teal accent
ON_PRIMARY = "#003735"
PRIMARY_CONTAINER = "#00504D"
ON_PRIMARY_CONTAINER = "#80F2E7"
SECONDARY_CONTAINER = "#2D3748"
ON_SECONDARY_CONTAINER = "#E2E8F0"
OUTLINE = "#4A5568"
ERROR = "#FF8A80"              # Soft Coral for Delete
TEXT_PRIMARY = "#F7FAFC"
TEXT_SECONDARY = "#A0AEC0"

# Material 3 Typography
TITLE_FONT = ("Segoe UI", 24, "bold")
HEADER_FONT = ("Segoe UI", 16, "bold")
BODY_FONT = ("Segoe UI", 12)
SMALL_FONT = ("Segoe UI", 11)

# Material 3 Shapes
RADIUS_LG = 28  # FABs, Search Bars, Main Containers
RADIUS_MD = 16  # Sidebars, Large Cards
RADIUS_SM = 12  # Buttons, Rows, Input fields

# File type icons
FILE_ICONS = {
    ".pdf": "📄", ".doc": "📝", ".docx": "📝", ".txt": "📃",
    ".xls": "📊", ".xlsx": "📊", ".ppt": "📊", ".pptx": "📊",
    ".jpg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".zip": "📦",
    ".rar": "📦", "default": "📄"
}

def open_path(path):
    """Cross-platform path opening"""
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as e:
        logging.error(f"Failed to open path {path}: {e}")
        raise e

class ModernFileManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("📁 FileSense")
        self.geometry("1200x750")
        self.minsize(1000, 600)

        # State
        self.current_view = "smart"  # smart, clusters, all
        self.selected_file = None
        self.selected_files = set()  # Multi-select support
        self.semantic_searcher = None
        self.needs_cluster_refresh = False
        self.active_context_menu = None

        # Build UI
        self.build_ui()
        
        # Load initial data
        self.load_view("smart")
        
        # Check for Tesseract
        self._check_tesseract()
        
        # Run clustering if needed
        self._ensure_clustering()

    def _check_tesseract(self):
        """Check if Tesseract is available and log status"""
        from text_extractor import is_tesseract_available
        if not is_tesseract_available():
            logging.info("Tesseract OCR not found. Image text extraction is disabled (Standard behavior).")

        # Keyboard shortcuts
        self.bind('<Control-o>', lambda e: self.open_file())
        self.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.bind('<Control-r>', lambda e: self.refresh_clusters())
        self.bind('<Delete>', lambda e: self.delete_selected_files())

        logging.info("Application started")

    def build_ui(self):
        """Build the modern file manager UI"""
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color=SURFACE)
        main_container.pack(fill="both", expand=True)
        
        # Sidebar
        self.build_sidebar(main_container)
        
        # Content area
        content_frame = ctk.CTkFrame(main_container, fg_color=SURFACE)
        content_frame.pack(side="left", fill="both", expand=True)
        
        # Toolbar
        self.build_toolbar(content_frame)
        
        # File list area
        self.build_file_list(content_frame)
        
        # Status bar
        self.build_status_bar(content_frame)

    def build_sidebar(self, parent):
        """Build left sidebar navigation"""
        sidebar = ctk.CTkFrame(parent, fg_color=SURFACE_CONTAINER, width=220, corner_radius=0)
        sidebar.pack(side="left", fill="y", padx=0, pady=0)
        sidebar.pack_propagate(False)
        
        # App title
        title_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(20, 30))
        
        title = ctk.CTkLabel(
            title_frame, 
            text="📁 FileSense", 
            font=TITLE_FONT,
            text_color=TEXT_PRIMARY
        )
        title.pack(anchor="w")
        
        # Navigation buttons
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=10, pady=10)
        
        self.nav_buttons = {}
        
        # Smart Priority
        self.nav_buttons["smart"] = self.create_nav_button(
            nav_frame, "⭐ Smart Priority", "smart"
        )
        
        # Clusters
        self.nav_buttons["clusters"] = self.create_nav_button(
            nav_frame, "📂 Categories", "clusters"
        )
        
        # All Files
        self.nav_buttons["all"] = self.create_nav_button(
            nav_frame, "📋 All Files", "all"
        )
        
        # Divider
        divider = ctk.CTkFrame(sidebar, fg_color=OUTLINE, height=1)
        divider.pack(fill="x", padx=15, pady=20)
        
        # Actions
        actions_label = ctk.CTkLabel(
            sidebar, 
            text="ACTIONS", 
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY
        )
        actions_label.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Add File button
        self.add_btn = ctk.CTkButton(
            sidebar,
            text="➕ Add File",
            command=self.open_file,
            fg_color=PRIMARY,
            text_color=ON_PRIMARY,
            hover_color=ON_PRIMARY_CONTAINER,
            height=40,
            font=BODY_FONT,
            corner_radius=RADIUS_SM
        )
        self.add_btn.pack(fill="x", padx=15, pady=5)
        
        # Refresh Clusters button
        refresh_btn = ctk.CTkButton(
            sidebar,
            text="🔄 Refresh Clusters",
            command=self.refresh_clusters,
            fg_color="transparent",
            border_width=1,
            border_color=OUTLINE,
            hover_color=SURFACE_CONTAINER_HIGH,
            height=40,
            font=BODY_FONT,
            corner_radius=RADIUS_SM
        )
        refresh_btn.pack(fill="x", padx=15, pady=5)

    def create_nav_button(self, parent, text, view_name):
        """Create a navigation button"""
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=lambda: self.switch_view(view_name),
            fg_color="transparent",
            hover_color=SURFACE_CONTAINER_HIGH,
            anchor="w",
            height=40,
            font=BODY_FONT,
            corner_radius=RADIUS_SM
        )
        btn.pack(fill="x", pady=2)
        return btn

    def build_toolbar(self, parent):
        """Build top toolbar"""
        toolbar = ctk.CTkFrame(parent, fg_color=SURFACE_CONTAINER, height=60, corner_radius=0)
        toolbar.pack(fill="x", padx=0, pady=0)
        toolbar.pack_propagate(False)
        
        # View title
        self.view_title = ctk.CTkLabel(
            toolbar,
            text="⭐ Smart Priority",
            font=HEADER_FONT,
            text_color=TEXT_PRIMARY
        )
        self.view_title.pack(side="left", padx=20, pady=15)
        
        # Search bar
        search_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        search_frame.pack(side="right", padx=20, pady=15)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Search files...",
            width=300,
            height=35,
            font=BODY_FONT,
            fg_color=SURFACE,
            border_color=OUTLINE,
            corner_radius=RADIUS_LG
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        
        search_btn = ctk.CTkButton(
            search_frame,
            text="Search",
            command=self.perform_search,
            width=80,
            height=35,
            font=BODY_FONT,
            fg_color=PRIMARY,
            text_color=ON_PRIMARY,
            hover_color=ON_PRIMARY_CONTAINER,
            corner_radius=RADIUS_LG
        )
        search_btn.pack(side="left")

    def build_file_list(self, parent):
        """Build file list area"""
        list_container = ctk.CTkFrame(parent, fg_color=SURFACE)
        list_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Scrollable container for headers and rows
        self.file_list_frame = ctk.CTkScrollableFrame(
            list_container,
            fg_color=SURFACE,
            corner_radius=0
        )
        self.file_list_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Column headers inside scrollable (tagged to preserve during clear)
        headers_frame = ctk.CTkFrame(self.file_list_frame, fg_color=SURFACE_CONTAINER, height=40, corner_radius=0)
        headers_frame.pack(fill="x", padx=0, pady=(0, 5))
        headers_frame.pack_propagate(False)
        headers_frame._is_header = True
        
        headers = [
            ("Name", 0.5),
            ("Type", 0.15),
            ("Last Opened", 0.2),
            ("Actions", 0.15)
        ]
        
        for header_text, width_ratio in headers:
            header = ctk.CTkLabel(
                headers_frame,
                text=header_text,
                font=("Segoe UI", 10, "bold"),
                text_color=TEXT_SECONDARY,
                anchor="w"
            )
            x_pos = sum(h[1] for h in headers[:headers.index((header_text, width_ratio))])
            header.place(relx=x_pos, x=10, rely=0.5, anchor="w", relwidth=width_ratio)

    def build_status_bar(self, parent):
        """Build bottom status bar"""
        status_bar = ctk.CTkFrame(parent, fg_color=SURFACE_CONTAINER, height=35, corner_radius=0)
        status_bar.pack(fill="x", padx=0, pady=0, side="bottom")
        status_bar.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            status_bar,
            text="Ready",
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY
        )
        self.status_label.pack(side="left", padx=15, pady=8)
        
        self.file_count_label = ctk.CTkLabel(
            status_bar,
            text="0 files",
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY
        )
        self.file_count_label.pack(side="right", padx=15, pady=8)

    def switch_view(self, view_name):
        """Switch between different views"""
        self.current_view = view_name
        
        # Update nav button styles
        for name, btn in self.nav_buttons.items():
            if name == view_name:
                btn.configure(fg_color=PRIMARY_CONTAINER, text_color=ON_PRIMARY_CONTAINER)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_PRIMARY)
        
        # Update view title
        titles = {
            "smart": "⭐ Smart Priority",
            "clusters": "📂 Categories",
            "all": "📋 All Files"
        }
        self.view_title.configure(text=titles.get(view_name, "Files"))
        
        # Load view data
        self.load_view(view_name)

    def load_view(self, view_name):
        """Load data for the selected view"""
        logging.info(f"Loading view {view_name}")
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        if view_name == "smart":
            self.load_smart_priority()
        elif view_name == "clusters":
            self.load_clusters()
        elif view_name == "all":
            self.load_all_files()

    def load_smart_priority(self):
        """Load smart priority files"""
        # Show loading state
        self.show_loading_state("Loading smart priority...")
        
        # Load in background thread
        threading.Thread(target=self._load_smart_priority_async, daemon=True).start()
    
    def _load_smart_priority_async(self):
        """Load smart priority in background"""
        try:
            files = get_smart_priority_files(limit=50)
            
            logging.info(f"Files to display: {[os.path.basename(f['path']) for f in files]}")
            
            # Update UI on main thread
            self.after(0, self._display_smart_priority, files)
            
        except Exception as e:
            logging.error(f"Error loading smart priority: {e}")
            self.after(0, lambda: self.show_empty_state("Unable to load smart priority files. Please check your database connection."))
    
    def _display_smart_priority(self, files):
        """Display smart priority files on main thread"""
        # Clear loading state (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        if not files:
            self.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        added_paths = set()
        for file_data in files:
            # Normalize path for accurate deduplication
            norm_path = os.path.normpath(os.path.abspath(file_data["path"]))
            if norm_path not in added_paths:
                self.create_file_row(file_data, file_data.get("last_opened"))
                added_paths.add(norm_path)
        
        logging.info(f"Displayed smart files: {list(added_paths)}")
        self.file_count_label.configure(text=f"{len(added_paths)} files")
        self.status_label.configure(text="Smart priority loaded")


    def load_clusters(self):
        """Load clustered files with smart auto-refresh"""
        if self.needs_cluster_refresh:
            logging.info("Smart Refresh: New files detected, refreshing clusters...")
            self.refresh_clusters()
        else:
            self.show_loading_state("Loading categories...")
            threading.Thread(target=self._load_clusters_async, daemon=True).start()
    
    def _load_clusters_async(self):
        """Load clusters in background"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT cluster_label, COUNT(*) as count
                FROM files
                WHERE cluster_label IS NOT NULL
                GROUP BY cluster_label
                ORDER BY count DESC
            """)
            clusters = cur.fetchall()
            conn.close()
            
            self.after(0, self._display_clusters, clusters)
            
        except Exception as e:
            logging.error(f"Error loading clusters: {e}")
            self.after(0, lambda: self.show_empty_state("Unable to load file categories. Please check your database connection."))
    
    def _display_clusters(self, clusters):
        """Display clusters on main thread"""
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        if not clusters:
            self.show_empty_state("No clusters yet. Click 'Refresh Clusters' to organize your files!")
            return
        
        added_paths = set()
        for cluster_label, count in clusters:
            self.create_cluster_section(cluster_label, count, added_paths)
        
        total_files = len(added_paths)
        self.file_count_label.configure(text=f"{total_files} files in {len(clusters)} categories")
        self.status_label.configure(text="Categories loaded")

    def load_all_files(self):
        """Load all files"""
        self.show_loading_state("Loading all files...")
        threading.Thread(target=self._load_all_files_async, daemon=True).start()
    
    def _load_all_files_async(self):
        """Load all files in background"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT path, access_count, last_opened
                FROM files
                ORDER BY last_opened DESC
            """)
            rows = cur.fetchall()
            conn.close()
            
            self.after(0, self._display_all_files, rows)
            
        except Exception as e:
            logging.error(f"Error loading files: {e}")
            self.after(0, lambda: self.show_empty_state("Unable to load all files. Please check your database connection."))
    
    def _display_all_files(self, rows):
        """Display all files on main thread"""
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        if not rows:
            self.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        added_paths = set()
        for path, count, last_opened in rows:
            # Normalize path for accurate deduplication
            norm_path = os.path.normpath(os.path.abspath(path))
            if norm_path not in added_paths:
                file_data = {
                    "path": path,
                    "score": count / 10.0,  # Normalize
                    "reasons": {"Freq": str(count)}
                }
                self.create_file_row(file_data, last_opened)
                added_paths.add(norm_path)
        
        self.file_count_label.configure(text=f"{len(added_paths)} files")
        self.status_label.configure(text="All files loaded")

    def create_file_row(self, file_data, last_opened=None):
        """Create a file row in the list"""
        path = file_data["path"]
        
        logging.info(f"Creating file row for {os.path.basename(path)}")
        
        # Determine selection color
        is_selected = path in self.selected_files
        fg_color = PRIMARY_CONTAINER if is_selected else "transparent"
        
        # File row container
        row = ctk.CTkFrame(
            self.file_list_frame,
            fg_color=fg_color,
            height=50,
            corner_radius=RADIUS_SM
        )
        row.pack(fill="x", padx=10, pady=2)
        row.pack_propagate(False)
        
        # Hover effect - preserve selection color
        def on_enter(e):
            if path not in self.selected_files:
                row.configure(fg_color=SURFACE_CONTAINER_HIGH)
        
        def on_leave(e):
            if path not in self.selected_files:
                row.configure(fg_color="transparent")
        
        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)
        
        # Click to select (with Ctrl for multi-select)
        def on_click(e):
            if e.state & 0x4:  # Ctrl key pressed (state bit 2)
                if path in self.selected_files:
                    self.selected_files.remove(path)
                    row.configure(fg_color="transparent")
                else:
                    self.selected_files.add(path)
                    row.configure(fg_color=PRIMARY_CONTAINER)
            else:
                # Single select - clear others
                self.selected_files.clear()
                self.selected_files.add(path)
                # Refresh to update all rows
                self.load_view(self.current_view)
        
        row.bind("<Button-1>", on_click)
        # Also bind to children widgets
        for child in row.winfo_children():
            child.bind("<Button-1>", lambda e, p=path: on_click(e))
        
        # Right-click context menu
        def on_right_click(e):
            self.show_context_menu(path, e.x_root, e.y_root)
        
        row.bind("<Button-3>", on_right_click)  # Right-click on Windows/Linux
        row.bind("<Button-2>", on_right_click)  # Right-click on macOS
        for child in row.winfo_children():
            child.bind("<Button-3>", lambda e, p=path: self.show_context_menu(p, e.x_root, e.y_root))
            child.bind("<Button-2>", lambda e, p=path: self.show_context_menu(p, e.x_root, e.y_root))
        
        # Icon + Name
        ext = os.path.splitext(path)[1].lower()
        icon = FILE_ICONS.get(ext, FILE_ICONS["default"])
        name = os.path.basename(path)
        
        name_label = ctk.CTkLabel(
            row,
            text=f"{icon}  {name}",
            font=BODY_FONT,
            text_color=TEXT_PRIMARY,
            anchor="w"
        )
        name_label.place(relx=0, rely=0.5, anchor="w", relwidth=0.5)
        name_label.bind("<Double-Button-1>", lambda e: self.open_existing_file(path))
        
        # Type
        file_type = ext[1:].upper() if ext else "FILE"
        type_label = ctk.CTkLabel(
            row,
            text=file_type,
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY,
            anchor="w"
        )
        type_label.place(relx=0.5, rely=0.5, anchor="w", relwidth=0.15)
        
        # Last Opened
        if last_opened:
            time_text = self.format_time(last_opened)
        else:
            time_text = "Recently"
        
        time_label = ctk.CTkLabel(
            row,
            text=time_text,
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY,
            anchor="w"
        )
        time_label.place(relx=0.65, rely=0.5, anchor="w", relwidth=0.2)
        
        # Open folder button
        folder_btn = ctk.CTkButton(
            row,
            text="📁",
            command=lambda: self.open_containing_folder(path),
            width=30,
            height=30,
            fg_color="transparent",
            hover_color=SURFACE_CONTAINER_HIGH,
            font=BODY_FONT
        )
        folder_btn.place(relx=0.85, rely=0.5, anchor="w")
        
        # Delete button
        delete_btn = ctk.CTkButton(
            row,
            text="🗑️",
            command=lambda: self.delete_file(path),
            width=30,
            height=30,
            fg_color="transparent",
            hover_color=ERROR,
            font=BODY_FONT
        )
        delete_btn.place(relx=0.91, rely=0.5, anchor="w")

    def create_cluster_section(self, cluster_label, count, added_paths):
        """Create a cluster section"""
        # Cluster header
        header = ctk.CTkFrame(
            self.file_list_frame,
            fg_color=SURFACE_CONTAINER,
            height=45,
            corner_radius=RADIUS_SM
        )
        header.pack(fill="x", padx=10, pady=(10, 5))
        header.pack_propagate(False)
        
        label = ctk.CTkLabel(
            header,
            text=f"📁 {cluster_label}",
            font=HEADER_FONT,
            text_color=TEXT_PRIMARY,
            anchor="w"
        )
        label.pack(side="left", padx=15, pady=10)
        
        count_label = ctk.CTkLabel(
            header,
            text=f"{count} files",
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY
        )
        count_label.pack(side="right", padx=15, pady=10)
        
        # Load files in this cluster
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT path, access_count, last_opened
            FROM files
            WHERE cluster_label = ?
            ORDER BY access_count DESC
            LIMIT 10
        """, (cluster_label,))
        files = cur.fetchall()
        conn.close()
        
        for path, count, last_opened in files:
            norm_path = os.path.normpath(os.path.abspath(path))
            if norm_path not in added_paths:
                file_data = {
                    "path": path,
                    "score": count / 10.0,
                    "reasons": {}
                }
                self.create_file_row(file_data, last_opened)
                added_paths.add(norm_path)

    def show_empty_state(self, message):
        """Show empty state message with improved visual design"""
        empty_frame = ctk.CTkFrame(self.file_list_frame, fg_color="transparent")
        empty_frame.pack(expand=True, fill="both", pady=100)
        
        # Large icon
        icon_label = ctk.CTkLabel(
            empty_frame,
            text="📂",
            font=("Segoe UI", 48),
            text_color=TEXT_SECONDARY
        )
        icon_label.pack(pady=(0, 20))
        
        # Main message
        label = ctk.CTkLabel(
            empty_frame,
            text=message,
            font=BODY_FONT,
            text_color=TEXT_SECONDARY,
            wraplength=400
        )
        label.pack(pady=(0, 30))
        
        # Quick action buttons
        if "No files tracked" in message or "Add some files" in message:
            add_btn = ctk.CTkButton(
                empty_frame,
                text="➕ Add Your First File",
                command=self.open_file,
                fg_color=PRIMARY,
                text_color=ON_PRIMARY,
                hover_color=ON_PRIMARY_CONTAINER,
                height=40,
                font=BODY_FONT
            )
            add_btn.pack(pady=5)
        
        # Helpful tip
        tip_label = ctk.CTkLabel(
            empty_frame,
            text="💡 Tip: Press Ctrl+O to add files, Delete to remove selected",
            font=SMALL_FONT,
            text_color="#606060"
        )
        tip_label.pack(pady=(30, 0))
    
    def show_loading_state(self, message="Loading..."):
        """Show loading state"""
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        loading_frame = ctk.CTkFrame(self.file_list_frame, fg_color="transparent")
        loading_frame.pack(expand=True, fill="both", pady=100)
        
        label = ctk.CTkLabel(
            loading_frame,
            text=f"⏳ {message}",
            font=BODY_FONT,
            text_color=TEXT_SECONDARY
        )
        label.pack()
        
        # Add progress bar
        progress_bar = ctk.CTkProgressBar(
            loading_frame,
            mode="indeterminate",
            width=200
        )
        progress_bar.pack(pady=10)
        progress_bar.start()
        
        self.status_label.configure(text=message)

    def format_time(self, timestamp_str):
        """Format timestamp to exact date and time"""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.strftime("%b %d, %Y %I:%M %p")
        except:
            return "Unknown"

    def perform_search(self):
        """Perform semantic search"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        # Sanitize query
        if len(query) > 500: # Increased limit
            query = query[:500]
            messagebox.showinfo("Info", "Search query was truncated to 500 characters.")
        
        logging.info(f"Performing search: {query}")
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        self.status_label.configure(text="Searching...")
        
        # Run search in background
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query):
        """Perform search in background"""
        try:
            searcher = self._ensure_semantic_searcher()
            semantic_results = searcher.search(query, top_k=10)
            
            # Filter semantic results by threshold
            threshold = 0.2
            semantic_results = [r for r in semantic_results if r["score"] >= threshold]
            
            # Add keyword matches
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, path FROM files WHERE lower(searchable_text) LIKE lower(?)", ('%' + query + '%',))
            keyword_rows = cur.fetchall()
            conn.close()
            
            keyword_results = []
            for row in keyword_rows:
                file_id, path = row
                keyword_results.append({
                    "file_id": file_id,
                    "path": path,
                    "score": 0.5  # Fixed score for keyword matches
                })
            
            # Combine and sort results
            all_results_dict = {}
            for r in semantic_results + keyword_results:
                path = r["path"]
                if path not in all_results_dict or r["score"] > all_results_dict[path]["score"]:
                    all_results_dict[path] = r
            all_results = list(all_results_dict.values())
            all_results.sort(key=lambda x: x['score'], reverse=True)
            results = all_results[:15]  # Limit to top 15
            
            # Update UI on main thread
            self.after(0, self._update_search_results, results)
        except Exception as e:
            logging.error(f"Search error: {e}")
            self.after(0, lambda: self.status_label.configure(text="Search failed. Please try again."))

    def _update_search_results(self, results):
        """Update search results on main thread"""
        # Clear current list (preserve headers)
        for widget in self.file_list_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()
        
        if not results:
            self.show_empty_state("No results found")
            self.status_label.configure(text="No results")
            return
        
        seen = set()
        for result in results:
            norm_path = os.path.normcase(os.path.normpath(os.path.abspath(result["path"])))
            if norm_path not in seen:
                file_data = {
                    "path": result["path"],
                    "score": result["score"],
                    "reasons": {}
                }
                self.create_file_row(file_data)
                seen.add(norm_path)
        
        self.file_count_label.configure(text=f"{len(seen)} results")
        self.status_label.configure(text=f"Found {len(seen)} results")

    def open_file(self):
        """Open file dialog to add a file"""
        logging.info("Opening file dialog")
        file_path = filedialog.askopenfilename(title="Select a file to track")
        if not file_path:
            logging.info("File dialog canceled")
            return
        
        # Normalize path to prevent duplicates from different path formats
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # Disable add button to prevent multiple additions
        self.add_btn.configure(state="disabled")
        
        # Validate file path
        if not os.path.exists(file_path):
            logging.warning(f"Selected file does not exist: {file_path}")
            messagebox.showerror("Error", "Selected file does not exist.")
            self.add_btn.configure(state="normal")
            return
        
        # Check if file already added
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM files WHERE lower(path) = lower(?)", (file_path,))
        if cur.fetchone():
            messagebox.showinfo("Info", "This file is already added.")
            conn.close()
            self.add_btn.configure(state="normal")
            return
        conn.close()
        
        if not os.access(file_path, os.R_OK):
            logging.warning(f"Selected file is not readable: {file_path}")
            messagebox.showerror("Error", "Selected file is not readable.")
            self.add_btn.configure(state="normal")
            return
        
        # Process in background thread to keep UI responsive
        self.status_label.configure(text=f"Adding {os.path.basename(file_path)}...")
        threading.Thread(target=self._add_file_async, args=(file_path,), daemon=True).start()

    def _add_file_async(self, file_path):
        """Add file processing in background"""
        try:
            from text_extractor import get_searchable_text
            
            # This is the heavy operation
            searchable_text = get_searchable_text(file_path)
            
            logging.info(f"Added file {file_path} with searchable_text snippet: {searchable_text[:100]}")
            
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO files(path, searchable_text, access_count, last_opened)
                VALUES (?, ?, 1, datetime('now'))
            """, (file_path, searchable_text))
            conn.commit()
            conn.close()
            
            # Update UI on main thread
            self.after(0, self._on_file_added_success, file_path)
            
        except Exception as e:
            logging.error(f"Failed to add file: {e}")
            self.after(0, lambda err=e: messagebox.showerror("Error", f"Failed to add file: {err}"))
            self.after(0, lambda: self.add_btn.configure(state="normal"))


    def _on_file_added_success(self, file_path):
        """Callback for successful file addition"""
        self.status_label.configure(text=f"Added: {os.path.basename(file_path)}")
        self.add_btn.configure(state="normal")
        
        # Mark for clustering refresh
        self.needs_cluster_refresh = True
        
        # Refresh semantic searcher to include the new file
        if self.semantic_searcher:
            threading.Thread(target=self.semantic_searcher.load_files, daemon=True).start()
        
        # Refresh current view
        self.load_view(self.current_view)
        
        # Open the file
        self.open_existing_file(file_path)

    def open_existing_file(self, file_path):
        """Open an existing tracked file"""
        try:
            # Ensure absolute path
            file_path = os.path.normpath(os.path.abspath(file_path))
            
            if not os.path.exists(file_path):
                messagebox.showerror("Error", f"File not found on disk:\n{file_path}")
                return
            
            # Open file (Cross-platform)
            open_path(file_path)
            
            # Log session in background
            threading.Thread(
                target=self.process_file_session,
                args=(file_path,),
                daemon=True
            ).start()
            
            self.status_label.configure(text=f"Opened: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")

    def open_containing_folder(self, file_path):
        """Open the folder containing the file"""
        try:
            folder_path = os.path.dirname(os.path.abspath(file_path))
            if os.path.exists(folder_path):
                open_path(folder_path)
                self.status_label.configure(text=f"Opened folder: {os.path.basename(folder_path)}")
            else:
                messagebox.showerror("Error", "Folder not found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")

    def show_context_menu(self, file_path, x, y):
        """Show right-click context menu for a file with proper cleanup"""
        # Cleanup existing menu if any
        if self.active_context_menu and self.active_context_menu.winfo_exists():
            self.active_context_menu.destroy()
            
        menu = ctk.CTkToplevel(self)
        self.active_context_menu = menu
        menu.overrideredirect(True)
        menu.geometry(f"+{x}+{y}")
        menu.configure(fg_color=SURFACE_CONTAINER)
        
        # Menu items
        menu_items = [
            ("📄 Open File", lambda: self.open_existing_file(file_path)),
            ("📁 Open Folder", lambda: self.open_containing_folder(file_path)),
            ("───", None),
            ("📋 Copy Path", lambda: self.copy_file_path(file_path)),
            ("───", None),
            ("🗑️ Remove from App", lambda: self.delete_file(file_path)),
        ]
        
        for text, command in menu_items:
            if text.startswith("───"):
                separator = ctk.CTkFrame(menu, height=1, fg_color=OUTLINE)
                separator.pack(fill="x", padx=5, pady=2)
            else:
                btn = ctk.CTkButton(
                    menu,
                    text=text,
                    command=lambda cmd=command, m=menu: (cmd(), m.destroy()),
                    fg_color="transparent",
                    hover_color=SURFACE_CONTAINER_HIGH,
                    anchor="w",
                    height=30,
                    font=BODY_FONT
                )
                btn.pack(fill="x", padx=5, pady=1)
        
        # Proper modal behavior: Close when clicking away
        def on_focus_out(event):
            if menu.winfo_exists():
                menu.destroy()
                
        menu.bind("<FocusOut>", on_focus_out)
        menu.focus_set()
        menu.grab_set() # Capture all events until closed

    def copy_file_path(self, file_path):
        """Copy file path to clipboard"""
        self.clipboard_clear()
        self.clipboard_append(file_path)
        self.status_label.configure(text="Path copied to clipboard")

    def process_file_session(self, file_path):
        """Handle logging and waiting in background thread"""
        try:
            start_file_session(file_path)
            
            # Wait for file close (approximate)
            time.sleep(10)
            end_file_session(file_path)
            
            # Removed refresh to prevent duplicate listings
            
        except Exception as e:
            logging.error(f"Session error: {e}")

    def delete_file(self, file_path):
        """Delete file from tracking (not from disk)"""
        try:
            result = messagebox.askyesno(
                "Confirm Remove",
                f"Remove this file from the app?\n(File will remain on your disk)\n\n{os.path.basename(file_path)}"
            )
            
            if not result:
                return
            
            # Remove from database
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM files WHERE lower(path) = lower(?)", (file_path,))
            deleted_count = cur.rowcount
            conn.commit()
            conn.close()
            
            logging.info(f"Deleted {deleted_count} rows for path: {file_path}")
            
            if deleted_count == 0:
                messagebox.showwarning("Warning", "File was not found in the database. It may have already been removed.")
                return
            
            # Mark for clustering refresh
            self.needs_cluster_refresh = True
            
            # Remove from semantic search
            if self.semantic_searcher:
                self.semantic_searcher.remove_file(file_path)
            
            # Remove from active sessions
            remove_file_session(file_path)
            
            # Refresh view
            self.load_view(self.current_view)
            
            self.status_label.configure(text=f"Removed: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove file: {e}")

    def delete_selected_files(self):
        """Delete all selected files (batch operation)"""
        if not self.selected_files:
            messagebox.showinfo("Info", "No files selected. Click on files to select them.")
            return
        
        file_list = "\n".join([f"  • {os.path.basename(p)}" for p in self.selected_files])
        result = messagebox.askyesno(
            "Confirm Batch Remove",
            f"Remove these {len(self.selected_files)} files from the app?\n(Files will remain on your disk)\n\n{file_list}"
        )
        
        if not result:
            return
        
        deleted_count = 0
        for file_path in list(self.selected_files):
            try:
                conn = get_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute("DELETE FROM files WHERE lower(path) = lower(?)", (file_path,))
                if cur.rowcount > 0:
                    deleted_count += 1
                    logging.info(f"Deleted file: {file_path}")
                    # Remove from semantic search
                    if self.semantic_searcher:
                        self.semantic_searcher.remove_file(file_path)
                    # Remove from active sessions
                    remove_file_session(file_path)
                conn.commit()
                conn.close()
            except Exception as e:
                logging.error(f"Failed to delete {file_path}: {e}")
        
        # Mark for clustering refresh
        if deleted_count > 0:
            self.needs_cluster_refresh = True
            
        # Clear selection
        self.selected_files.clear()
        
        # Refresh view
        self.load_view(self.current_view)
        self.status_label.configure(text=f"Removed {deleted_count} files")
        messagebox.showinfo("Complete", f"Successfully removed {deleted_count} files.")

    def refresh_clusters(self):
        """Refresh file clusters with visual feedback"""
        logging.info("Refreshing clusters")
        self.show_loading_state("Clustering files...")
        
        def do_cluster():
            try:
                run_filename_clustering()
                self.needs_cluster_refresh = False
                self.after(0, lambda: self.status_label.configure(text="Clustering complete"))
                self.after(0, lambda: self.load_view(self.current_view))
            except Exception as e:
                logging.error(f"Clustering failed: {e}")
                self.after(0, lambda: self.status_label.configure(text="Clustering failed. Check logs for details."))
        
        threading.Thread(target=do_cluster, daemon=True).start()

    def _ensure_clustering(self):
        """Run clustering on startup if needed"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE cluster_label IS NULL")
            unclustered_count = cur.fetchone()[0]
            conn.close()
            
            if unclustered_count > 0:
                self.needs_cluster_refresh = True
        except:
            pass

    def _ensure_semantic_searcher(self):
        """Lazily load SemanticSearch singleton on first use with status updates"""
        if self.semantic_searcher is None:
            try:
                # Update status if we're on the main thread, otherwise use after
                status_msg = "Initializing AI Model (First run may take a minute)..."
                self.after(0, lambda: self.status_label.configure(text=status_msg))
                
                from ml.semantic_search import get_semantic_searcher
                self.semantic_searcher = get_semantic_searcher()
                
                self.after(0, lambda: self.status_label.configure(text="AI Model Ready"))
            except Exception as e:
                self.semantic_searcher = None
                logging.error(f"Failed to initialize semantic search: {e}")
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to initialize semantic search: {e}"))
        return self.semantic_searcher


if __name__ == "__main__":
    logging.info(f"USING DATABASE: {DB_PATH}")
    app = ModernFileManager()
    app.mainloop()
