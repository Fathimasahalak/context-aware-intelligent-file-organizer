import customtkinter as ctk
import os
from theme import *
from database import get_connection
from config import DB_PATH
from datetime import datetime

class FileList(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=SURFACE)
        self.app = app
        self.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.build()

    def build(self):
        """Build file list area"""
        # Scrollable container for headers and rows
        self.scrollable_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=SURFACE,
            corner_radius=0
        )
        self.scrollable_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Column headers inside scrollable (tagged to preserve during clear)
        headers_frame = ctk.CTkFrame(self.scrollable_frame, fg_color=SURFACE_CONTAINER, height=40, corner_radius=0)
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

    def clear(self):
        """Clear all rows but keep headers"""
        for widget in self.scrollable_frame.winfo_children():
            if not getattr(widget, '_is_header', False):
                widget.destroy()

    def create_file_row(self, file_data, last_opened=None):
        """Create a file row in the list"""
        path = file_data["path"]
        
        # Determine selection color
        is_selected = path in self.app.selected_files
        fg_color = PRIMARY_CONTAINER if is_selected else "transparent"
        
        # File row container
        row = ctk.CTkFrame(
            self.scrollable_frame,
            fg_color=fg_color,
            height=50,
            corner_radius=RADIUS_SM
        )
        row.pack(fill="x", padx=10, pady=2)
        row.pack_propagate(False)
        row._path = path # Store path for easy access

        # Hover effect - preserve selection color
        def on_enter(e):
            if path not in self.app.selected_files:
                row.configure(fg_color=SURFACE_CONTAINER_HIGH)
        
        def on_leave(e):
            if path not in self.app.selected_files:
                row.configure(fg_color="transparent")
        
        # Click to select (with Ctrl for multi-select)
        def on_click(e):
            if e.state & 0x4:  # Ctrl key pressed
                if path in self.app.selected_files:
                    self.app.selected_files.remove(path)
                    row.configure(fg_color="transparent")
                else:
                    self.app.selected_files.add(path)
                    row.configure(fg_color=PRIMARY_CONTAINER)
            else:
                # Single select - Clear previous selections visually
                for child in self.scrollable_frame.winfo_children():
                    if hasattr(child, "_path"):
                        if child._path in self.app.selected_files:
                            child.configure(fg_color="transparent")
                
                self.app.selected_files.clear()
                self.app.selected_files.add(path)
                row.configure(fg_color=PRIMARY_CONTAINER)
        
        def on_right_click(e):
            self.app.show_context_menu(path, e.x_root, e.y_root)

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
        time_text = self.format_time(last_opened) if last_opened else "Recently"
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
            row, text="📁",
            command=lambda: self.app.open_containing_folder(path),
            width=30, height=30, fg_color="transparent",
            hover_color=SURFACE_CONTAINER_HIGH, font=BODY_FONT
        )
        folder_btn.place(relx=0.85, rely=0.5, anchor="w")
        
        # Delete button
        delete_btn = ctk.CTkButton(
            row, text="🗑️",
            command=lambda: self.app.delete_file(path),
            width=30, height=30, fg_color="transparent",
            hover_color=ERROR, font=BODY_FONT
        )
        delete_btn.place(relx=0.91, rely=0.5, anchor="w")

        # --- EVENT BINDINGS ---
        interactive_widgets = [row, name_label, type_label, time_label]
        
        for w in interactive_widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_right_click)
            w.bind("<Button-2>", on_right_click)
            
        # Double click to open
        row.bind("<Double-Button-1>", lambda e: self.app.open_existing_file(path))
        name_label.bind("<Double-Button-1>", lambda e: self.app.open_existing_file(path))

    def create_cluster_section(self, cluster_label, count, added_paths):
        """Create a cluster section"""
        # Cluster header
        header = ctk.CTkFrame(
            self.scrollable_frame,
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

        # Rename button
        rename_btn = ctk.CTkButton(
            header,
            text="✏️",
            command=lambda l=cluster_label: self.app.rename_cluster_dialog(l),
            width=30,
            height=30,
            fg_color="transparent",
            hover_color=SURFACE_CONTAINER_HIGH,
            font=BODY_FONT
        )
        rename_btn.pack(side="left", padx=5, pady=5)
        
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

    def format_time(self, timestamp_str):
        """Format timestamp to exact date and time"""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.strftime("%b %d, %Y %I:%M %p")
        except:
            return "Unknown"

    def show_empty_state(self, message):
        """Show empty state message with improved visual design"""
        empty_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
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
                command=self.app.open_file,
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
        self.clear()
        
        loading_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
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
        
        self.app.status_label.configure(text=message)
