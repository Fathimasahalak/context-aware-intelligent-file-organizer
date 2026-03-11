import customtkinter as ctk
from theme import *

class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=SURFACE_CONTAINER, width=220, corner_radius=0)
        self.app = app
        self.pack(side="left", fill="y", padx=0, pady=0)
        self.pack_propagate(False)
        
        self.nav_buttons = {}
        self.build()

    def build(self):
        """Build left sidebar navigation"""
        # App title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(20, 30))
        
        title = ctk.CTkLabel(
            title_frame, 
            text="📁 FileSense", 
            font=TITLE_FONT,
            text_color=TEXT_PRIMARY
        )
        title.pack(anchor="w")
        
        # Navigation buttons
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=10, pady=10)
        
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
        divider = ctk.CTkFrame(self, fg_color=OUTLINE, height=1)
        divider.pack(fill="x", padx=15, pady=20)
        
        # Actions
        actions_label = ctk.CTkLabel(
            self, 
            text="ACTIONS", 
            font=SMALL_FONT,
            text_color=TEXT_SECONDARY
        )
        actions_label.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Add File button
        self.add_btn = ctk.CTkButton(
            self,
            text="➕ Add File",
            command=self.app.open_file,
            fg_color=PRIMARY,
            text_color=ON_PRIMARY,
            hover_color=ON_PRIMARY_CONTAINER,
            height=40,
            font=BODY_FONT,
            corner_radius=RADIUS_SM
        )
        self.add_btn.pack(fill="x", padx=15, pady=5)

    def create_nav_button(self, parent, text, view_name):
        """Create a navigation button"""
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=lambda: self.app.switch_view(view_name),
            fg_color="transparent",
            hover_color=SURFACE_CONTAINER_HIGH,
            anchor="w",
            height=40,
            font=BODY_FONT,
            corner_radius=RADIUS_SM
        )
        btn.pack(fill="x", pady=2)
        return btn

    def update_selection(self, view_name):
        """Update button styles based on selected view"""
        for name, btn in self.nav_buttons.items():
            if name == view_name:
                btn.configure(fg_color=PRIMARY_CONTAINER, text_color=ON_PRIMARY_CONTAINER)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_PRIMARY)
