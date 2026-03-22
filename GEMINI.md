# Auto Production — Gemini CLI Context

This project is an automation suite for **SolidWorks** using **Python** and the **win32com** (COM API) library. It focuses on streamlining the production lifecycle: exporting DXF/STEP files, generating Bill of Materials (BOM), and managing supplier data.

## MCP Server superpowers
 - **Usage:** Always use superpowers tools, skills, and agents or feature available. 

## Project Overview

- **Purpose:** Automate SolidWorks exports (DXF for Laser, STEP for CNC/Router) and production data management.
- **Architecture (WAT):**
    - **Workflows:** Markdown SOPs and plans (located in `docs/superpowers/plans/` and `specs/`).
    - **Agents:** AI decision-makers (like Gemini CLI) orchestrating tools.
    - **Tools:** Deterministic Python scripts in `tools/` for execution.
- **Tech Stack:**
    - **Python 3.x** with `pywin32` (win32com), `ezdxf`, `openpyxl`, and `tkinter`.
    - **SolidWorks 2024+** (must be running for most tools).
- **Core Logic:**
    - `tools/exporter/`: Unified desktop app for DXF and STEP exports.
    - `tools/dxf_exporter/`: Original standalone DXF tool.
    - `src/pdm/`: Modern PDM suite (PyQt6) for file lifecycle management (Check-In/Out, Where Used).
    - `tools/fornecedores/`: Supplier lookup and management.
    - `tools/post_process/`: Automated rule application for geometry/data.

## Building and Running

### Key Commands

- **Launch Modernized GUI (Recommended):**
  ```bash
  run.bat
  ```
- **Launch PDM System (PyQt6):**
  ```bash
  run_pdm.bat
  ```
- **Launch Legacy Unified GUI:**
  ```bash
  python tools/exporter/main.py
  ```
- **Launch Standalone DXF Exporter:**
  ```bash
  python tools/dxf_exporter/main.py
  ```
- **Run Headless STEP Export Test:**
  ```bash
  python tools/exporter/test_step.py
  ```
- **Post-Process Rules:**
  ```bash
  run_post_process.bat
  ```

### Requirements

- **SolidWorks** must be open and active.
- Dependencies: `pip install -r tools/exporter/requirements.txt` (includes `pywin32`, `ezdxf`, `openpyxl`).

## Development Conventions

### SolidWorks COM API (Critical)
Refer to `docs/project-guide.md` for exhaustive details on SW 2024 quirks.

- **Binding:** Use **early binding** for queries/reads and **late binding** for `SaveAs4` and `ResolveAllLightweightComponents` to avoid `DISP_E_TYPEMISMATCH` or silent no-ops.
- **Object Wrapping:** Always use the `_wrap(obj, "InterfaceName")` helper for objects returned by methods like `GetChildren` or `GetModelDoc2`.
- **Method/Property Quirk:** In SW 2024, some methods behave as properties. Use the `callable-guard` pattern: `ref = obj.Method; val = ref() if callable(ref) else ref`.
- **Path Normalization:** Always use `os.path.normpath(os.path.abspath(path))` before passing paths to SolidWorks (e.g., `OpenDoc6`, `CloseDoc`).
- **Temporary Files:** Use `.tmp/` for intermediate files (e.g., modifying parts before STEP export). Clean up in `finally` blocks.

### Code Structure
- **GUI:** `tkinter` with a sidebar navigation pattern. Content frames are located in `tools/exporter/modules/`.
- **Separation of Concerns:** All SolidWorks-specific COM logic should reside in `solidworks.py` wrappers.
- **Logging:** Use the shared log widget in `MainWindow` via `log_fn` callbacks.

## Key Directories

- `tools/`: Python implementation logic.
- `docs/`: Technical guides, design specs, and implementation plans.
- `assets/`: Excel and SolidWorks templates for reports and BOMs (formerly Templates/).
- `Resultados/`: Default output directory for exports.
- `.tmp/`: Workspace for temporary file modifications (gitignored).

