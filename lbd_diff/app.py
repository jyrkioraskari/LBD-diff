from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from rdflib import Graph

from .diff_engine import ModelDiff, diff_graphs, format_term, load_turtle, predicate_value_text


class LbdDiffApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LBD Diff")
        self.geometry("1100x720")
        self.minsize(900, 560)

        self.first_path = tk.StringVar()
        self.second_path = tk.StringVar()
        self.status = tk.StringVar(value="Load two Turtle files to compare.")

        self._first_graph: Graph | None = None
        self._second_graph: Graph | None = None

        self._configure_style()
        self._build_layout()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Toolbar.TFrame", background="#f4f6f8")
        style.configure("Status.TLabel", padding=(8, 5))
        style.configure("Treeview", rowheight=24)
        style.configure("Treeview.Heading", font=("", 10, "bold"))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=10)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        toolbar.columnconfigure(4, weight=1)

        ttk.Button(toolbar, text="Load first file", command=self._choose_first).grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(toolbar, textvariable=self.first_path, state="readonly").grid(row=0, column=1, sticky="ew")

        ttk.Button(toolbar, text="Load second file", command=self._choose_second).grid(row=0, column=3, padx=(18, 8))
        ttk.Entry(toolbar, textvariable=self.second_path, state="readonly").grid(row=0, column=4, sticky="ew")

        ttk.Button(toolbar, text="Compare", command=self._compare).grid(row=0, column=5, padx=(18, 0))

        content = ttk.Frame(self, padding=(10, 0, 10, 0))
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(content, columns=("count",), show="tree headings")
        self.tree.heading("#0", text="Model difference")
        self.tree.heading("count", text="Count")
        self.tree.column("#0", width=830, stretch=True)
        self.tree.column("count", width=120, anchor="e", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        status = ttk.Label(self, textvariable=self.status, style="Status.TLabel", anchor="w")
        status.grid(row=2, column=0, sticky="ew")

    def _choose_first(self) -> None:
        path = self._ask_turtle_file()
        if path:
            self.first_path.set(path)
            self._first_graph = None
            self.status.set(f"First file selected: {Path(path).name}")

    def _choose_second(self) -> None:
        path = self._ask_turtle_file()
        if path:
            self.second_path.set(path)
            self._second_graph = None
            self.status.set(f"Second file selected: {Path(path).name}")

    def _ask_turtle_file(self) -> str:
        return filedialog.askopenfilename(
            title="Select LBD Turtle file",
            filetypes=[
                ("Turtle files", "*.ttl *.turtle"),
                ("RDF files", "*.ttl *.turtle *.rdf *.nt"),
                ("All files", "*.*"),
            ],
        )

    def _compare(self) -> None:
        first = self.first_path.get()
        second = self.second_path.get()
        if not first or not second:
            messagebox.showwarning("Files required", "Select two Turtle files before comparing.")
            return

        self.status.set("Parsing and comparing files...")
        self._set_buttons_state("disabled")
        thread = threading.Thread(target=self._compare_worker, args=(first, second), daemon=True)
        thread.start()

    def _compare_worker(self, first: str, second: str) -> None:
        try:
            first_graph = self._first_graph or load_turtle(first)
            second_graph = self._second_graph or load_turtle(second)
            diff = diff_graphs(first_graph, second_graph, first, second)
        except Exception as exc:
            self.after(0, self._show_error, exc)
            return

        self._first_graph = first_graph
        self._second_graph = second_graph
        self.after(0, self._show_diff, diff)

    def _show_error(self, exc: Exception) -> None:
        self._set_buttons_state("normal")
        self.status.set("Comparison failed.")
        messagebox.showerror("Comparison failed", str(exc))

    def _show_diff(self, diff: ModelDiff) -> None:
        self._set_buttons_state("normal")
        self.tree.delete(*self.tree.get_children())

        root_text = f"{diff.first_file.name} compared with {diff.second_file.name}"
        root = self.tree.insert("", "end", text=root_text, values=(self._total_changes(diff),), open=True)
        self.tree.insert(root, "end", text=f"First graph triples: {diff.first_triple_count}", values=("",))
        self.tree.insert(root, "end", text=f"Second graph triples: {diff.second_triple_count}", values=("",))

        self._insert_resource_group(root, "Added resources", diff.added_resources, "added")
        self._insert_resource_group(root, "Removed resources", diff.removed_resources, "removed")
        self._insert_resource_group(root, "Changed resources", diff.changed_resources, "changed")

        if diff.has_changes:
            self.status.set(
                f"Compared {diff.first_file.name} and {diff.second_file.name}: "
                f"{len(diff.added_resources)} added, "
                f"{len(diff.removed_resources)} removed, "
                f"{len(diff.changed_resources)} changed resources."
            )
        else:
            self.status.set("The two RDF graphs contain the same triples.")

    def _insert_resource_group(self, parent: str, title: str, resources: tuple, mode: str) -> None:
        group = self.tree.insert(parent, "end", text=title, values=(len(resources),), open=True)
        for resource in resources:
            text = format_term(resource.subject, self._second_graph if mode == "added" else self._first_graph)
            total = len(resource.added) + len(resource.removed)
            item = self.tree.insert(group, "end", text=text, values=(total,), open=False)

            if resource.added:
                added_node = self.tree.insert(item, "end", text="Added triples", values=(len(resource.added),), open=False)
                for added in resource.added:
                    self.tree.insert(added_node, "end", text=predicate_value_text(added, self._second_graph), values=("",))

            if resource.removed:
                removed_node = self.tree.insert(item, "end", text="Removed triples", values=(len(resource.removed),), open=False)
                for removed in resource.removed:
                    self.tree.insert(removed_node, "end", text=predicate_value_text(removed, self._first_graph), values=("",))

    def _set_buttons_state(self, state: str) -> None:
        for child in self.winfo_children():
            self._set_state_recursive(child, state)

    def _set_state_recursive(self, widget: tk.Widget, state: str) -> None:
        if isinstance(widget, ttk.Button):
            widget.configure(state=state)
        for child in widget.winfo_children():
            self._set_state_recursive(child, state)

    @staticmethod
    def _total_changes(diff: ModelDiff) -> int:
        return len(diff.added_resources) + len(diff.removed_resources) + len(diff.changed_resources)


def main() -> None:
    app = LbdDiffApp()
    app.mainloop()

