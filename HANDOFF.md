# Handoff — 2026-03-12

## Feature 1: Assembly DXF Exporter & Cleaner

### Para testar amanhã

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\dxf_exporter"
python main.py
```

1. Abre o SolidWorks
2. Corre `main.py`
3. Seleciona um assembly com pelo menos 1 peça com `corte fabrico = laser`
4. Seleciona uma pasta de output
5. Clica **Export & Clean**

---

### Se der erro no export (SaveAs4)

Alternativa para o `pExportData`: em vez de `None`, criar o objeto de export:

```python
export_data = sw_app.GetExportFileData(1)  # 1 = swExportDXF
drw_doc.SaveAs4(output_dxf_path, 0, 1, export_data, errors, warnings)
```

Editar `solidworks.py` linha ~182.

### Se `GetComponents(False)` devolver lista vazia

Tentar `GetComponents(True)` — há variações entre versões do SolidWorks.
Editar `solidworks.py` linha ~64.

---

### Ficheiros principais

| Ficheiro | O que faz |
|---|---|
| `tools/dxf_exporter/main.py` | App tkinter — entry point |
| `tools/dxf_exporter/solidworks.py` | SolidWorks COM API |
| `tools/dxf_exporter/dxf_cleaner.py` | Limpeza DXF (✅ testado) |
| `docs/superpowers/specs/2026-03-12-assembly-dxf-exporter-design.md` | Spec completo |
