# Auto Production Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the codebase into a layered architecture (Core, Service, UI, Utils) while fixing critical COM and Excel bugs.

**Architecture:** Layered Service-Oriented MVC. Business logic is isolated from UI in Services; SolidWorks interaction is encapsulated in Core; Shared logic in Utils.

**Tech Stack:** Python 3.x, win32com (SolidWorks API), openpyxl, tkinter.

---

### Task 0: Critical Fixes (Phase 0)
Fix the Excel index conflict and the inconsistent `GetRootComponent3` pattern in the current structure to ensure immediate stability.

**Files:**
- Modify: `tools/exporter/solidworks.py`
- Modify: `tools/post_process/apply_rules.py`
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [x] **Step 1: Fix `GetRootComponent3` pattern in `get_all_parts`**
  Ensure it uses the callable-guard pattern.

- [x] **Step 2: Fix dynamic header detection in `apply_rules.py`**
  Modify it to scan for "Pos" or "Qt" instead of assuming row 2.

- [x] **Step 3: Run existing tests to verify stability**
  Run: `pytest tools/exporter/tests/`

- [x] **Step 4: Commit Phase 0**

---

### Task 1: Scaffolding and Utils (Phase 1)
Create the new directory structure and migrate the `ExcelWriter`.

**Files:**
- Create: `src/utils/excel_writer.py`
- Create: `src/utils/path_utils.py`
- Create: `tests/utils/test_excel_writer.py`

- [x] **Step 1: Create `src/` hierarchy**

- [x] **Step 2: Implement `src/utils/path_utils.py`**

- [x] **Step 3: Migrate and enhance `ExcelWriter`**
  Add `resize_table` and dynamic header detection.

- [x] **Step 4: Commit Phase 1**

---

### Task 2: Core Layer (SolidWorks Client)
Migrate the SolidWorks wrapper to `src/core/` and add the `@ensure_sw_connection` decorator.

**Files:**
- Create: `src/core/solidworks.py`
- Test: `tests/core/test_solidworks.py`

- [x] **Step 1: Implement `@ensure_sw_connection`**
  Handles COM disconnection errors.

- [x] **Step 2: Migrate `SolidWorksClient` classes**
  Move logic from `tools/exporter/solidworks.py` to the new class-based structure in `src/core/`.

- [x] **Step 3: Commit Phase 2**

---

### Task 3: Service Layer (Orchestration)
Create the `ExporterService` to handle the business logic of exporting parts.

**Files:**
- Create: `src/services/exporter_service.py`
- Create: `src/services/dxf_service.py`

- [x] **Step 1: Implement base `ExporterService` with threading and callbacks**
- [x] **Step 2: Move DXF traversal and export logic to `DxfService`**
- [x] **Step 3: Commit Phase 3**

---

### Task 4: UI Refactoring (Phase 3)
Rewrite the main window and modules to use the services.

**Files:**
- Create: `src/ui/main_window.py`
- Create: `src/ui/modules/base_frame.py`
- Create: `src/ui/modules/dxf_frame.py`

- [x] **Step 1: Create the new Main Window using the sidebar registry**
- [x] **Step 2: Implement `DxfFrame` connecting to `DxfService`**
- [x] **Step 3: Commit Phase 4**

---

### Task 5: Final Integration and Cleanup
Move assets, update entry point, and verify the full flow.

- [x] **Step 1: Move templates to `assets/`**
- [x] **Step 2: Create `main.py` at root**
- [x] **Step 3: Verify full export flow** (Verified via unit tests and code inspection)
- [x] **Step 4: Commit and finalize**
