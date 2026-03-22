# Design Spec: Auto Production Dashboard & UX Modernization

**Date:** 2026-03-19
**Status:** Approved (Brainstormed)
**Topic:** Transition from sidebar navigation to a unified Dashboard with selective processing and robust cancellation.

## 1. Objective
Redesign the Auto Production GUI to provide a high-level overview of the production state, allow selective processing of specific components (Laser, CNC, etc.), and implement a safe "Hold to Cancel" mechanism to prevent accidental interruptions in SolidWorks.

## 2. User Experience (UX) Architecture

### 2.1 Dashboard Layout (Main Screen)
- **Unified View:** Instead of separate tabs, the main screen will feature a grid of "Process Cards".
- **Process Cards:**
    - Laser (DXF + Excel)
    - Proteções (DXF + Excel)
    - Router (STEP + Excel)
    - CNC (STEP + Excel)
    - Torno (STEP + Excel)
    - Lista de Material (BOM)
    - Perfis de Alumínio
- **Card States:**
    - `Pending`: Neutral color.
    - `Processing`: Pulsing or animated border/icon.
    - `Completed`: Green checkmark.
    - `Error`: Red exclamation mark.
- **Top Action Bar:**
    - Persistent Assembly Path selector (.sldasm).
    - Large **"GERAR TUDO"** (Generate All) button.
    - Filter Icon: Opens a quick toggle list to enable/disable specific cards for the current run.

### 2.2 Modal Progress Hub (Execution Phase)
- **Overlay:** When "Gerar Tudo" is clicked, a semi-transparent dark overlay covers the Dashboard.
- **Central Progress Hub:**
    - **Global Progress Bar:** Shows overall completion percentage.
    - **Informative Log:** A scrolling text area with timestamps and human-readable events (e.g., "Exporting: Base_Bracket (Part 12 of 30)").
    - **Color Coding:** Green (Success), Yellow (Warning), Red (Error).
- **"Hold to Cancel" Button:**
    - A red circular button.
    - **Mechanism:** User must press and hold for 2 seconds to trigger cancellation.
    - **Visual Feedback:** A stroke around the circle fills up while pressed. If released early, the progress is saved/continued.

### 2.3 Enhanced Logging & Feedback
- **Process-Specific Logs:** Clicking on an "Error" card after a run will filter the central log to show only errors related to that specific process.
- **Report Generation:** At the end of the run, a summary report is displayed (Total parts, total errors, time elapsed).

## 3. Technical Implementation Strategy

### 3.1 GUI Framework
- **Tkinter (Standard):** Leverage `tk.Canvas` for the circular "Hold to Cancel" button and custom card styles to maintain light dependency weight.
- **Theming:** Maintain the existing dark theme (Nord-inspired palette) but improve spacing and font hierarchy.

### 3.2 Threading & Control
- **Execution Thread:** SolidWorks COM operations run in a background thread.
- **GUI Thread:** Remains responsive to handle the "Hold" gesture and log updates.
- **Cancellation Event:** The "Hold" gesture sets a `threading.Event` that the SolidWorks worker checks between operations to stop gracefully.

### 3.3 Folder Management
- **Persistence:** Use a local config file (JSON) to save the last used output folder and active filters.

## 4. Success Criteria
- [ ] User can generate all production files with a single click.
- [ ] User can selectively run only "Laser" or "Torno" without navigating tabs.
- [ ] Accidental clicks on "Cancel" do not stop the process.
- [ ] The log is readable and provides clear progress on part counts.
- [ ] Interface remains responsive throughout the export cycle.
