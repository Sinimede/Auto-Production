# Auto Production Modernization Design

**Date:** 2026-03-19
**Status:** Draft
**Topic:** Architectural Refactoring, Code Quality, and Bug Resolution

## 1. Objective
Refactor the "Auto Production" suite into a professional, modular Python application. This modernization focuses on separating business logic from the UI, improving SolidWorks COM stability, and resolving critical Excel processing inconsistencies.

## 2. Architecture: Service-Oriented MVC
The project will move from a script-based structure to a layered architecture:

- **Core Layer (`src/core/`):** Pure SolidWorks API wrappers. Handles SW 2024 quirks (early/late binding, callable-guards, object wrapping).
- **Service Layer (`src/services/`):** Business logic (traversal, export flows, file management). Orchestrates the Core and Utils layers.
- **UI Layer (`src/ui/`):** Tkinter Views. Responsible only for user input and displaying progress via callbacks.
- **Utils Layer (`src/utils/`):** Shared helpers for Excel (openpyxl), logging, and path normalization.

## 3. Key Components & Data Flow

### 3.1 SolidWorks Client (`src/core/solidworks.py`)
- **Resilience:** Implements `@ensure_sw_connection` decorator to handle disconnected COM objects.
- **SW 2024 Compliance:** Standardizes the use of `GetRootComponent3` and `GetChildren` with proper wrapping and callable-guards.
- **Geometry Logic:** Refined `_select_length_axis` to detect extrusion axes in short profiles (length < width/height).

### 3.2 Exporter Service (`src/services/exporter_service.py`)
- **Threading:** Launches exports in background threads.
- **Callbacks:** Provides `on_progress(msg, current, total)` and `on_error(exception)` hooks for the UI.
- **File Orchestration:** Manages `.tmp/` lifecycle for Router parts and ensures cleanup.

### 3.3 Dynamic Excel Writer (`src/utils/excel_writer.py`)
- **Dynamic Header Detection:** Scans for "Pos" or "Qt" markers to identify the data start row (solving the Laser vs Router index conflict).
- **Table Management:** Automatically resizes Excel `ListObjects` (Tables) to match the data range.
- **Integrated Validation:** Automatically runs `PostProcess` rules immediately after export.

## 4. Proposed Directory Structure
```text
auto-production/
├── src/
│   ├── core/           # SolidWorksClient, decorators
│   ├── services/       # DxfService, StepService, ValidationService
│   ├── ui/             # MainWindow, Frames, Widgets
│   └── utils/          # ExcelWriter, Logger, PathUtils
├── assets/             # Templates (.xlsx, .sldbomtbt)
├── tests/              # Unit tests for Services and Utils
├── main.py             # Entry point
└── requirements.txt    # dependencies
```

## 5. Implementation Strategy
1. **Phase 0 (Critical Fixes):** Fix Excel indices and `GetRootComponent3` patterns in the current structure.
2. **Phase 1 (Scaffolding):** Create the `src/` hierarchy and migrate `solidworks.py` to `src/core/`.
3. **Phase 2 (Logic Extraction):** Move export orchestration from GUI modules to `src/services/`.
4. **Phase 3 (UI Refactoring):** Rewrite Tkinter modules to use the new Services and Callbacks.
5. **Phase 4 (Validation):** Integrate Rule validation into the main export flow.

## 6. Success Criteria
- Zero GUI "freezes" during exports.
- All Excel exports have correct headers and resized tables.
- Full test coverage for `ExcelWriter` and `PathUtils`.
- Successful export of a 100+ part assembly without manual intervention.
