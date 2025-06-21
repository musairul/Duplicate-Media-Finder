#!/usr/bin/env python3
"""
Entry point for the Duplicate Media Finder application.
"""

from main import DuplicateFinderWizard
import tkinter as tk
from tkinter import ttk

def main():
    """Main entry point for the application."""
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

if __name__ == "__main__":
    main()
