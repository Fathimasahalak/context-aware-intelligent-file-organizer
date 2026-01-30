import customtkinter as ctk
from tkinter import filedialog
import os
import threading
import time
import sqlite3

from database import init_db
from logger import start_file_session, end_file_session
from ml.filename_cluster import run_filename_clustering
# Your SentenceTransformer-based class
from ml.semantic_search import SemanticSearch

DB_PATH = os.path.join("data", "file_logs.db")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

init_db()

COLORS = {
    "Study": "#028CFD",
    "Work": "#C8E6C9",
    "Personal": "#F8BBD0",
    None: "#EEEEEE"
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Context Aware File Organizer")
        self.geometry("700x600")

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

        # Initialize semantic searcher and build index
        self.semantic_searcher = SemanticSearch()
        self.semantic_searcher.load_files()

    # ---------------- Priority View ----------------

    def build_priority_tab(self):
        self.open_btn = ctk.CTkButton(
            self.priority_tab, text="Open File", command=self.open_file)
        self.open_btn.pack(pady=10)

        self.status = ctk.CTkLabel(self.priority_tab, text="")
        self.status.pack(pady=5)

        self.priority_frame = ctk.CTkScrollableFrame(self.priority_tab)
        self.priority_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.load_priority_files()

    def load_priority_files(self):
        for w in self.priority_frame.winfo_children():
            w.destroy()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT path FROM files ORDER BY access_count DESC")
        rows = cur.fetchall()
        conn.close()

        for (path,) in rows:
            btn = ctk.CTkButton(self.priority_frame, text=os.path.basename(path),
                                command=lambda p=path: self.open_from_list(p))
            btn.pack(fill="x", pady=2)

    # ---------------- Grouped View ----------------

    def build_cluster_tab(self):
        self.cluster_btn = ctk.CTkButton(
            self.cluster_tab, text="Run Clustering", command=self.run_clustering)
        self.cluster_btn.pack(pady=10)

        self.cluster_frame = ctk.CTkScrollableFrame(self.cluster_tab)
        self.cluster_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.load_cluster_files()

    def run_clustering(self):
        run_filename_clustering()
        self.load_cluster_files()

    def load_cluster_files(self):
        for w in self.cluster_frame.winfo_children():
            w.destroy()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT path, cluster_label FROM files")
        rows = cur.fetchall()
        conn.close()

        for path, label in rows:
            color = COLORS.get(label, "#EEEEEE")

            row = ctk.CTkFrame(self.cluster_frame, fg_color=color)
            row.pack(fill="x", pady=3, padx=3)

            name_lbl = ctk.CTkLabel(row, text=os.path.basename(path))
            name_lbl.pack(side="left", padx=10)

            tag_lbl = ctk.CTkLabel(row, text=label if label else "Unclustered")
            tag_lbl.pack(side="right", padx=10)

            row.bind("<Button-1>", lambda e, p=path: self.open_from_list(p))

    # ---------------- Semantic Search Tab ----------------

    def build_search_tab(self):
        self.search_frame = ctk.CTkFrame(self.search_tab)
        self.search_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.search_entry = ctk.CTkEntry(
            self.search_frame, placeholder_text="Enter search query...")
        self.search_entry.pack(fill="x", padx=10, pady=10)

        self.search_btn = ctk.CTkButton(
            self.search_frame, text="Search", command=self.perform_search)
        self.search_btn.pack(pady=5)

        self.search_results_frame = ctk.CTkScrollableFrame(self.search_frame)
        self.search_results_frame.pack(
            fill="both", expand=True, padx=10, pady=10)

    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        results = self.semantic_searcher.search(query, top_k=20)

        # Clear previous results
        for w in self.search_results_frame.winfo_children():
            w.destroy()

        if not results:
            no_res_lbl = ctk.CTkLabel(
                self.search_results_frame, text="No results found.")
            no_res_lbl.pack(pady=10)
            return

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        for result in results:
            fid = result["file_id"]
            score = result["score"]
            cur.execute("SELECT path FROM files WHERE id = ?", (fid,))
            row = cur.fetchone()
            if row:
                path = row[0]
                btn_text = f"{os.path.basename(path)} (Score: {score:.2f})"
                btn = ctk.CTkButton(self.search_results_frame, text=btn_text, anchor="w",
                                    command=lambda p=path: self.open_from_list(p))
                btn.pack(fill="x", pady=2)

        conn.close()

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

        # Refresh all views after closing file
        self.load_priority_files()
        self.load_cluster_files()
        self.semantic_searcher.load_files()  # reload semantic index


if __name__ == "__main__":
    app = App()
    app.mainloop()
