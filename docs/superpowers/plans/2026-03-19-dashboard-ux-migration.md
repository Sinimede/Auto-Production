# Auto Production Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sidebar-based GUI with a modern Dashboard featuring process cards, selective processing, and a secure "Hold to Cancel" mechanism.

**Architecture:** A centralized `DashboardFrame` replaces individual modules. Each process is represented by a `ProcessCard` widget. Execution is managed by a `JobManager` that runs tasks in a background thread while keeping the UI responsive for the "Hold to Cancel" gesture.

**Tech Stack:** Python 3.x, Tkinter (Canvas for custom widgets), Threading.

---

### Task 1: Refactor Logging System
**Files:**
- Modify: `tools/exporter/main.py`
- Modify: `tools/exporter/modules/base_frame.py` (if exists, or create util)

- [x] **Step 1: Create a structured LogManager**
- [x] **Step 2: Update MainWindow to store log entries**
- [x] **Step 3: Implement filtering logic in MainWindow**
- [x] **Step 4: Commit**

### Task 2: Implement ProcessCard Widget
**Files:**
- Create: `tools/exporter/widgets/process_card.py`
- Test: `tools/exporter/tests/test_process_card.py`

- [x] **Step 1: Define ProcessCard class**
- [x] **Step 2: Add click event for log filtering**
- [x] **Step 3: Commit**

### Task 3: Implement "Hold to Cancel" Button
**Files:**
- Create: `tools/exporter/widgets/hold_button.py`
- Test: `tools/exporter/tests/test_hold_button.py`

- [x] **Step 1: Create HoldButton using tk.Canvas**
- [x] **Step 2: Implement reset logic on release**
- [x] **Step 3: Commit**

### Task 4: Create Dashboard Frame
**Files:**
- Create: `tools/exporter/modules/dashboard_module.py`
- Modify: `tools/exporter/main.py`

- [x] **Step 1: Layout the grid of ProcessCards**
- [x] **Step 2: Add the Top Action Bar with Assembly Selector and "GERAR TUDO"**
- [x] **Step 3: Integrate with MainWindow's module switcher**
- [x] **Step 4: Commit**

### Task 5: Modal Progress Hub & Execution Loop
**Files:**
- Modify: `tools/exporter/modules/dashboard_module.py`
- Create: `tools/exporter/core/job_manager.py`

- [x] **Step 1: Implement the Modal Overlay (semi-transparent Frame)**
- [x] **Step 2: Create JobManager to sequence tasks (Laser -> STEP -> BOM)**
- [x] **Step 3: Link "Hold to Cancel" to JobManager's stop event**
- [x] **Step 4: Update ProcessCard states during execution**
- [x] **Step 5: Commit**

### Task 6: Cleanup & Migration
**Files:**
- Modify: `tools/exporter/main.py`
- Delete: `tools/exporter/modules/all_module.py` (integrated into Dashboard)

- [x] **Step 1: Set Dashboard as the default view**
- [ ] **Step 2: Ensure persistent settings (last folder) work with new UI**
- [ ] **Step 3: Final validation with SolidWorks**
- [ ] **Step 4: Commit**
