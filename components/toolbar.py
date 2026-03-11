import customtkinter as ctk
from theme import *

class Toolbar(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=SURFACE_CONTAINER, height=60, corner_radius=0)
        self.app = app
        self.pack(side="top", fill="x", padx=0, pady=0)
        self.pack_propagate(False)
        
        self.build()

    def build(self):
        """Build top toolbar"""
        # View title
        self.view_title = ctk.CTkLabel(
            self,
            text="⭐ Smart Priority",
            font=HEADER_FONT,
            text_color=TEXT_PRIMARY
        )
        self.view_title.pack(side="left", padx=20, pady=15)
        
        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
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
        self.search_entry.bind("<Return>", lambda e: self.app.perform_search())
        
        # Expose search_entry to app for logic access
        self.app.search_entry = self.search_entry
        
        search_btn = ctk.CTkButton(
            search_frame,
            text="Search",
            command=self.app.perform_search,
            width=80,
            height=35,
            font=BODY_FONT,
            fg_color=PRIMARY,
            text_color=ON_PRIMARY,
            hover_color=ON_PRIMARY_CONTAINER,
            corner_radius=RADIUS_LG
        )
        search_btn.pack(side="left")

    def update_title(self, title):
        self.view_title.configure(text=title)
