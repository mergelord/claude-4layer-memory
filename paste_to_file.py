#!/usr/bin/env python3
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

def clean_text(text):
    if text.startswith('\ufeff'):
        text = text[1:]
    text = re.sub(r'[\u200b\u200c\u200d\u00ad]', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [line.rstrip() for line in text.splitlines()]
    return '\n'.join(lines) + '\n'

class PasteToFileApp:
    def __init__(self, root):
        self.root = root
        root.title("Paste to File (no BOM, LF only)")
        root.geometry("900x600")

        file_frame = ttk.Frame(root)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(file_frame, text="Target file:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_var, width=80).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_file).pack(side=tk.LEFT)
        ttk.Button(file_frame, text="Normalize Current File", command=self.normalize_current).pack(side=tk.LEFT, padx=5)

        self.text = tk.Text(root, wrap=tk.NONE, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Clear", command=self.clear).pack(side=tk.RIGHT, padx=5)

    def browse_file(self):
        path = filedialog.asksaveasfilename(
            title="Select target file",
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if path:
            self.file_var.set(path)

    def normalize_current(self):
        path = self.file_var.get()
        if not path:
            messagebox.showerror("Error", "No target file specified")
            return
        p = Path(path)
        if not p.exists():
            messagebox.showerror(f"File does not exist: {p}")
            return
        t = p.read_text('utf-8')
        cleaned = clean_text(t)
        p.write_text(cleaned, 'utf-8')
        messagebox.showinfo("Done", f"Normalized: {p}")

    def save(self):
        path = self.file_var.get()
        if not path:
            messagebox.showerror("Error", "No target file specified")
            return
        raw = self.text.get("1.0", tk.END)
        cleaned = clean_text(raw)
        Path(path).write_text(cleaned, 'utf-8')
        messagebox.showinfo("Done", f"Saved to {path}")

    def clear(self):
        self.text.delete("1.0", tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = PasteToFileApp(root)
    root.mainloop()
