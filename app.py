import customtkinter as ctk
from tkinter import filedialog
import os
import threading
import time
import sqlite3

from database import init_db
from logger import start_file_session, end_file_session
from ml.filename_cluster import run_filename_clustering

DB_PATH = os.path.join("data", "file_logs.db")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

init_db()

# Enhanced color scheme
COLORS = {
    "Study": "#4A90E2",        # Professional blue
    "Work": "#7ED321",         # Fresh green
    "Personal": "#F5A623",     # Warm orange
    None: "#2C3E50"            # Dark gray
}

# UI Styling Constants
BUTTON_COLOR = "#4A90E2"
DELETE_BUTTON_COLOR = "#E74C3C"
FRAME_COLOR = "#2C2C2C"
HEADER_FONT = ("Arial", 16, "bold")
BUTTON_FONT = ("Arial", 12, "bold")
BODY_FONT = ("Arial", 11)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("📁 Context Aware File Organizer")
        self.geometry("900x700")
        self.minsize(800, 600)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

        # Add tabs
        self.priority_tab = self.tabs.add("Priority View")
        self.cluster_tab = self.tabs.add("Grouped View")
        self.search_tab = self.tabs.add("Semantic Search")

        # Build each tab UI
        self.build_priority_tab()
        self.build_cluster_tab()
        self.build_search_tab()

        # Initialize semantic searcher lazily (will be loaded on first use)
        self.semantic_searcher = None
        
        # Run initial clustering if needed
        self._ensure_clustering()

    def _ensure_clustering(self):
        """Run clustering on startup if no files are clustered yet"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE cluster_label IS NOT NULL")
            clustered_count = cur.fetchone()[0]
            conn.close()
            
            if clustered_count == 0:
                # Run clustering in background on startup
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

    # ---------------- Priority View ----------------

    def build_priority_tab(self):
        # Header frame
        header_frame = ctk.CTkFrame(self.priority_tab, fg_color=FRAME_COLOR)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        title_lbl = ctk.CTkLabel(header_frame, text="📂 Priority View", font=HEADER_FONT)
        title_lbl.pack(side="left", padx=10, pady=10)
        
        self.open_btn = ctk.CTkButton(
            header_frame, text="➕ Open File", command=self.open_file,
            height=35, font=BUTTON_FONT, fg_color=BUTTON_COLOR)
        self.open_btn.pack(side="right", padx=10, pady=10)

        # Status bar
        self.status = ctk.CTkLabel(self.priority_tab, text="", text_color="#B0B0B0", font=BODY_FONT)
        self.status.pack(pady=5)
        
        # Divider
        divider = ctk.CTkFrame(self.priority_tab, fg_color="#3C3C3C", height=1)
        divider.pack(fill="x", pady=5)

        self.priority_frame = ctk.CTkScrollableFrame(self.priority_tab)
        self.priority_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.load_priority_files()

    def load_priority_files(self):
        # Clear frame properly by destroying all children
        try:
            for w in self.priority_frame.winfo_children():
                w.destroy()
        except:
            pass

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT path FROM files ORDER BY access_count DESC")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"Error loading priority files: {e}")
            rows = []

        if not rows:
            no_files_lbl = ctk.CTkLabel(self.priority_frame, text="No files tracked yet", text_color="#888888")
            no_files_lbl.pack(pady=20)
            return

        for (path,) in rows:
            file_frame = ctk.CTkFrame(self.priority_frame, fg_color=FRAME_COLOR, corner_radius=8)
            file_frame.pack(fill="x", pady=3, padx=5)
            
            btn = ctk.CTkButton(file_frame, text=f"📄 {os.path.basename(path)}", anchor="w",
                                command=lambda p=path: self.open_from_list(p),
                                font=BODY_FONT, height=40)
            btn.pack(side="left", fill="x", expand=True, padx=2)
            
            del_btn = ctk.CTkButton(file_frame, text="🗑️", width=40, height=40, 
                                   fg_color=DELETE_BUTTON_COLOR, hover_color="#C0392B",
                                   command=lambda p=path: self.delete_file(p), font=("Arial", 12))
            del_btn.pack(side="right", padx=2)

    # ---------------- Grouped View ----------------

    def build_cluster_tab(self):
        # Header frame
        header_frame = ctk.CTkFrame(self.cluster_tab, fg_color=FRAME_COLOR)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        title_lbl = ctk.CTkLabel(header_frame, text="🏷️  Grouped View", font=HEADER_FONT)
        title_lbl.pack(side="left", padx=10, pady=10)
        
        self.cluster_btn = ctk.CTkButton(
            header_frame, text="⚙️ Run Clustering", command=self.run_clustering,
            height=35, font=BUTTON_FONT, fg_color=BUTTON_COLOR)
        self.cluster_btn.pack(side="right", padx=10, pady=10)
        
        # Divider
        divider = ctk.CTkFrame(self.cluster_tab, fg_color="#3C3C3C", height=1)
        divider.pack(fill="x", pady=5)

        self.cluster_frame = ctk.CTkScrollableFrame(self.cluster_tab)
        self.cluster_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.load_cluster_files()

    def run_clustering(self):
        # Show loading state
        try:
            for w in self.cluster_frame.winfo_children():
                w.destroy()
        except:
            pass
        
        loading_lbl = ctk.CTkLabel(self.cluster_frame, text="Clustering in progress...")
        loading_lbl.pack(pady=10)
        
        # Run clustering in background thread
        threading.Thread(target=self._do_clustering, daemon=True).start()

    def _do_clustering(self):
        try:
            run_filename_clustering()
        except Exception as e:
            print(f"Clustering error: {e}")
        finally:
            # Update GUI on main thread
            self.after(0, self.load_cluster_files)

    def load_cluster_files(self):
        # Clear frame properly by destroying all children
        try:
            for w in self.cluster_frame.winfo_children():
                w.destroy()
        except:
            pass

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT path, cluster_label FROM files WHERE cluster_label IS NOT NULL ORDER BY cluster_label, path")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"Error loading cluster files: {e}")
            rows = []

        if not rows:
            no_cluster_lbl = ctk.CTkLabel(self.cluster_frame, text="⚠️ No clustered files. Click 'Run Clustering' to organize files.", 
                                         text_color="#888888", font=BODY_FONT)
            no_cluster_lbl.pack(pady=30)
            return

        # Group by cluster label
        clusters = {}
        for path, label in rows:
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(path)

        # Display clusters
        for label in sorted(clusters.keys()):
            # Cluster header
            header = ctk.CTkFrame(self.cluster_frame, fg_color=COLORS.get(label, FRAME_COLOR), corner_radius=8)
            header.pack(fill="x", pady=(10, 5), padx=5)
            
            header_text = ctk.CTkLabel(header, text=f"🏷️  {label} ({len(clusters[label])} files)", 
                                       font=("Arial", 13, "bold"), text_color="white")
            header_text.pack(side="left", padx=10, pady=8)

            # Files in cluster
            for path in clusters[label]:
                row = ctk.CTkFrame(self.cluster_frame, fg_color=FRAME_COLOR, corner_radius=6)
                row.pack(fill="x", pady=2, padx=10)

                name_lbl = ctk.CTkButton(row, text=f"  📄 {os.path.basename(path)}", anchor="w",
                                        command=lambda p=path: self.open_from_list(p), 
                                        font=BODY_FONT, height=38)
                name_lbl.pack(side="left", fill="x", expand=True, padx=2)
                
                del_btn = ctk.CTkButton(row, text="🗑️", width=38, height=38,
                                       fg_color=DELETE_BUTTON_COLOR, hover_color="#C0392B",
                                       command=lambda p=path: self.delete_file(p), font=("Arial", 12))
                del_btn.pack(side="right", padx=2)

    # ---------------- Semantic Search Tab ----------------

    def build_search_tab(self):
        self.search_frame = ctk.CTkFrame(self.search_tab)
        self.search_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header_lbl = ctk.CTkLabel(self.search_frame, text="🔍 Semantic Search", font=HEADER_FONT)
        header_lbl.pack(pady=(0, 15))
        
        # Search input frame
        search_input_frame = ctk.CTkFrame(self.search_frame, fg_color=FRAME_COLOR, corner_radius=8)
        search_input_frame.pack(fill="x", pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_input_frame, placeholder_text="Type to search documents...",
            height=40, font=("Arial", 12))
        self.search_entry.pack(fill="x", padx=10, pady=(10, 5))
        self.search_entry.bind("<Return>", lambda e: self.perform_search())

        self.search_btn = ctk.CTkButton(
            search_input_frame, text="🔎 Search", command=self.perform_search,
            height=40, font=BUTTON_FONT, fg_color=BUTTON_COLOR)
        self.search_btn.pack(fill="x", padx=10, pady=(5, 10))

        self.search_results_frame = ctk.CTkScrollableFrame(self.search_frame)
        self.search_results_frame.pack(
            fill="both", expand=True, padx=10, pady=10)

    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        # Clear results immediately to show loading state
        try:
            for w in self.search_results_frame.winfo_children():
                w.destroy()
        except:
            pass

        loading_lbl = ctk.CTkLabel(
            self.search_results_frame, text="Searching...")
        loading_lbl.pack(pady=10)

        # Run search in background thread to keep UI responsive
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query):
        try:
            searcher = self._ensure_semantic_searcher()
            results = searcher.search(query, top_k=20)

            # Special case: if query is exactly a file extension (pdf, txt, etc),
            # prioritize files with that extension
            query_lower = query.lower()
            if query_lower in ['pdf', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'csv']:
                # First get all results with lower threshold
                all_results = searcher.search(query, top_k=20)
                results = [r for r in all_results if r["score"] >= -0.05]
                
                # Boost scores for files matching the extension
                for r in results:
                    file_ext = os.path.splitext(r["path"])[1].lower().lstrip('.')
                    if file_ext == query_lower:
                        r["score"] += 1.0  # Boost matching extension to top
                
                # Re-sort by boosted scores
                results = sorted(results, key=lambda r: r["score"], reverse=True)
            else:
                # Normal search: filter by threshold
                threshold = 0.1
                results = [r for r in results if r["score"] >= threshold]

            # Schedule GUI update on main thread using after()
            self.after(0, self._update_search_results, results)
        except Exception as e:
            error_msg = str(e)
            print(f"Search error: {error_msg}")
            self.after(0, self._show_search_error, error_msg)

    def _update_search_results(self, results):
        """Update search results on main thread"""
        try:
            for w in self.search_results_frame.winfo_children():
                w.destroy()
        except:
            pass

        if not results:
            no_res_lbl = ctk.CTkLabel(
                self.search_results_frame, text="❌ No relevant results found.", 
                text_color="#888888", font=BODY_FONT)
            no_res_lbl.pack(pady=20)
            return

        # Results count
        count_lbl = ctk.CTkLabel(
            self.search_results_frame, text=f"✓ Found {len(results)} result(s)", 
            text_color="#7ED321", font=("Arial", 11, "bold"))
        count_lbl.pack(pady=(10, 5))
        
        # Results divider
        divider = ctk.CTkFrame(self.search_results_frame, fg_color="#3C3C3C", height=1)
        divider.pack(fill="x", pady=5)

        for result in results:
            path = result["path"]
            score = result["score"]
            try:
                # Create a frame for each file with open and delete buttons
                file_frame = ctk.CTkFrame(self.search_results_frame, fg_color=FRAME_COLOR, corner_radius=6)
                file_frame.pack(fill="x", pady=3, padx=5)
                
                # File info with score
                info_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
                info_frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)
                
                file_name = os.path.basename(path)
                btn = ctk.CTkButton(info_frame, text=f"📄 {file_name}",
                                    anchor="w", command=lambda p=path: self.open_from_list(p),
                                    font=BODY_FONT, height=38)
                btn.pack(fill="x")
                
                # Delete button
                del_btn = ctk.CTkButton(file_frame, text="🗑️", width=38, height=38,
                                       fg_color=DELETE_BUTTON_COLOR, hover_color="#C0392B",
                                       command=lambda p=path: self.delete_file(p), font=("Arial", 12))
                del_btn.pack(side="right", padx=5, pady=5)
            except Exception as e:
                print(f"Error creating button for {path}: {e}")

    def _show_search_error(self, error_msg):
        """Show error message on search"""
        try:
            for w in self.search_results_frame.winfo_children():
                w.destroy()
        except:
            pass
        
        error_lbl = ctk.CTkLabel(
            self.search_results_frame, text=f"Error: {error_msg}")
        error_lbl.pack(pady=10)

    # ---------------- File open logic ----------------

    def open_file(self):
        file_path = filedialog.askopenfilename()
        if not file_path:
            return

        self.status.configure(text=f"Opened: {file_path}")

        start_file_session(file_path)
        os.startfile(file_path)

        threading.Thread(target=self.wait_and_close,
                         args=(file_path,), daemon=True).start()

    def open_from_list(self, file_path):
        start_file_session(file_path)
        os.startfile(file_path)

        threading.Thread(target=self.wait_and_close,
                         args=(file_path,), daemon=True).start()

    def wait_and_close(self, file_path):
        # simple fixed sleep, replace with better logic if you want
        time.sleep(10)
        end_file_session(file_path)

    def delete_file(self, file_path):
        """Delete a file and remove it from database"""
        try:
            # Confirm deletion
            from tkinter import messagebox
            result = messagebox.askyesno(
                "Confirm Delete",
                f"Are you sure you want to delete:\n{os.path.basename(file_path)}?"
            )
            
            if not result:
                return
            
            # Delete from filesystem
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleted: {file_path}")
            
            # Remove from database
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM files WHERE path = ?", (file_path,))
            conn.commit()
            conn.close()
            
            # Refresh all views
            self.load_priority_files()
            self.load_cluster_files()
            
            # Show confirmation
            self.status.configure(text=f"Deleted: {os.path.basename(file_path)}")
            
        except Exception as e:
            error_msg = f"Error deleting file: {e}"
            print(error_msg)
            self.status.configure(text=error_msg)

        # Refresh all views after closing file
        self.load_priority_files()
        self.load_cluster_files()
        if self.semantic_searcher is not None:
            self.semantic_searcher.load_files()  # reload semantic index


if __name__ == "__main__":
    app = App()
    app.mainloop()
