"""
main.py — Assembly DXF Exporter & Cleaner

Windows Desktop tool for mechanical engineers.
Connects to SolidWorks, finds all parts marked 'corte fabrico = laser' in an
assembly, exports their drawings to DXF, and removes concentric circles caused
by countersunk holes.

Usage:
    python main.py
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Assembly DXF Exporter & Cleaner")
        self.resizable(False, False)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # Row 0 — Assembly file
        tk.Label(self, text="Assembly (.sldasm):", anchor="e").grid(
            row=0, column=0, sticky="e", **pad)
        self.asm_var = tk.StringVar()
        tk.Entry(self, textvariable=self.asm_var, width=58).grid(
            row=0, column=1, padx=4, pady=4)
        tk.Button(self, text="Browse…", command=self._browse_asm).grid(
            row=0, column=2, padx=(0, 8), pady=4)

        # Row 1 — Output folder
        tk.Label(self, text="Output folder:", anchor="e").grid(
            row=1, column=0, sticky="e", **pad)
        self.out_var = tk.StringVar()
        tk.Entry(self, textvariable=self.out_var, width=58).grid(
            row=1, column=1, padx=4, pady=4)
        tk.Button(self, text="Browse…", command=self._browse_out).grid(
            row=1, column=2, padx=(0, 8), pady=4)

        # Row 2 — Export button
        self.btn_export = tk.Button(
            self, text="Export & Clean",
            command=self._start_export,
            bg="#0078D4", fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=20, pady=6,
            relief="flat", cursor="hand2",
        )
        self.btn_export.grid(row=2, column=0, columnspan=3, pady=(10, 4))

        # Row 3 — Progress bar
        self.progress = ttk.Progressbar(self, length=560, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=3, padx=10, pady=(4, 0))

        # Row 4 — Status label
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(self, textvariable=self.status_var, anchor="w",
                 font=("Segoe UI", 9)).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 4))

        # Row 5 — Log area
        self.log = scrolledtext.ScrolledText(
            self, width=78, height=16, state="disabled",
            font=("Consolas", 9), relief="sunken", bd=1,
        )
        self.log.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 10))

    # ------------------------------------------------------------------
    # File / folder dialogs
    # ------------------------------------------------------------------

    def _browse_asm(self):
        path = filedialog.askopenfilename(
            title="Seleciona o assembly SolidWorks",
            filetypes=[("SolidWorks Assembly", "*.sldasm"), ("All files", "*.*")],
        )
        if path:
            self.asm_var.set(path)

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Export pipeline
    # ------------------------------------------------------------------

    def _start_export(self):
        asm = self.asm_var.get().strip()
        out = self.out_var.get().strip()

        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return

        # Reset UI state
        self.btn_export.config(state="disabled")
        self.progress["value"] = 0
        self._clear_log()
        self._set_status("A iniciar…")

        thread = threading.Thread(target=self._worker, args=(asm, out), daemon=True)
        thread.start()

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in a background thread. All UI updates go through root.after()."""
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_laser_part, get_part_path,
            export_part_to_dxf,
        )
        from dxf_cleaner import clean_dxf

        def ui(fn):
            self.after(0, fn)

        ok_count = 0
        warn_count = 0
        err_count = 0
        asm_doc = None
        asm_opened_by_us = False

        try:
            ui(lambda: self._log("Conectando ao SolidWorks…"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes…"))
            all_parts = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            laser_parts = [p for p in unique_parts if is_laser_part(p)]

            ui(lambda: self._log(
                f"Total de peças: {len(all_parts)} | "
                f"Únicas: {len(unique_parts)} | "
                f"Corte laser: {len(laser_parts)}"
            ))
            ui(lambda: self._log("─" * 68))

            total = len(laser_parts)
            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça encontrada com 'corte fabrico = laser'. "
                    "Verifica as propriedades das peças no SolidWorks."
                ))
                return

            ui(lambda: self._set_progress(0, total))

            for i, part in enumerate(laser_parts):
                part_path = get_part_path(part)
                part_name = os.path.basename(part_path)
                base_name = os.path.splitext(part_name)[0]

                ui(lambda n=part_name, idx=i: (
                    self._set_progress(idx, total),
                    self._set_status(f"A processar {n}…"),
                ))

                raw_dxf = os.path.join(out_dir, base_name + "_raw.dxf")
                final_dxf = os.path.join(out_dir, base_name + ".dxf")

                try:
                    export_part_to_dxf(sw, part_path, raw_dxf)
                    removed = clean_dxf(raw_dxf, final_dxf)
                    try:
                        os.remove(raw_dxf)
                    except OSError:
                        pass
                    ok_count += 1
                    circles_txt = (
                        f"{removed} círculo(s) removido(s)" if removed else "sem alterações"
                    )
                    msg = f"  OK     {base_name}.dxf  [{circles_txt}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    err_count += 1
                    msg = f"  ERROR  {base_name} — {exc}"
                    ui(lambda m=msg: self._log(m))
                    # Clean up partial raw file if it exists
                    if os.path.isfile(raw_dxf):
                        try:
                            os.remove(raw_dxf)
                        except OSError:
                            pass

            ui(lambda: self._set_progress(total, total))

        except Exception as exc:
            err_count += 1
            msg = f"ERRO FATAL: {exc}"
            ui(lambda m=msg: self._log(m))

        finally:
            # Close assembly only if we opened it (don't close the engineer's work)
            if asm_opened_by_us and asm_doc is not None and sw is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_export.config(state="normal")
                self._set_status("Concluído.")
                self._log("─" * 68)
                self._log(
                    f"Resultado: {ok_count} exportado(s)  |  "
                    f"{warn_count} aviso(s)  |  {err_count} erro(s)"
                )

            ui(_finish)

    # ------------------------------------------------------------------
    # Thread-safe UI helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_progress(self, value: int, maximum: int):
        self.progress["maximum"] = maximum or 1
        self.progress["value"] = value


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Ensure the script's directory is in sys.path so sibling modules are found.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    app = App()
    app.mainloop()
