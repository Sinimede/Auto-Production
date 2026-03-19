"""
test_step_15024.py -- Export STEP para o assembly 15024.100.900 (ativo no SW).
Mesmo fluxo que test_step.py mas com o caminho correto.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Patch ASM_PATH antes de importar main
import test_step as ts

ROOT     = r"C:\Users\Micael\Desktop\15024 - Pack and Go conj 100"
ts.ASM_PATH = os.path.normpath(os.path.join(ROOT, "15024.100.900.SLDASM"))
ts.OUT_DIR  = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Resultados"))
ts.TMP_DIR  = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".tmp"))

if __name__ == "__main__":
    ts.main()
