import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import sqlite3
from datetime import datetime

from database import init_db
from logger import start_file_session, end_file_session
from ml.filename_cluster import run_filename_clustering
from ml.recommendation import get_smart_priority_files

from config import DB_PATH, COLORS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

init_db()

# Modern File Manager Color Scheme
SIDEBAR_BG = "#1E1E1E"
MAIN_BG = "#252525"
CONTENT_BG = "#2B2B2B"
HOVER_BG = "#3C3C3C"
SELECTED_BG = "#0E639C"
BORDER_COLOR = "#3E3E3E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0A0"
ACCENT_COLOR = "#0078D4"
DELETE_COLOR = "#E81123"

# Typography
TITLE_FONT = ("Segoe UI", 18, "bold")
HEADER_FONT = ("Segoe UI", 14, "bold")
BODY_FONT = ("Segoe UI", 11)
SMALL_FONT = ("Segoe UI", 10)

# File type icons
FILE_ICONS = {
    ".pdf": "📄",
    ".doc": "📝",
    ".docx": "📝",
    ".txt": "📃",
    ".xls": "📊",
    ".xlsx": "📊",
    ".ppt": "📊",
    ".pptx": "📊",
    ".jpg": "🖼️",
    ".png": "🖼️",
    ".gif": "🖼️",
    ".zip": "📦",
    ".rar": "📦",
    "default": "📄"
}


class ModernFileManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("📁 Smart File Organizer")
        self.geometry("1200x750")
        self.minsize(1000, 600)

        # State
        self.current_view = "smart"  # smart, clusters, all
        self.selected_file = None
        self.semantic_searcher = None

        # Build UI
        self.build_ui()
        
        # Load initial data
        self.load_view("smart")
        
        # Run clustering if needed
        self._ensure_clustering()

    def build_ui(self):
        """Build the modern file manager UI"""
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color=MAIN_BG)
        main_container.pack(fill="both", expand=True)
        
        # Sidebar
        self.build_sidebar(main_container)
        
        # Content area
        content_frame = ctk.CTkFrame(main_container, fg_color=MAIN_BG)
        content_frame.pack(side="left", fill="both", expand=True)
        
        # Toolbar
        self.build_toolbar(content_frame)
        
        # File list area
        self.build_file_list(content_frame)
        
        # Status bar
        self.build_status_bar(content_frame)

    def build_sidebar(self, parent):
        """Build left sidebar navigation"""
        sidebar = ctk.CTkFrame(parent, fg_color=SIDEBAR_BG, width=220, corner_radius=0)
        sidebar.pack(side="left", fill="y", padx=0, pady=0)
        sidebar.pack_propagate(False)
        
        # App title
        title_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(20, 30))
        
        title = ctk.CTkLabel(
            title_frame, 
            text="📁 File Organizer", 
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
        divider = ctk.CTkFrame(sidebar, fg_color=BORDER_COLOR, height=1)
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
        add_btn = ctk.CTkButton(
            sidebar,
            text="➕ Add File",
            command=self.open_file,
            fg_color=ACCENT_COLOR,
            hover_color="#106EBE",
            height=40,
            font=BODY_FONT,
            corner_radius=6
        )
        add_btn.pack(fill="x", padx=15, pady=5)
        
        # Refresh Clusters button
        refresh_btn = ctk.CTkButton(
            sidebar,
            text="🔄 Refresh Clusters",
            command=self.refresh_clusters,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_COLOR,
            hover_color=HOVER_BG,
            height=40,
            font=BODY_FONT,
            corner_radius=6
        )
        refresh_btn.pack(fill="x", padx=15, pady=5)

    def create_nav_button(self, parent, text, view_name):
        """Create a navigation button"""
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=lambda: self.switch_view(view_name),
            fg_color="transparent",
            hover_color=HOVER_BG,
            anchor="w",
            height=40,
            font=BODY_FONT,
            corner_radius=6
        )
        btn.pack(fill="x", pady=2)
        return btn

    def build_toolbar(self, parent):
        """Build top toolbar"""
        toolbar = ctk.CTkFrame(parent, fg_color=CONTENT_BG, height=60, corner_radius=0)
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
            fg_color=MAIN_BG,
            border_color=BORDER_COLOR
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
            fg_color=ACCENT_COLOR,
            hover_color="#106EBE"
        )
        search_btn.pack(side="left")

    def build_file_list(self, parent):
        """Build file list area"""
        list_container = ctk.CTkFrame(parent, fg_color=MAIN_BG)
        list_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Column headers
        headers_frame = ctk.CTkFrame(list_container, fg_color=CONTENT_BG, height=40, corner_radius=0)
        headers_frame.pack(fill="x", padx=0, pady=0)
        headers_frame.pack_propagate(False)
        
        headers = [
            ("Name", 0.4),
            ("Type", 0.15),
            ("Last Opened", 0.2),
            ("Score", 0.15),
            ("Actions", 0.1)
        ]
        
        for header_text, width_ratio in headers:
            header = ctk.CTkLabel(
                headers_frame,
                text=header_text,
                font=("Segoe UI", 10, "bold"),
                text_color=TEXT_SECONDARY,
                anchor="w"
            )
            header.place(relx=sum(h[1] for h in headers[:headers.index((header_text, width_ratio))]), 
                        rely=0.5, anchor="w", relwidth=width_ratio)
        
        # Scrollable file list
        self.file_list_frame = ctk.CTkScrollableFrame(
            list_container,
            fg_color=MAIN_BG,
            corner_radius=0
        )
        self.file_list_frame.pack(fill="both", expand=True, padx=0, pady=0)

    def build_status_bar(self, parent):
        """Build bottom status bar"""
        status_bar = ctk.CTkFrame(parent, fg_color=CONTENT_BG, height=35, corner_radius=0)
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
                btn.configure(fg_color=SELECTED_BG)
            else:
                btn.configure(fg_color="transparent")
        
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
        # Clear current list
        for widget in self.file_list_frame.winfo_children():
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
            
            # Update UI on main thread
            self.after(0, self._display_smart_priority, files)
            
        except Exception as e:
            print(f"Error loading smart priority: {e}")
            self.after(0, lambda: self.show_empty_state(f"Error: {e}"))
    
    def _display_smart_priority(self, files):
        """Display smart priority files on main thread"""
        # Clear loading state
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
        
        if not files:
            self.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        for file_data in files:
            self.create_file_row(file_data)
        
        self.file_count_label.configure(text=f"{len(files)} files")
        self.status_label.configure(text="Smart priority loaded")


    def load_clusters(self):
        """Load clustered files"""
        self.show_loading_state("Loading categories...")
        threading.Thread(target=self._load_clusters_async, daemon=True).start()
    
    def _load_clusters_async(self):
        """Load clusters in background"""
        try:
            conn = sqlite3.connect(DB_PATH)
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
            print(f"Error loading clusters: {e}")
            self.after(0, lambda: self.show_empty_state(f"Error: {e}"))
    
    def _display_clusters(self, clusters):
        """Display clusters on main thread"""
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
        
        if not clusters:
            self.show_empty_state("No clusters yet. Click 'Refresh Clusters' to organize your files!")
            return
        
        for cluster_label, count in clusters:
            self.create_cluster_section(cluster_label, count)
        
        total_files = sum(c[1] for c in clusters)
        self.file_count_label.configure(text=f"{total_files} files in {len(clusters)} categories")
        self.status_label.configure(text="Categories loaded")

    def load_all_files(self):
        """Load all files"""
        self.show_loading_state("Loading all files...")
        threading.Thread(target=self._load_all_files_async, daemon=True).start()
    
    def _load_all_files_async(self):
        """Load all files in background"""
        try:
            conn = sqlite3.connect(DB_PATH)
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
            print(f"Error loading files: {e}")
            self.after(0, lambda: self.show_empty_state(f"Error: {e}"))
    
    def _display_all_files(self, rows):
        """Display all files on main thread"""
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
        
        if not rows:
            self.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        for path, count, last_opened in rows:
            file_data = {
                "path": path,
                "score": count / 10.0,  # Normalize
                "reasons": {"Freq": str(count)}
            }
            self.create_file_row(file_data, last_opened)
        
        self.file_count_label.configure(text=f"{len(rows)} files")
        self.status_label.configure(text="All files loaded")

    def create_file_row(self, file_data, last_opened=None):
        """Create a file row in the list"""
        path = file_data["path"]
        score = file_data.get("score", 0)
        
        # File row container
        row = ctk.CTkFrame(
            self.file_list_frame,
            fg_color="transparent",
            height=50,
            corner_radius=6
        )
        row.pack(fill="x", padx=10, pady=2)
        row.pack_propagate(False)
        
        # Hover effect
        row.bind("<Enter>", lambda e: row.configure(fg_color=HOVER_BG))
        row.bind("<Leave>", lambda e: row.configure(fg_color="transparent"))
        
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
        name_label.place(relx=0, rely=0.5, anchor="w", relwidth=0.4)
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
        type_label.place(relx=0.4, rely=0.5, anchor="w", relwidth=0.15)
        
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
        time_label.place(relx=0.55, rely=0.5, anchor="w", relwidth=0.2)
        
        # Score
        score_text = f"{score:.2f}" if score > 0 else "-"
        score_label = ctk.CTkLabel(
            row,
            text=score_text,
            font=SMALL_FONT,
            text_color=ACCENT_COLOR if score > 0.5 else TEXT_SECONDARY,
            anchor="w"
        )
        score_label.place(relx=0.75, rely=0.5, anchor="w", relwidth=0.15)
        
        # Delete button
        delete_btn = ctk.CTkButton(
            row,
            text="🗑️",
            command=lambda: self.delete_file(path),
            width=40,
            height=30,
            fg_color="transparent",
            hover_color=DELETE_COLOR,
            font=BODY_FONT
        )
        delete_btn.place(relx=0.9, rely=0.5, anchor="w", relwidth=0.1)

    def create_cluster_section(self, cluster_label, count):
        """Create a cluster section"""
        # Cluster header
        header = ctk.CTkFrame(
            self.file_list_frame,
            fg_color=CONTENT_BG,
            height=45,
            corner_radius=6
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
        conn = sqlite3.connect(DB_PATH)
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
            file_data = {
                "path": path,
                "score": count / 10.0,
                "reasons": {}
            }
            self.create_file_row(file_data, last_opened)

    def show_empty_state(self, message):
        """Show empty state message"""
        empty_frame = ctk.CTkFrame(self.file_list_frame, fg_color="transparent")
        empty_frame.pack(expand=True, fill="both", pady=100)
        
        label = ctk.CTkLabel(
            empty_frame,
            text=message,
            font=BODY_FONT,
            text_color=TEXT_SECONDARY
        )
        label.pack()
    
    def show_loading_state(self, message="Loading..."):
        """Show loading state"""
        # Clear current list
        for widget in self.file_list_frame.winfo_children():
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
        
        self.status_label.configure(text=message)

    def format_time(self, timestamp_str):
        """Format timestamp to human readable"""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            now = datetime.now()
            diff = now - dt
            
            if diff.days == 0:
                return "Today"
            elif diff.days == 1:
                return "Yesterday"
            elif diff.days < 7:
                return f"{diff.days} days ago"
            else:
                return dt.strftime("%b %d, %Y")
        except:
            return "Unknown"

    def perform_search(self):
        """Perform semantic search"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        # Clear current list
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
        
        self.status_label.configure(text="Searching...")
        
        # Run search in background
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query):
        """Perform search in background"""
        try:
            searcher = self._ensure_semantic_searcher()
            results = searcher.search(query, top_k=20)
            
            # Filter by threshold
            threshold = 0.1
            results = [r for r in results if r["score"] >= threshold]
            
            # Update UI on main thread
            self.after(0, self._update_search_results, results)
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text=f"Search error: {e}"))

    def _update_search_results(self, results):
        """Update search results on main thread"""
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
        
        if not results:
            self.show_empty_state("No results found")
            self.status_label.configure(text="No results")
            return
        
        for result in results:
            file_data = {
                "path": result["path"],
                "score": result["score"],
                "reasons": {}
            }
            self.create_file_row(file_data)
        
        self.file_count_label.configure(text=f"{len(results)} results")
        self.status_label.configure(text=f"Found {len(results)} results")

    def open_file(self):
        """Open file dialog to add a file"""
        file_path = filedialog.askopenfilename(title="Select a file to track")
        if not file_path:
            return
        
        try:
            from text_extractor import get_searchable_text
            
            searchable_text = get_searchable_text(file_path)
            
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO files(path, searchable_text, access_count, last_opened)
                VALUES (?, ?, 1, datetime('now'))
            """, (file_path, searchable_text))
            conn.commit()
            conn.close()
            
            self.status_label.configure(text=f"Added: {os.path.basename(file_path)}")
            
            # Refresh current view
            self.load_view(self.current_view)
            
            # Open the file
            self.open_existing_file(file_path)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add file: {e}")

    def open_existing_file(self, file_path):
        """Open an existing tracked file"""
        try:
            # Ensure absolute path
            file_path = os.path.abspath(file_path)
            
            if not os.path.exists(file_path):
                messagebox.showerror("Error", "File not found on disk")
                return
            
            # Open file
            os.startfile(file_path)
            
            # Log session in background
            threading.Thread(
                target=self.process_file_session,
                args=(file_path,),
                daemon=True
            ).start()
            
            self.status_label.configure(text=f"Opened: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")

    def process_file_session(self, file_path):
        """Handle logging and waiting in background thread"""
        try:
            start_file_session(file_path)
            
            # Refresh UI
            self.after(0, lambda: self.load_view(self.current_view))
            
            # Wait for file close (approximate)
            time.sleep(10)
            end_file_session(file_path)
            
            # Refresh again
            self.after(0, lambda: self.load_view(self.current_view))
            
        except Exception as e:
            print(f"Session error: {e}")

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
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM files WHERE path = ?", (file_path,))
            conn.commit()
            conn.close()
            
            # Remove from semantic search
            if self.semantic_searcher:
                self.semantic_searcher.remove_file(file_path)
            
            # Refresh view
            self.load_view(self.current_view)
            
            self.status_label.configure(text=f"Removed: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove file: {e}")

    def refresh_clusters(self):
        """Refresh file clusters"""
        self.status_label.configure(text="Clustering files...")
        
        def do_cluster():
            try:
                run_filename_clustering()
                self.after(0, lambda: self.status_label.configure(text="Clustering complete"))
                self.after(0, lambda: self.load_view(self.current_view))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(text=f"Clustering error: {e}"))
        
        threading.Thread(target=do_cluster, daemon=True).start()

    def _ensure_clustering(self):
        """Run clustering on startup if needed"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE cluster_label IS NOT NULL")
            clustered_count = cur.fetchone()[0]
            conn.close()
            
            if clustered_count == 0:
                threading.Thread(target=lambda: run_filename_clustering(), daemon=True).start()
        except:
            pass

    def _ensure_semantic_searcher(self):
        """Lazily load SemanticSearch on first use"""
        if self.semantic_searcher is None:
            from ml.semantic_search import SemanticSearch
            self.semantic_searcher = SemanticSearch()
            self.semantic_searcher.load_files()
        return self.semantic_searcher


if __name__ == "__main__":
    print(f"USING DATABASE: {DB_PATH}")
    app = ModernFileManager()
    app.mainloop()
