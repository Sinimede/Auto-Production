
import os
import tkinter as tk
import traceback
from tkinter import ttk, messagebox, simpledialog
from .base_frame import BaseFrame, BG_CONTENT, BG_MAIN, ACCENT, TEXT, TEXT_WHITE, TEXT_DIM, BORDER, FONT_TITLE, FONT_UI, FONT_LABEL, FONT_BTN
from datetime import datetime

class PdmFrame(BaseFrame):
    def __init__(self, parent, service, log_fn, get_asm_path):
        super().__init__(parent, service, log_fn, get_asm_path)
        self.pdm_service = service # PdmService
        self.current_user = os.getlogin()
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # 1. Header & Search
        header = tk.Frame(self, bg=BG_CONTENT, padx=14, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(header, text="Gestão PDM", bg=BG_CONTENT, fg=TEXT_WHITE, font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        
        search_frame = tk.Frame(header, bg=BG_CONTENT)
        search_frame.grid(row=0, column=1, sticky="e")
        
        tk.Label(search_frame, text="Procurar:", bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg=BG_MAIN, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_UI, width=30)
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self._on_search())
        
        tk.Button(search_frame, text="Ir", command=self._on_search, bg=ACCENT, fg=TEXT_WHITE, font=FONT_LABEL, relief="flat", padx=10).pack(side="left")

        # 2. Main Treeview
        tree_container = tk.Frame(self, bg=BG_MAIN, padx=14, pady=5)
        tree_container.grid(row=1, column=0, sticky="nsew")
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_container, columns=("status", "lifecycle", "user", "version", "path"), show="headings", selectmode="browse")
        self.tree.heading("status", text="Estado")
        self.tree.heading("lifecycle", text="Ciclo de Vida")
        self.tree.heading("user", text="Utilizador")
        self.tree.heading("version", text="Versão")
        self.tree.heading("path", text="Caminho Completo")
        
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("lifecycle", width=100, anchor="center")
        self.tree.column("user", width=120)
        self.tree.column("version", width=60, anchor="center")
        self.tree.column("path", width=400)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 3. Toolbar
        toolbar = tk.Frame(self, bg=BG_CONTENT, padx=14, pady=10)
        toolbar.grid(row=2, column=0, sticky="ew")

        self.btn_refresh = tk.Button(toolbar, text="\u21bb Atualizar Árvore", command=self.refresh_tree, bg=BG_MAIN, fg=TEXT, font=FONT_LABEL, relief="flat", padx=15, pady=5)
        self.btn_refresh.pack(side="left", padx=5)

        tk.Frame(toolbar, width=2, bg=BORDER).pack(side="left", fill="y", padx=10)

        self.btn_checkout = tk.Button(toolbar, text="\ud83d\udd12 Check-Out", command=self._on_checkout, bg=ACCENT, fg=TEXT_WHITE, font=FONT_BTN, relief="flat", padx=20, pady=8)
        self.btn_checkout.pack(side="left", padx=5)

        self.btn_checkin = tk.Button(toolbar, text="\ud83d\udd13 Check-In", command=self._on_checkin, bg="#28a745", fg=TEXT_WHITE, font=FONT_BTN, relief="flat", padx=20, pady=8)
        self.btn_checkin.pack(side="left", padx=5)

        self.btn_approve = tk.Button(toolbar, text="\u2705 Aprovar", command=self._on_approve, bg="#17a2b8", fg=TEXT_WHITE, font=FONT_BTN, relief="flat", padx=20, pady=8)
        self.btn_approve.pack(side="left", padx=5)

        tk.Frame(toolbar, width=2, bg=BORDER).pack(side="left", fill="y", padx=15)

        self.btn_history = tk.Button(toolbar, text="Histórico", command=self._show_history, bg=BG_MAIN, fg=TEXT, font=FONT_LABEL, relief="flat", padx=12, pady=5)
        self.btn_history.pack(side="left", padx=5)

        self.btn_where_used = tk.Button(toolbar, text="Onde é Usado?", command=self._on_where_used, bg=BG_MAIN, fg=TEXT, font=FONT_LABEL, relief="flat", padx=12, pady=5)
        self.btn_where_used.pack(side="left", padx=5)

        self.btn_add_external = tk.Button(toolbar, text="+ Ficheiro", command=self._on_add_external, bg=BG_MAIN, fg=TEXT, font=FONT_LABEL, relief="flat", padx=12, pady=5)
        self.btn_add_external.pack(side="left", padx=5)

        # 5. Context Menu (Rebuilt dynamically in _show_context_menu)
        self.context_menu = tk.Menu(self, tearoff=0)
        
        self.tree.bind("<Button-3>", self._show_context_menu)

        # 6. Status Bar
        self.status_bar = tk.Frame(self, bg=BG_MAIN, pady=5, padx=14)
        self.status_bar.grid(row=3, column=0, sticky="ew")
        
        self.lbl_stats = tk.Label(self.status_bar, text="0 ficheiros bloqueados pela equipa", bg=BG_MAIN, fg=TEXT_DIM, font=FONT_LABEL)
        self.lbl_stats.pack(side="left")

    def _show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
            
        self.tree.selection_set(item_id)
        item = self.tree.item(item_id)
        values = item['values']
        
        status = values[0]
        lifecycle = values[1]
        owner = values[2]
        
        # Create a fresh menu object every time to avoid Windows render bugs
        menu = tk.Menu(self, tearoff=0)
        
        # Build dynamic options with plain text
        if status == "LOCKED":
            if owner == self.current_user:
                menu.add_command(label="Check-In", command=self._on_checkin)
            else:
                menu.add_command(label="Bloqueado por " + owner, state="disabled")
        else:
            menu.add_command(label="Check-Out", command=self._on_checkout)
            
        menu.add_separator()
        menu.add_command(label="Histórico", command=self._show_history)
        menu.add_command(label="Onde é Usado?", command=self._on_where_used)
        
        if lifecycle != "Approved":
            menu.add_separator()
            menu.add_command(label="Aprovar para Produção", command=self._on_approve)
        
        # Display the menu
        menu.post(event.x_root, event.y_root)

    def _on_where_used(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione um ficheiro na árvore.")
            return

        item = self.tree.item(selected[0])
        file_path = item['values'][4]
        
        parents = self.pdm_service.get_where_used(file_path)
        
        win = tk.Toplevel(self)
        win.title(f"Onde é Usado - {os.path.basename(file_path)}")
        win.geometry("700x400")
        win.configure(bg=BG_MAIN)
        
        tk.Label(win, text=f"Montagens que utilizam este ficheiro:", bg=BG_MAIN, fg=TEXT_WHITE, font=FONT_TITLE, pady=10).pack()
        
        list_frame = tk.Frame(win, bg=BG_MAIN, padx=10, pady=10)
        list_frame.pack(fill="both", expand=True)
        
        tree = ttk.Treeview(list_frame, columns=("path",), show="headings")
        tree.heading("path", text="Caminho da Montagem")
        tree.column("path", width=650)
        tree.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        sb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sb.set)
        
        if not parents:
            tree.insert("", "end", values=("Nenhuma montagem encontrada no índice SQL.",))
        else:
            for p in parents:
                tree.insert("", "end", values=(p,))

        def open_parent():
            sel = tree.selection()
            if sel:
                path = tree.item(sel[0])['values'][0]
                if os.path.exists(path):
                    # Here we could trigger a callback to the main window to open this assembly
                    messagebox.showinfo("Informação", f"Para abrir esta montagem, selecione-a no topo da aplicação.\nCaminho: {path}")
                    win.destroy()
                else:
                    messagebox.showerror("Erro", "Ficheiro não encontrado no disco.")

        btn_frame = tk.Frame(win, bg=BG_MAIN, pady=10)
        btn_frame.pack()
        tk.Button(btn_frame, text="Fechar", command=win.destroy, bg=BG_CONTENT, fg=TEXT, relief="flat", padx=15).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Ver Caminho", command=open_parent, bg=ACCENT, fg=TEXT_WHITE, relief="flat", padx=15).pack(side="left", padx=5)

    def _on_add_external(self):
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(title="Selecionar Ficheiro para PDM")
        if not file_path:
            return
            
        # Check if already in PDM (optional check)
        # For now, just trigger a Check-In if it's not locked, or register it.
        # If it's a new file, we can just do a Check-In directly to register it.
        
        comment = simpledialog.askstring("Registar Ficheiro", "Comentário inicial (obrigatório):", parent=self)
        if not comment:
            return

        # Check-In needs the file to be "locked" by the user first if we follow the strict flow.
        # But for new files, we can bypass this or simulate a lock.
        # Let's use a temporary lock or just allow direct check-in if not in DB.
        
        is_locked, owner = self.pdm_service.is_locked(file_path)
        if is_locked and owner != self.current_user:
            messagebox.showerror("Erro", f"Ficheiro está bloqueado por {owner}.")
            return

        # If not locked, we simulate a check-out first to satisfy the service requirements
        if not is_locked:
            # We need to be careful: check_out renames the file.
            # For external files, maybe we should just register them.
            # Let's try to just do a manual DB insert for initial registration if check_in fails
            pass

        # Actually, let's just use the existing check_in but ensure it works without a .lock file for the first time?
        # No, PdmService.check_in requires a .lock file.
        
        # Proper way: Check-Out then Check-In.
        success, msg = self.pdm_service.check_out(file_path, self.current_user)
        if success:
            success2, msg2 = self.pdm_service.check_in(file_path, self.current_user, comment)
            if success2:
                self._on_log(f"Ficheiro registado com sucesso: {os.path.basename(file_path)}", "SUCCESS")
                self.refresh_tree()
            else:
                messagebox.showerror("Erro no Check-In", msg2)
        else:
            messagebox.showerror("Erro no Check-Out", msg)


    def refresh_tree(self):
        """Populates the tree with files from the active assembly."""
        asm_path = self._get_asm_path()
        if not asm_path or not os.path.exists(asm_path):
            messagebox.showwarning("Aviso", "Por favor, selecione um assembly válido no cabeçalho.")
            return

        self.tree.delete(*self.tree.get_children())
        self._on_log(f"A atualizar árvore PDM para {os.path.basename(asm_path)}...")
        print(f"DEBUG: Iniciando refresh_tree para {asm_path}")
        
        try:
            # Check lock before opening (Rule 4 Implementation)
            is_locked, owner = self.pdm_service.is_locked(asm_path)
            if is_locked and owner != self.current_user:
                if not messagebox.askyesno("Aviso de Bloqueio", f"O assembly está em Check-Out por {owner}.\nAbertura será apenas de leitura. Continuar?"):
                    return

            # Connect to SW if needed
            print("DEBUG: Connecting to SW...")
            self.pdm_service.sw.connect()
            
            print("DEBUG: Opening assembly resolved...")
            doc, _ = self.pdm_service.sw.open_assembly_resolved(asm_path)
            
            if not doc:
                print("DEBUG: Falha ao abrir documento (doc is None)")
                messagebox.showerror("Erro", "Falha ao abrir o documento no SolidWorks.")
                return

            # Get all components
            print("DEBUG: Getting BOM components...")
            bom_flat, _ = self.pdm_service.sw.get_bom_components(doc)
            print(f"DEBUG: Found {len(bom_flat)} components")
            
            paths = set()
            paths.add(os.path.normpath(asm_path))
            for bc in bom_flat:
                if bc.path:
                    paths.add(os.path.normpath(bc.path))

            # Add to tree
            print(f"DEBUG: Populating tree with {len(paths)} unique paths...")
            locked_count = 0
            for p in sorted(list(paths)):
                is_locked, owner = self.pdm_service.is_locked(p)
                lifecycle = self.pdm_service.get_status(p)
                
                # Try to get version from history
                history = self.pdm_service.get_history(file_path=p)
                version = history[0]['version'] if history else "-"
                
                status = "Disponível"
                if is_locked:
                    status = "LOCKED"
                    locked_count += 1
                
                tags = ("locked",) if is_locked else ("available",)
                if lifecycle == "Approved":
                    tags = tags + ("approved",)
                    
                self.tree.insert("", "end", values=(status, lifecycle, owner or "-", version, p), tags=tags)

            self.tree.tag_configure("locked", foreground="#ff6b6b")
            self.tree.tag_configure("available", foreground="#51cf66")
            self.tree.tag_configure("approved", font=(FONT_UI[0], FONT_UI[1], "bold"))
            
            self.lbl_stats.config(text=f"{locked_count} ficheiros bloqueados pela equipa | Total: {len(paths)}")
            self._on_log("Árvore PDM atualizada.")
            print("DEBUG: Refresh concluído com sucesso.")

        except Exception as e:
            print("DEBUG: EXCEÇÃO NO REFRESH_TREE:")
            traceback.print_exc()
            messagebox.showerror("Erro", f"Erro ao ler assembly: {e}")

    def _on_checkout(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione um ficheiro na árvore.")
            return

        item = self.tree.item(selected[0])
        file_path = item['values'][4] # Path is now index 4
        
        success, msg = self.pdm_service.check_out(file_path, self.current_user)
        if success:
            self._on_log(msg, "SUCCESS")
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", msg)

    def _on_checkin(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione um ficheiro na árvore.")
            return

        item = self.tree.item(selected[0])
        file_path = item['values'][4]
        
        # Check if user owns it
        is_locked, owner = self.pdm_service.is_locked(file_path)
        if not is_locked or owner != self.current_user:
            messagebox.showwarning("Aviso", "Não pode fazer Check-In de um ficheiro que não bloqueou.")
            return

        comment = simpledialog.askstring("Check-In", "Comentário da alteração (obrigatório):", parent=self)
        if not comment:
            messagebox.showwarning("Aviso", "O comentário é obrigatório.")
            return

        success, msg = self.pdm_service.check_in(file_path, self.current_user, comment)
        if success:
            self._on_log(msg, "SUCCESS")
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", msg)

    def _on_approve(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione um ficheiro na árvore.")
            return

        item = self.tree.item(selected[0])
        file_path = item['values'][4]
        file_name = os.path.basename(file_path)

        if not messagebox.askyesno("Aprovação", f"Deseja aprovar '{file_name}' para produção?\nIsto tornará o ficheiro apenas de leitura."):
            return

        if self.pdm_service.set_status(file_path, "Approved"):
            # Also set file to read-only at OS level
            try:
                import stat
                os.chmod(file_path, stat.S_IREAD)
            except:
                pass
            self._on_log(f"Ficheiro {file_name} aprovado para produção.", "SUCCESS")
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", "Falha ao atualizar status para Approved.")

    def _on_search(self):
        query = self.search_var.get().strip()
        if not query:
            self.refresh_tree()
            return
            
        self._on_log(f"A pesquisar no PDM por '{query}'...")
        results = self.pdm_service.search_files(query)
        self.tree.delete(*self.tree.get_children())
        
        locked_count = 0
        for res in results:
            p = res['file_path']
            is_locked, owner = self.pdm_service.is_locked(p)
            lifecycle = self.pdm_service.get_status(p)
            
            # Try to get version from history
            history = self.pdm_service.get_history(file_path=p)
            version = history[0]['version'] if history else "-"
            
            status = "Disponível"
            if is_locked:
                status = "LOCKED"
                locked_count += 1
            
            tags = ("locked",) if is_locked else ("available",)
            if lifecycle == "Approved":
                tags = tags + ("approved",)
                
            self.tree.insert("", "end", values=(status, lifecycle, owner or "-", version, p), tags=tags)
        
        self.lbl_stats.config(text=f"Pesquisa: {len(results)} resultados | {locked_count} bloqueados")
        self._on_log(f"Pesquisa concluída: {len(results)} ficheiros encontrados.")

    def _show_history(self):
        selected = self.tree.selection()
        file_path = None
        if selected:
            item = self.tree.item(selected[0])
            file_path = item['values'][4]

        history_win = tk.Toplevel(self)
        history_win.title(f"Histórico - {os.path.basename(file_path) if file_path else 'Global'}")
        history_win.geometry("800x500")
        history_win.configure(bg=BG_MAIN)
        
        columns = ("date", "user", "action", "version", "comment")
        h_tree = ttk.Treeview(history_win, columns=columns, show="headings")
        h_tree.heading("date", text="Data")
        h_tree.heading("user", text="Utilizador")
        h_tree.heading("action", text="Ação")
        h_tree.heading("version", text="Ver.")
        h_tree.heading("comment", text="Comentário")
        
        h_tree.column("date", width=130)
        h_tree.column("user", width=100)
        h_tree.column("action", width=80)
        h_tree.column("version", width=40)
        h_tree.column("comment", width=300)
        
        h_tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        data = self.pdm_service.get_history(file_path=file_path)
        for row in data:
            h_tree.insert("", "end", values=(row['date'], row['user'], row['action'], row['version'], row['comment']))
        
        btn_close = tk.Button(history_win, text="Fechar", command=history_win.destroy, bg=BG_CONTENT, fg=TEXT, relief="flat", padx=15, pady=5)
        btn_close.pack(pady=10)
