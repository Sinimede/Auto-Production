# SWAT-PDM Sync & Performance Optimization Plan

> **Date:** March 22, 2026
> **Status:** Accomplished today. Ready for further PDM expansion.

**Goal:** Resolve SolidWorks 2024 COM integration errors and optimize the metadata sync process for professional responsiveness.

---

### Accomplishments (Today)

#### 1. SolidWorks 2024 COM Fixes
- [x] **Resolved VARIANT Error:** Fixed `int() argument must be a string... not 'VARIANT'` by passing `0, 0` for errors/warnings in `OpenDoc6` and manually unpacking the result tuple.
- [x] **Restored `get_dependencies`:** Fixed a broken method header in `src/core/solidworks.py` that was causing sync failures.
- [x] **Code Cleanup:** Removed duplicated and incomplete `get_all_parts` methods in `SolidWorksClient`.

#### 2. Performance Optimization (Fast Sync)
- [x] **Persistent Connection:** Updated `SolidWorksClient.connect()` to reuse existing `ISldWorks` instances, avoiding expensive reconnection overhead.
- [x] **Hash-Based Caching:** 
    - Added `last_synced_hash` to `file_metadata` database table.
    - Implemented MD5 hashing in `SolidWorksClient`.
    - Updated `on_sync_data_card` to skip the sync process if the file hasn't changed (near-instant response for unchanged files).
- [x] **Hybrid Sync Strategy:** 
    - Implemented `get_custom_properties_fast` using `olefile` for closed files (bypassing SW entirely for most metadata).
    - Maintained full SolidWorks COM fallback for open files or complex dynamic properties.
- [x] **Dependency Management:** Added `olefile` to `requirements.txt`.

#### 3. PDM Evolution (Versioning & Trees)
- [x] **Immutable Versioning:** Every Check-In now increments the internal version (1, 2, 3...) and creates a snapshot in a hidden `.versions/` directory.
- [x] **Assembly Tree View:** Added a new tab in the Data Card to visualize the assembly hierarchy recursively from the database.
- [x] **Batch Sync:** Implemented "Sync All" for assembly trees, allowing one-click metadata updates for hundreds of components.
- [x] **Asynchronous Execution:** Moved the SolidWorks sync process to a background thread (`QThread` + `Worker`), ensuring the PDM UI remains responsive during long COM calls.

---

### Pending Tasks (Next Session)

#### Task 1: Version Control Improvements
- [ ] **Visual Diff (BOM):** Compare the BOM of the current version with a previous one to highlight added/removed components.
- [ ] **Restore Version:** Add capability to revert the current file to an older version from the `.versions/` archive.

#### Task 2: UI/UX Refinement
- [ ] **Status Icons:** Add icons to the file table (e.g., a lock icon for checked-out files, a green check for approved files).
- [ ] **Data Card Validation:** Highlight missing mandatory properties (like Description or Material) in red.
