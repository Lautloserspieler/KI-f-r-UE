"""Simple Tkinter-based control panel for Auto-PCG."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from auto_pcg.services.pcg_service import AutoPCGService


def launch_control_panel() -> None:
    app = AutoPCGControlPanel()
    app.mainloop()


class AutoPCGControlPanel(tk.Tk):
    """Minimal desktop UI to configure and run Auto-PCG pipelines."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Auto-PCG Control Panel")
        self.geometry("900x640")
        self._worker: Optional[threading.Thread] = None
        self._build_ui()

    # UI ---------------------------------------------------------------------------------

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(container, text="Konfiguration", padding=8)
        form.pack(fill=tk.X, expand=False)

        self.project_var = tk.StringVar(value=str(Path.cwd()))
        self.prompt_var = tk.StringVar(value="Erstelle eine alpine Hochgebirgslandschaft")
        self.heightmap_var = tk.StringVar(value="")
        self.export_dir_var = tk.StringVar(value=str(Path.cwd() / "exports"))
        self.performance_profile_var = tk.StringVar(value="high_end_pc")
        self.target_style_var = tk.StringVar(value="realistic")
        self.season_var = tk.StringVar(value="summer")
        self.max_assets_var = tk.StringVar(value="")
        self.batch_size_var = tk.StringVar(value="")
        self.world_size_var = tk.StringVar(value="10000")
        self.sector_size_var = tk.StringVar(value="1000")
        self.ollama_url_var = tk.StringVar(value="")
        self.ollama_model_var = tk.StringVar(value="")
        self.ollama_timeout_var = tk.StringVar(value="")
        self.ue_editor_var = tk.StringVar(value="")
        self.ue_map_var = tk.StringVar(value="")
        self.ue_folder_var = tk.StringVar(value="/Game/AutoPCG")

        self.use_spatial_var = tk.BooleanVar(value=True)
        self.hierarchical_var = tk.BooleanVar(value=True)
        self.heuristic_only_var = tk.BooleanVar(value=False)
        self.no_local_llm_var = tk.BooleanVar(value=False)
        self.disable_layer_paint_var = tk.BooleanVar(value=False)
        self.no_spawn_var = tk.BooleanVar(value=False)

        row = 0
        row = self._add_path_field(form, row, "Projektverzeichnis", self.project_var, directory=True)
        row = self._add_path_field(form, row, "Heightmap", self.heightmap_var)
        row = self._add_path_field(form, row, "Export-Verzeichnis", self.export_dir_var, directory=True)

        row = self._add_text_field(form, row, "Prompt", self.prompt_var, width=60)
        row = self._add_combo_field(
            form, row, "Performance-Profil", self.performance_profile_var, ["mobile", "desktop", "console", "high_end_pc"]
        )
        row = self._add_text_field(form, row, "Stil (target_style)", self.target_style_var)
        row = self._add_combo_field(form, row, "Saison", self.season_var, ["summer", "autumn", "winter", "spring"])
        row = self._add_text_field(form, row, "Max Assets", self.max_assets_var)
        row = self._add_text_field(form, row, "Batch Size", self.batch_size_var)
        row = self._add_text_field(form, row, "World Size (m)", self.world_size_var)
        row = self._add_text_field(form, row, "Sector Size (m)", self.sector_size_var)
        row = self._add_text_field(form, row, "Ollama URL", self.ollama_url_var)
        row = self._add_text_field(form, row, "Ollama Modell", self.ollama_model_var)
        row = self._add_text_field(form, row, "Ollama Timeout", self.ollama_timeout_var)
        row = self._add_path_field(form, row, "UE Editor Pfad", self.ue_editor_var)
        row = self._add_text_field(form, row, "UE Map", self.ue_map_var)
        row = self._add_text_field(form, row, "UE Asset Folder", self.ue_folder_var)

        checkbox_frame = ttk.Frame(form)
        checkbox_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(checkbox_frame, text="Spatial DB", variable=self.use_spatial_var).pack(side=tk.LEFT)
        ttk.Checkbutton(checkbox_frame, text="Hierarchische PCG", variable=self.hierarchical_var).pack(side=tk.LEFT)
        ttk.Checkbutton(checkbox_frame, text="Heuristik only", variable=self.heuristic_only_var).pack(side=tk.LEFT)
        ttk.Checkbutton(checkbox_frame, text="Kein lokales LLM", variable=self.no_local_llm_var).pack(side=tk.LEFT)
        ttk.Checkbutton(checkbox_frame, text="Layer-Paint deaktivieren", variable=self.disable_layer_paint_var).pack(
            side=tk.LEFT
        )
        ttk.Checkbutton(checkbox_frame, text="Kein UE Spawn", variable=self.no_spawn_var).pack(side=tk.LEFT)

        button_frame = ttk.Frame(container)
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Pipeline starten", command=self._start_pipeline).pack(side=tk.LEFT)

        output_frame = ttk.LabelFrame(container, text="Ausgabe", padding=6)
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.output_text = tk.Text(output_frame, height=18, wrap=tk.NONE)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        scroll_y = ttk.Scrollbar(self.output_text, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _add_path_field(self, parent, row: int, label: str, var: tk.StringVar, directory: bool = False) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        entry = ttk.Entry(parent, textvariable=var, width=50)
        entry.grid(row=row, column=1, sticky="we", pady=2)
        button = ttk.Button(
            parent,
            text="...",
            width=3,
            command=lambda v=var: self._browse(var, directory=directory),
        )
        button.grid(row=row, column=2, pady=2, padx=(6, 0))
        return row + 1

    def _add_text_field(self, parent, row: int, label: str, var: tk.StringVar, width: int = 30) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="we", pady=2, columnspan=2)
        return row + 1

    def _add_combo_field(self, parent, row: int, label: str, var: tk.StringVar, values: list[str]) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        combo = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="we", pady=2, columnspan=2)
        return row + 1

    # Actions -----------------------------------------------------------------------------

    def _browse(self, var: tk.StringVar, directory: bool = False) -> None:
        if directory:
            selection = filedialog.askdirectory()
        else:
            selection = filedialog.askopenfilename()
        if selection:
            var.set(selection)

    def _start_pipeline(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Auto-PCG", "Es läuft bereits ein Auftrag.")
            return
        self._append_output("\n[INFO] Starte Auto-PCG Pipeline...\n")
        self._worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self._worker.start()

    def _run_pipeline(self) -> None:
        try:
            kwargs = self._collect_service_args()
            service = AutoPCGService(**kwargs)
            result = service.run_full_pipeline(self.prompt_var.get())
            payload = json.dumps(
                {
                    "graph": getattr(result.get("graph"), "description", "graph"),
                    "assets": len(result.get("assets", [])),
                    "season": self.season_var.get(),
                },
                indent=2,
                ensure_ascii=False,
            )
            self._append_output(payload + "\n")
        except Exception as exc:  # pragma: no cover - UI runtime
            self._append_output(f"[ERROR] {exc}\n")

    def _collect_service_args(self) -> dict:
        def parse_int(value: str) -> Optional[int]:
            return int(value) if value.strip() else None

        def parse_float(value: str) -> Optional[float]:
            return float(value) if value.strip() else None

        args = {
            "project_root": Path(self.project_var.get()),
            "max_assets": parse_int(self.max_assets_var.get()),
            "prefer_heuristics": self.heuristic_only_var.get(),
            "classification_batch_size": parse_int(self.batch_size_var.get()),
            "ollama_url": self.ollama_url_var.get() or None,
            "ollama_model": self.ollama_model_var.get() or None,
            "ollama_timeout": parse_float(self.ollama_timeout_var.get()),
            "use_local_model": not self.no_local_llm_var.get(),
            "export_directory": Path(self.export_dir_var.get()) if self.export_dir_var.get() else None,
            "heightmap": Path(self.heightmap_var.get()) if self.heightmap_var.get() else None,
            "performance_profile": self.performance_profile_var.get(),
            "target_style": self.target_style_var.get(),
            "auto_layer_paint": not self.disable_layer_paint_var.get(),
            "use_spatial_database": self.use_spatial_var.get(),
            "world_size": float(self.world_size_var.get() or 2048.0),
            "sector_size": float(self.sector_size_var.get() or 512.0),
            "season": self.season_var.get(),
            "hierarchical_pcg": self.hierarchical_var.get(),
            "ue_editor": Path(self.ue_editor_var.get()) if self.ue_editor_var.get() else None,
            "ue_map": self.ue_map_var.get() or None,
            "ue_asset_folder": self.ue_folder_var.get() or "/Game/AutoPCG",
            "ue_spawn": not self.no_spawn_var.get(),
        }
        return args

    def _append_output(self, text: str) -> None:
        def append() -> None:
            self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)

        self.after(0, append)


if __name__ == "__main__":
    launch_control_panel()
