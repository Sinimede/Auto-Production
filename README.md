# Auto Production

Auto Production is an automation suite for **SolidWorks** using **Python** and the **win32com** (COM API) library. It focuses on streamlining the production lifecycle by automating the export of DXF/STEP files, generating Bill of Materials (BOM), and managing supplier data.

## Features

- **Unified Exporter GUI:** A desktop application to manage DXF (for Laser) and STEP (for CNC/Router) exports.
- **Standalone DXF Exporter:** A focused tool for quick DXF generation.
- **Supplier Management:** Tools for looking up and managing supplier data.
- **Post-Processing:** Automated rules engine for geometry and data validation.

## Prerequisites

- **Operating System:** Windows (required for SolidWorks COM API)
- **SolidWorks:** Version 2024 or later (must be running for most tools)
- **Python:** 3.x

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/Sinimede/Auto-Production.git
    cd Auto-Production
    ```

2.  Install dependencies:
    ```bash
    pip install -r tools/exporter/requirements.txt
    ```
    *Note: Dependencies include `pywin32`, `ezdxf`, `openpyxl`, and `tkinter`.*

## Usage

### Launch Unified GUI
To start the main application for DXF and STEP exports:
```bash
python tools/exporter/main.py
```

### Run Standalone DXF Exporter
For the dedicated DXF export tool:
```bash
python tools/dxf_exporter/main.py
```

### Post-Process Rules
To apply post-processing rules:
```bash
run_post_process.bat
```

## Project Structure

- `tools/`: Python implementation logic.
  - `exporter/`: Main GUI and core logic.
  - `dxf_exporter/`: Standalone DXF tool.
  - `fornecedores/`: Supplier management tools.
  - `post_process/`: Post-processing scripts.
- `docs/`: Technical guides, design specs, and implementation plans.
- `assets/`: Excel and SolidWorks templates for reports and BOMs (formerly Templates/).
- `Resultados/`: Default output directory for exports.

## Documentation

For detailed technical information, including SolidWorks COM API quirks and development conventions, please refer to [docs/project-guide.md](docs/project-guide.md).

## Contributing

1.  Create a feature branch.
2.  Commit your changes.
3.  Push to the branch.
4.  Open a Pull Request.

## License

[Add License Information Here]
