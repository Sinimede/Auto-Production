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

---

### Tomorrow's Strategy (March 23, 2026)

**Goal:** Expand PDM capabilities into Versioning and Assembly Tree Visualization.

#### Task 1: Version Control Improvements
- [ ] **Manual Versioning:** Implement a "New Version" button in the Data Card to increment the `revision` (e.g., from 00 to 01) and archive the old file in a `.versions/` hidden folder.
- [ ] **Visual Diff (BOM):** Compare the BOM of the current version with a previous one to highlight added/removed components.

#### Task 2: Assembly Tree View
- [ ] **Recursive Tree Builder:** Create a new widget to display the full assembly structure (tree) by recursively calling `get_dependencies`.
- [ ] **Batch Sync:** Implement a "Sync All" for the entire assembly tree, using the new Fast Sync logic to update the database for hundreds of files in seconds.

#### Task 3: UI/UX Refinement
- [ ] **Status Icons:** Add icons to the file table (e.g., a lock icon for checked-out files, a green check for approved files).
- [ ] **Async Sync:** Move the SolidWorks Sync process to a background thread to prevent the UI from freezing during the 3.5s COM calls.

---

### Preparations for Tomorrow
1. **Environment:** Ensure `olefile` is installed (`pip install -r requirements.txt`).
2. **Database:** The `file_metadata` table now includes `last_synced_hash`.
3. **SolidWorks:** Ensure SW 2024 is running for Task 2 (Assembly Tree).

**End of Session.**
