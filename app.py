import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import sys
import threading
import time
import sqlite3
from datetime import datetime
import logging

# Local imports
from core.database import init_db, get_connection
from core.logger import start_file_session, end_file_session, remove_file_session
from ml.filename_cluster import run_filename_clustering
from ml.recommendation import get_smart_priority_files
from config import DB_PATH
from theme import *
from utils.path_utils import open_path, normalize_path

# Components
from components.sidebar import Sidebar
from components.toolbar import Toolbar
from components.file_list import FileList

# Configure logging to logs directory
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    filename=os.path.join('logs', 'file_organizer.log')
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

try:
    init_db()
except Exception as e:
    logging.error(f"Failed to initialize database: {e}")
    import sys
    sys.exit(1)

class ModernFileManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("📁 FileSense")
        self.geometry("1200x750")
        self.minsize(1000, 600)

        # State
        self.current_view = "smart"  # smart, clusters, all
        self.selected_files = set()  # Multi-select support
        self.semantic_searcher = None
        self.needs_cluster_refresh = False
        self.active_context_menu = None
        self.view_request_id = 0
        self.drag_data = {"path": None, "ghost": None}
        self._search_timer = None # For debouncing

        # UI Components placeholders
        self.sidebar = None
        self.toolbar = None
        self.file_list = None
        self.status_label = None
        self.file_count_label = None
        self.search_entry = None

        # Build UI
        self.build_ui()
        
        # Load initial data
        self.switch_view("smart")
        
        # Shortcuts
        self._setup_shortcuts()
        
        # Check for Tesseract
        self._check_tesseract()
        
        # Run clustering if needed
        self._ensure_clustering()
        
        # Handle clean exit
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start smart background indexing
        threading.Thread(target=self._smart_background_sync, daemon=True).start()

    def on_closing(self):
        """Ensure the application and all threads exit cleanly"""
        logging.info("Closing application...")
        try:
            self.withdraw()
            self.quit()
            self.destroy()
        except:
            pass
        finally:
            os._exit(0)

    def _setup_shortcuts(self):
        """Setup application-wide keyboard shortcuts"""
        self.bind('<Control-o>', lambda e: self.open_file())
        self.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.bind('<Delete>', lambda e: self.delete_selected_files())

    def _check_tesseract(self):
        """Check if Tesseract is available and log status"""
        from core.text_extractor import is_tesseract_available
        if not is_tesseract_available():
            logging.info("Tesseract OCR not found. Image text extraction is disabled.")

        logging.info("Application started")

    def build_ui(self):
        """Build the modern file manager UI using components"""
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color=SURFACE)
        main_container.pack(fill="both", expand=True)
        
        # 1. Sidebar
        self.sidebar = Sidebar(main_container, self)
        
        # Content area
        content_frame = ctk.CTkFrame(main_container, fg_color=SURFACE)
        content_frame.pack(side="left", fill="both", expand=True)
        
        # 2. Toolbar
        self.toolbar = Toolbar(content_frame, self)
        
        # 3. File List
        self.file_list = FileList(content_frame, self)
        
        # 4. Status Bar
        self.build_status_bar(content_frame)

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
        
        # Update component styles
        self.sidebar.update_selection(view_name)
        
        titles = {
            "smart": "⭐ Smart Priority",
            "clusters": "📂 Categories",
            "all": "📋 All Files"
        }
        self.toolbar.update_title(titles.get(view_name, "Files"))
        
        # Load view data
        self.load_view(view_name)

    def load_view(self, view_name):
        """Load data for the selected view"""
        self.view_request_id += 1
        request_id = self.view_request_id
        
        logging.info(f"Loading view {view_name} (req: {request_id})")
        self.file_list.clear()
        self.selected_files.clear() # Clear selection when switching views
        
        if view_name == "smart":
            self.load_smart_priority(request_id)
        elif view_name == "clusters":
            self.load_clusters(request_id)
        elif view_name == "all":
            self.load_all_files(request_id)

    def load_smart_priority(self, request_id):
        """Load smart priority files"""
        self.file_list.show_loading_state("Loading smart priority...")
        threading.Thread(target=self._load_smart_priority_async, args=(request_id,), daemon=True).start()
    
    def _load_smart_priority_async(self, request_id):
        """Load smart priority in background"""
        try:
            files = get_smart_priority_files(limit=50)
            self.after(0, self._display_smart_priority, files, request_id)
        except Exception as e:
            logging.error(f"Error loading smart priority: {e}")
            if self.view_request_id == request_id:
                self.after(0, lambda: self.file_list.show_empty_state("Unable to load smart priority files."))
    
    def _display_smart_priority(self, files, request_id):
        """Display smart priority files on main thread"""
        if self.view_request_id != request_id:
            return
            
        self.file_list.clear()
        
        if not files:
            self.file_list.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        added_paths = set()
        for file_data in files:
            norm_path = normalize_path(file_data["path"])
            if norm_path not in added_paths:
                self.file_list.create_file_row(file_data, file_data.get("last_opened"))
                added_paths.add(norm_path)
        
        self.file_count_label.configure(text=f"{len(added_paths)} files")
        self.status_label.configure(text="Smart priority loaded")

    def load_clusters(self, request_id):
        """Load clustered files with smart auto-refresh"""
        if self.needs_cluster_refresh:
            self._refresh_clusters()
        else:
            self.file_list.show_loading_state("Loading categories...")
            threading.Thread(target=self._load_clusters_async, args=(request_id,), daemon=True).start()
    
    def _load_clusters_async(self, request_id):
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
            self.after(0, self._display_clusters, clusters, request_id)
        except Exception as e:
            logging.error(f"Error loading clusters: {e}")
            if self.view_request_id == request_id:
                self.after(0, lambda: self.file_list.show_empty_state("Unable to load file categories."))
    
    def _display_clusters(self, clusters, request_id):
        """Display clusters on main thread"""
        if self.view_request_id != request_id:
            return
            
        self.file_list.clear()
        
        if not clusters:
            self.file_list.show_empty_state("No clusters yet. Click 'Categories' to organize your files!")
            return
        
        added_paths = set()
        for cluster_label, count in clusters:
            self.file_list.create_cluster_section(cluster_label, count, added_paths)
        
        total_files = len(added_paths)
        self.file_count_label.configure(text=f"{total_files} files in {len(clusters)} categories")
        self.status_label.configure(text="Categories loaded")

    def load_all_files(self, request_id):
        """Load all files"""
        self.file_list.show_loading_state("Loading all files...")
        threading.Thread(target=self._load_all_files_async, args=(request_id,), daemon=True).start()
    
    def _load_all_files_async(self, request_id):
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
            self.after(0, self._display_all_files, rows, request_id)
        except Exception as e:
            logging.error(f"Error loading files: {e}")
            if self.view_request_id == request_id:
                self.after(0, lambda: self.file_list.show_empty_state("Unable to load all files."))
    
    def _display_all_files(self, rows, request_id):
        """Display all files on main thread"""
        if self.view_request_id != request_id:
            return
            
        self.file_list.clear()
        
        if not rows:
            self.file_list.show_empty_state("No files tracked yet. Add some files to get started!")
            return
        
        added_paths = set()
        for path, count, last_opened in rows:
            norm_path = normalize_path(path)
            if norm_path not in added_paths:
                file_data = {
                    "path": path,
                    "score": count / 10.0,
                    "reasons": {"Freq": str(count)}
                }
                self.file_list.create_file_row(file_data, last_opened)
                added_paths.add(norm_path)
        
        self.file_count_label.configure(text=f"{len(added_paths)} files")
        self.status_label.configure(text="All files loaded")

    def perform_search(self):
        """Perform semantic search"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        if len(query) > 500:
            query = query[:500]
            messagebox.showinfo("Info", "Search query was truncated to 500 characters.")
        
        self.view_request_id += 1
        request_id = self.view_request_id
        
        self.file_list.clear()
        self.status_label.configure(text="Searching...")
        threading.Thread(target=self._do_search, args=(query, request_id), daemon=True).start()

    def _do_search(self, query, request_id):
        """Perform search in background with query expansion and improved AI thresholds"""
        try:
            searcher = self._ensure_semantic_searcher()
            query_lower = query.lower()
            
            # --- 1. Query Expansion (Improve recall for specific domains) ---
            expanded_queries = [query]
            synonym_map = {
                "cv": ["resume", "portfolio", "biodata", "curriculum vitae", "profile"],
                "resume": ["cv", "biodata", "curriculum vitae", "work history"],
                "biodata": ["cv", "resume", "personal info", "profile"],
                "portfolio": ["projects", "samples", "work", "gallery", "cv"],
                "image": ["photo", "picture", "screenshot", "img", "gallery"],
                "money": ["budget", "salary", "expense", "financial", "report"],
                "schedule": ["timetable", "plan", "calendar", "agenda"],
                "school": ["university", "college", "course", "exam", "notes"],
                "work": ["office", "job", "business", "company", "project"]
            }
            
            # Check if query is or contains any of our expansion keywords
            for word, synonyms in synonym_map.items():
                if word == query_lower or (f" {word} " in f" {query_lower} "):
                    expanded_queries.extend(synonyms)
                    break
            
            # Limit number of queries to keep it fast
            expanded_queries = list(set(expanded_queries))[:5]
            
            # --- 2. Keyword Search (Original query only for exact match) ---
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, path, searchable_text FROM files 
                WHERE lower(path) LIKE ? 
                OR lower(searchable_text) LIKE ?
            """, ('%' + query_lower + '%', '%' + query_lower + '%'))
            keyword_rows = cur.fetchall()
            conn.close()
            
            all_results_dict = {}
            import re
            
            # Process Keywords
            for row in keyword_rows:
                fid, path, body_text = row
                basename = os.path.basename(path).lower()
                ext = os.path.splitext(basename)[1].lower()
                
                score = 0.4
                if query_lower in basename:
                    score = 0.8
                    if query_lower == basename or query_lower == os.path.splitext(basename)[0]:
                        score = 1.0
                elif query_lower == ext[1:] or (query_lower.startswith('.') and query_lower == ext):
                    score = 0.9
                
                all_results_dict[path] = {"file_id": fid, "path": path, "score": score}
            
            # --- 3. Multi-Query Semantic Search (Expansion) ---
            # Threshold: Adjusted for a balance of flexibility and precision
            base_threshold = 0.35 if len(query_lower) > 3 else 0.5
            
            for q in expanded_queries:
                semantic_results = searcher.search(q, top_k=15)
                
                # Queries that are expansions get a slight penalty to avoid noise
                expansion_multiplier = 1.0 if q == query else 0.9
                
                for r in semantic_results:
                    path = r["path"]
                    ai_score = r["score"] * expansion_multiplier
                    
                    if ai_score >= base_threshold:
                        if path in all_results_dict:
                            # If we have both keyword and AI, the AI can boost the score
                            all_results_dict[path]["score"] = max(all_results_dict[path]["score"], ai_score)
                        else:
                            all_results_dict[path] = {
                                "file_id": r["file_id"], "path": path, "score": ai_score
                            }
            
            results = list(all_results_dict.values())
            results.sort(key=lambda x: x['score'], reverse=True)
            self.after(0, self._update_search_results, results[:25], request_id)
            
        except Exception as e:
            logging.error(f"Search error: {e}")
            if self.view_request_id == request_id:
                self.after(0, lambda: self.status_label.configure(text="Search failed."))

    def _update_search_results(self, results, request_id):
        """Update search results on main thread"""
        if self.view_request_id != request_id:
            return
            
        self.file_list.clear()
        
        if not results:
            self.file_list.show_empty_state("No results found")
            self.status_label.configure(text="No results")
            return
        
        seen = set()
        for result in results:
            norm_path = normalize_path(result["path"])
            if norm_path not in seen:
                file_data = {"path": result["path"], "score": result["score"], "reasons": {}}
                self.file_list.create_file_row(file_data)
                seen.add(norm_path)
        
        self.file_count_label.configure(text=f"{len(seen)} results")
        self.status_label.configure(text=f"Found {len(seen)} results")

    def open_file(self):
        """Open file dialog to add a file"""
        file_path = filedialog.askopenfilename(title="Select a file to track")
        if not file_path:
            return
        
        file_path = normalize_path(file_path)
        self.sidebar.add_btn.configure(state="disabled")
        
        if not os.path.exists(file_path):
            messagebox.showerror("Error", "Selected file does not exist.")
            self.sidebar.add_btn.configure(state="normal")
            return
        
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM files WHERE lower(path) = lower(?)", (file_path,))
        if cur.fetchone():
            messagebox.showinfo("Info", "This file is already added.")
            conn.close()
            self.sidebar.add_btn.configure(state="normal")
            return
        conn.close()
        
        self.status_label.configure(text=f"Adding {os.path.basename(file_path)}...")
        threading.Thread(target=self._add_file_async, args=(file_path,), daemon=True).start()

    def _add_file_async(self, file_path):
        """Add file processing in background"""
        try:
            from core.text_extractor import get_searchable_text
            searchable_text = get_searchable_text(file_path)
            
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO files(path, searchable_text, access_count, last_opened)
                VALUES (?, ?, 1, datetime('now'))
            """, (file_path, searchable_text))
            conn.commit()
            conn.close()
            
            self.after(0, self._on_file_added_success, file_path)
        except Exception as e:
            logging.error(f"Failed to add file: {e}")
            self.after(0, lambda err=e: messagebox.showerror("Error", f"Failed to add file: {err}"))
            self.after(0, lambda: self.sidebar.add_btn.configure(state="normal"))

    def _on_file_added_success(self, file_path):
        """Callback for successful file addition"""
        self.status_label.configure(text=f"Added: {os.path.basename(file_path)}")
        self.sidebar.add_btn.configure(state="normal")
        self.needs_cluster_refresh = True
        
        if self.semantic_searcher:
            threading.Thread(target=self.semantic_searcher.load_files, daemon=True).start()
        
        self.load_view(self.current_view)

    def open_existing_file(self, file_path):
        """Open an existing tracked file"""
        try:
            file_path = normalize_path(file_path)
            if not os.path.exists(file_path):
                messagebox.showerror("Error", f"File not found on disk:\n{file_path}")
                return
            
            open_path(file_path)
            threading.Thread(target=self.process_file_session, args=(file_path,), daemon=True).start()
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
        """Show right-click context menu with aligned icons"""
        if self.active_context_menu and self.active_context_menu.winfo_exists():
            self.active_context_menu.destroy()
            
        menu = ctk.CTkToplevel(self)
        self.active_context_menu = menu
        menu.overrideredirect(True)
        menu.withdraw() # Hide until positioned to avoid flicker
        menu.configure(fg_color=SURFACE_CONTAINER)
        
        menu_items = [
            ("📄", "Open File", lambda: self.open_existing_file(file_path)),
            ("📁", "Open Folder", lambda: self.open_containing_folder(file_path)),
            ("───", "", None),
            ("🏷️", "Move to Category", lambda: self.move_to_category_dialog(file_path)),
            ("🔄", "Refresh This File", lambda: self.reindex_single_file(file_path)),
            ("📋", "Copy Path", lambda: self.copy_file_path(file_path)),
            ("───", "", None),
            ("🗑️", "Remove from App", lambda: self.delete_file(file_path)),
        ]
        
        for icon, text, command in menu_items:
            if icon == "───":
                separator = ctk.CTkFrame(menu, height=1, fg_color=OUTLINE)
                separator.pack(fill="x", padx=10, pady=4)
            else:
                btn = ctk.CTkButton(
                    menu, text=f"{icon}   {text}",
                    command=lambda cmd=command, m=menu: (cmd(), m.destroy()),
                    fg_color="transparent", hover_color=SURFACE_CONTAINER_HIGH,
                    anchor="w", height=34, font=BODY_FONT, padx=15
                )
                btn.pack(fill="x", padx=2, pady=1)
        
        # Focus handling to prevent glitches
        menu.bind("<FocusOut>", lambda e: self.after(100, lambda: self._check_menu_focus(menu)))
        menu.attributes("-topmost", True)
        
        # Position and show
        self.after(10, lambda: self._position_menu(menu, x, y))

    def _check_menu_focus(self, menu):
        """Close menu if focus is lost to another window"""
        if not menu.winfo_exists(): return
        focus = self.focus_get()
        if focus is None or not str(focus).startswith(str(menu)):
            menu.destroy()
            if self.active_context_menu == menu:
                self.active_context_menu = None

    def _position_menu(self, menu, x, y):
        """Position menu within screen bounds and show it"""
        if not menu.winfo_exists(): return
        menu.update_idletasks()
        w, h = menu.winfo_width(), menu.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        
        # Adjust if off-screen
        if x + w > sw: x = sw - w - 10
        if y + h > sh: y = sh - h - 10
        if x < 0: x = 10
        if y < 0: y = 10
        
        menu.geometry(f"+{x}+{y}")
        menu.deiconify()
        menu.focus_set()

    def _center_dialog(self, dialog):
        """Center a ctk dialog on the main window"""
        self.update_idletasks()
        
        # Approximate size of CTkInputDialog
        d_width = 400
        d_height = 200
        
        # Main window dimensions
        m_width = self.winfo_width()
        m_height = self.winfo_height()
        m_x = self.winfo_x()
        m_y = self.winfo_y()
        
        # Calculate center
        x = m_x + (m_width // 2) - (d_width // 2)
        y = m_y + (m_height // 2) - (d_height // 2)
        
        dialog.geometry(f"{d_width}x{d_height}+{x}+{y}")

    def rename_cluster_dialog(self, old_label):
        """Show dialog to rename a cluster"""
        dialog = ctk.CTkInputDialog(text=f"Rename category '{old_label}' to:", title="Rename Category")
        self._center_dialog(dialog)
        new_label = dialog.get_input()
        if new_label and new_label != old_label:
            self.rename_cluster(old_label, new_label)

    def rename_cluster(self, old_label, new_label):
        """Rename a cluster and learn from it"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            
            # 1. Update all files with this label
            cur.execute("""
                UPDATE files 
                SET cluster_label = ?, is_manual_label = 1 
                WHERE cluster_label = ?
            """, (new_label, old_label))
            
            # 2. Add to user_categories for learning
            cur.execute("INSERT OR IGNORE INTO user_categories (name) VALUES (?)", (new_label,))
            
            # 3. Trigger fingerprint update in background
            from ml.filename_cluster import update_category_fingerprint
            threading.Thread(target=update_category_fingerprint, args=(new_label,), daemon=True).start()
            
            conn.commit()
            conn.close()
            
            self.status_label.configure(text=f"Renamed '{old_label}' to '{new_label}'")
            self.switch_view("clusters") # Refresh view
        except Exception as e:
            logging.error(f"Failed to rename cluster: {e}")
            messagebox.showerror("Error", f"Failed to rename: {e}")

    def move_to_category_dialog(self, file_path):
        """Show dialog to move a file to a different category"""
        # Get existing categories
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT cluster_label FROM files WHERE cluster_label IS NOT NULL")
        existing_categories = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT name FROM user_categories")
        user_cats = [row[0] for row in cur.fetchall()]
        conn.close()
        
        all_categories = sorted(list(set(existing_categories + user_cats)))
        
        # Simple input dialog for now (can be improved to a dropdown)
        dialog = ctk.CTkInputDialog(text="Enter category name:", title="Move to Category")
        self._center_dialog(dialog)
        category_name = dialog.get_input()
        
        if category_name:
            self.move_file_to_category(file_path, category_name)

    def move_file_to_category(self, file_path, category_name):
        """Move a file to a category and learn from it"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            
            # 1. Get file ID
            cur.execute("SELECT id FROM files WHERE path = ?", (file_path,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return
            file_id = row[0]
            
            # 2. Update file
            cur.execute("""
                UPDATE files 
                SET cluster_label = ?, is_manual_label = 1 
                WHERE id = ?
            """, (category_name, file_id))
            
            # 3. Log history
            from datetime import datetime
            cur.execute("""
                INSERT INTO category_history (file_id, category_name, timestamp)
                VALUES (?, ?, ?)
            """, (file_id, category_name, datetime.now().isoformat()))
            
            # 4. Ensure category exists in user_categories
            cur.execute("INSERT OR IGNORE INTO user_categories (name) VALUES (?)", (category_name,))
            
            # 5. Trigger fingerprint update
            from ml.filename_cluster import update_category_fingerprint
            threading.Thread(target=update_category_fingerprint, args=(category_name,), daemon=True).start()
            
            conn.commit()
            conn.close()
            
            logging.info(f"Successfully moved file {file_id} to category '{category_name}'")
            messagebox.showinfo("Success", f"File moved to '{category_name}'")
            
            self.status_label.configure(text=f"Moved to '{category_name}'")
            if self.current_view == "clusters":
                self.switch_view("clusters")
        except Exception as e:
            logging.error(f"Failed to move file: {e}")
            messagebox.showerror("Error", f"Failed to move: {e}")

    def copy_file_path(self, file_path):
        """Copy file path to clipboard"""
        self.clipboard_clear()
        self.clipboard_append(file_path)
        self.status_label.configure(text="Path copied to clipboard")

    def process_file_session(self, file_path):
        """Handle logging session in background and perform smart repair if needed"""
        try:
            # 1. Log the session
            from logger import start_file_session, end_file_session
            start_file_session(file_path)
            
            # 2. Smart Repair check: if file is a doc but has no content indexed, fix it now
            ext = os.path.splitext(file_path.lower())[1]
            if ext in ['.docx', '.xlsx', '.pdf', '.pptx']:
                conn = get_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT searchable_text FROM files WHERE path = ?", (file_path,))
                row = cur.fetchone()
                # If text is very short (just filename), it might be from an old version
                if row and (not row[0] or len(row[0]) < 50):
                    logging.info(f"Smart Repair: On-access indexing for {os.path.basename(file_path)}")
                    from text_extractor import get_searchable_text
                    text = get_searchable_text(file_path)
                    cur.execute("UPDATE files SET searchable_text = ? WHERE path = ?", (text, file_path))
                    conn.commit()
                    self.needs_cluster_refresh = True
                    if self.semantic_searcher:
                        self.semantic_searcher.load_files()
                conn.close()

            time.sleep(10)
            end_file_session(file_path)
        except Exception as e:
            logging.error(f"Session error: {e}")

    def delete_file(self, file_path):
        """Delete file from tracking"""
        try:
            if not messagebox.askyesno("Confirm Remove", f"Remove this file from the app?\n\n{os.path.basename(file_path)}"):
                return
            
            file_path = normalize_path(file_path)
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM files WHERE lower(path) = lower(?)", (file_path,))
            deleted_count = cur.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                self.needs_cluster_refresh = True
                if self.semantic_searcher:
                    self.semantic_searcher.remove_file(file_path)
                remove_file_session(file_path)
                
                # Fix selection ghosting
                if file_path in self.selected_files:
                    self.selected_files.remove(file_path)
                
                self.load_view(self.current_view)
                self.status_label.configure(text=f"Removed: {os.path.basename(file_path)}")
        except Exception as e:
            logging.error(f"Failed to remove file: {e}")
            messagebox.showerror("Error", f"Failed to remove file: {e}")

    def delete_selected_files(self):
        """Delete all selected files (efficient batch operation)"""
        if not self.selected_files:
            return
        
        selected_list = list(self.selected_files)
        if not messagebox.askyesno("Confirm Batch Remove", f"Remove {len(selected_list)} files from the app?"):
            return
        
        self.status_label.configure(text=f"Removing {len(selected_list)} files...")
        
        def task():
            try:
                conn = get_connection(DB_PATH)
                cur = conn.cursor()
                deleted_count = 0
                
                # Use a single transaction for all deletions
                for file_path in selected_list:
                    cur.execute("DELETE FROM files WHERE lower(path) = lower(?)", (file_path,))
                    if cur.rowcount > 0:
                        deleted_count += 1
                        if self.semantic_searcher:
                            self.semantic_searcher.remove_file(file_path)
                        remove_file_session(file_path)
                
                conn.commit()
                conn.close()
                
                # Cleanup state on main thread
                self.after(0, self._on_batch_delete_complete, deleted_count)
            except Exception as e:
                logging.error(f"Batch delete failed: {e}")
                self.after(0, lambda: messagebox.showerror("Error", f"Batch delete failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_batch_delete_complete(self, count):
        """Callback after batch deletion finishes"""
        if count > 0:
            self.needs_cluster_refresh = True
            self.selected_files.clear()
            self.load_view(self.current_view)
            self.status_label.configure(text=f"Removed {count} files")
        else:
            self.status_label.configure(text="No files were removed")

    def _refresh_clusters(self):
        """Refresh file clusters"""
        self.file_list.show_loading_state("Clustering files...")
        def do_cluster():
            try:
                run_filename_clustering()
                self.needs_cluster_refresh = False
                self.after(0, lambda: self.status_label.configure(text="Clustering complete"))
                self.after(0, lambda: self.load_view(self.current_view))
            except Exception as e:
                logging.error(f"Clustering failed: {e}")
                self.after(0, lambda: self.status_label.configure(text="Clustering failed."))
        threading.Thread(target=do_cluster, daemon=True).start()

    def reindex_single_file(self, file_path):
        """Force re-index content for one file"""
        self.status_label.configure(text=f"Re-indexing {os.path.basename(file_path)}...")
        def task():
            try:
                from text_extractor import get_searchable_text
                text = get_searchable_text(file_path)
                conn = get_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute("UPDATE files SET searchable_text = ? WHERE path = ?", (text, file_path))
                conn.commit()
                conn.close()
                if self.semantic_searcher:
                    # Remove from cache first so load_files picks it up as an "addition"
                    self.semantic_searcher.remove_file(file_path)
                    self.semantic_searcher.load_files()
                self.after(0, lambda: self.status_label.configure(text="File re-indexed"))
                self.after(0, lambda: self.load_view(self.current_view))
            except Exception as e:
                logging.error(f"Re-indexing failed: {e}")
                self.after(0, lambda: self.status_label.configure(text="Re-indexing failed"))
        threading.Thread(target=task, daemon=True).start()

    def _smart_background_sync(self):
        """Quietly repair the search index for files that were added with old logic"""
        conn = None
        try:
            time.sleep(5) # Let app start first
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            # Find files where searchable_text is very short (just metadata) but the file is a doc
            cur.execute("""
                SELECT id, path FROM files 
                WHERE (length(searchable_text) < 50 OR searchable_text IS NULL)
                AND (path LIKE '%.docx' OR path LIKE '%.xlsx' OR path LIKE '%.pdf' OR path LIKE '%.pptx')
            """)
            stale_files = cur.fetchall()
            
            if stale_files:
                logging.info(f"Smart Sync: Repairing {len(stale_files)} index entries...")
                from text_extractor import get_searchable_text
                for fid, path in stale_files:
                    if os.path.exists(path):
                        text = get_searchable_text(path)
                        cur.execute("UPDATE files SET searchable_text = ? WHERE id = ?", (text, fid))
                        conn.commit()
                        if self.semantic_searcher:
                            self.semantic_searcher.remove_file(path)
                        time.sleep(0.5) # Don't hog CPU
                
                self.needs_cluster_refresh = True
                if self.semantic_searcher:
                    self.semantic_searcher.load_files()
        except Exception as e:
            logging.error(f"Smart sync failed: {e}")
        finally:
            if conn:
                conn.close()

    def _ensure_clustering(self):
        """Run clustering on startup if needed"""
        try:
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE cluster_label IS NULL")
            if cur.fetchone()[0] > 0:
                self.needs_cluster_refresh = True
            conn.close()
        except: pass

    def _ensure_semantic_searcher(self):
        """Lazily load SemanticSearcher"""
        if self.semantic_searcher is None:
            try:
                self.after(0, lambda: self.status_label.configure(text="Initializing AI Model..."))
                from ml.semantic_search import get_semantic_searcher
                self.semantic_searcher = get_semantic_searcher()
                self.after(0, lambda: self.status_label.configure(text="AI Model Ready"))
            except Exception as e:
                logging.error(f"Semantic search failed: {e}")
        return self.semantic_searcher

if __name__ == "__main__":
    app = ModernFileManager()
    app.mainloop()
