import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import sqlite3
from datetime import datetime
import logging

# Local imports
from database import init_db, get_connection
from logger import start_file_session, end_file_session, remove_file_session
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
        
        # Start smart background indexing
        threading.Thread(target=self._smart_background_sync, daemon=True).start()

    def _setup_shortcuts(self):
        """Setup application-wide keyboard shortcuts"""
        self.bind('<Control-o>', lambda e: self.open_file())
        self.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.bind('<Delete>', lambda e: self.delete_selected_files())

    def _check_tesseract(self):
        """Check if Tesseract is available and log status"""
        from text_extractor import is_tesseract_available
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
        logging.info(f"Loading view {view_name}")
        self.file_list.clear()
        
        if view_name == "smart":
            self.load_smart_priority()
        elif view_name == "clusters":
            self.load_clusters()
        elif view_name == "all":
            self.load_all_files()

    def load_smart_priority(self):
        """Load smart priority files"""
        self.file_list.show_loading_state("Loading smart priority...")
        threading.Thread(target=self._load_smart_priority_async, daemon=True).start()
    
    def _load_smart_priority_async(self):
        """Load smart priority in background"""
        try:
            files = get_smart_priority_files(limit=50)
            self.after(0, self._display_smart_priority, files)
        except Exception as e:
            logging.error(f"Error loading smart priority: {e}")
            self.after(0, lambda: self.file_list.show_empty_state("Unable to load smart priority files."))
    
    def _display_smart_priority(self, files):
        """Display smart priority files on main thread"""
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

    def load_clusters(self):
        """Load clustered files with smart auto-refresh"""
        if self.needs_cluster_refresh:
            self._refresh_clusters()
        else:
            self.file_list.show_loading_state("Loading categories...")
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
            self.after(0, lambda: self.file_list.show_empty_state("Unable to load file categories."))
    
    def _display_clusters(self, clusters):
        """Display clusters on main thread"""
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

    def load_all_files(self):
        """Load all files"""
        self.file_list.show_loading_state("Loading all files...")
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
            self.after(0, lambda: self.file_list.show_empty_state("Unable to load all files."))
    
    def _display_all_files(self, rows):
        """Display all files on main thread"""
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
        
        self.file_list.clear()
        self.status_label.configure(text="Searching...")
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query):
        """Perform search in background with strict relevance filtering"""
        try:
            searcher = self._ensure_semantic_searcher()
            query_lower = query.lower()
            
            conn = get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, path, searchable_text FROM files 
                WHERE lower(path) LIKE ? 
                OR lower(searchable_text) LIKE ?
            """, ('%' + query_lower + '%', '%' + query_lower + '%'))
            keyword_rows = cur.fetchall()
            conn.close()
            
            semantic_results = searcher.search(query, top_k=15)
            all_results_dict = {}
            import re
            
            # Process Keywords
            for row in keyword_rows:
                fid, path, body_text = row
                basename = os.path.basename(path).lower()
                ext = os.path.splitext(basename)[1].lower()
                
                if len(query_lower) <= 3:
                    found_as_word = False
                    # Treat underscores and word boundaries as separators
                    pattern = r'(?:\b|_)' + re.escape(query_lower) + r'(?:\b|_)'
                    if re.search(pattern, basename):
                        found_as_word = True
                    elif body_text and re.search(pattern, body_text.lower()):
                        found_as_word = True
                    if not found_as_word:
                        continue

                score = 0.4
                if query_lower in basename:
                    score = 0.8
                    if query_lower == basename or query_lower == os.path.splitext(basename)[0]:
                        score = 1.0
                    pattern = r'(?:\b|_)' + re.escape(query_lower) + r'(?:\b|_)'
                    if re.search(pattern, basename):
                        score = max(score, 0.95)
                elif query_lower == ext[1:] or (query_lower.startswith('.') and query_lower == ext):
                    score = 0.9
                
                all_results_dict[path] = {"file_id": fid, "path": path, "score": score}
            
            # Process AI Results
            base_threshold = 0.45 if len(query_lower) > 3 else 0.6
            for r in semantic_results:
                path = r["path"]
                ai_score = r["score"]
                if ai_score >= base_threshold:
                    if path in all_results_dict:
                        all_results_dict[path]["score"] = max(all_results_dict[path]["score"], ai_score)
                    else:
                        all_results_dict[path] = {
                            "file_id": r["file_id"], "path": path, "score": ai_score * 0.85
                        }
            
            results = list(all_results_dict.values())
            results.sort(key=lambda x: x['score'], reverse=True)
            self.after(0, self._update_search_results, results[:20])
            
        except Exception as e:
            logging.error(f"Search error: {e}")
            self.after(0, lambda: self.status_label.configure(text="Search failed."))

    def _update_search_results(self, results):
        """Update search results on main thread"""
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
            from text_extractor import get_searchable_text
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
        """Show right-click context menu for a file"""
        if self.active_context_menu and self.active_context_menu.winfo_exists():
            self.active_context_menu.destroy()
            
        menu = ctk.CTkToplevel(self)
        self.active_context_menu = menu
        menu.overrideredirect(True)
        menu.geometry(f"+{x}+{y}")
        menu.configure(fg_color=SURFACE_CONTAINER)
        
        menu_items = [
            ("📄 Open File", lambda: self.open_existing_file(file_path)),
            ("📁 Open Folder", lambda: self.open_containing_folder(file_path)),
            ("───", None),
            ("🔄 Refresh This File", lambda: self.reindex_single_file(file_path)),
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
                    menu, text=text,
                    command=lambda cmd=command, m=menu: (cmd(), m.destroy()),
                    fg_color="transparent", hover_color=SURFACE_CONTAINER_HIGH,
                    anchor="w", height=30, font=BODY_FONT
                )
                btn.pack(fill="x", padx=5, pady=1)
        
        menu.bind("<FocusOut>", lambda e: menu.destroy())
        menu.focus_set()
        menu.grab_set()

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
                self.load_view(self.current_view)
                self.status_label.configure(text=f"Removed: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove file: {e}")

    def delete_selected_files(self):
        """Delete all selected files (batch operation)"""
        if not self.selected_files:
            return
        
        if not messagebox.askyesno("Confirm Batch Remove", f"Remove {len(self.selected_files)} files from the app?"):
            return
        
        deleted_count = 0
        for file_path in list(self.selected_files):
            try:
                conn = get_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute("DELETE FROM files WHERE lower(path) = lower(?)", (file_path,))
                if cur.rowcount > 0:
                    deleted_count += 1
                    if self.semantic_searcher:
                        self.semantic_searcher.remove_file(file_path)
                    remove_file_session(file_path)
                conn.commit()
                conn.close()
            except Exception as e:
                logging.error(f"Failed to delete {file_path}: {e}")
        
        if deleted_count > 0:
            self.needs_cluster_refresh = True
            self.selected_files.clear()
            self.load_view(self.current_view)
            self.status_label.configure(text=f"Removed {deleted_count} files")

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
            conn.close()
        except Exception as e:
            logging.error(f"Smart sync failed: {e}")

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
