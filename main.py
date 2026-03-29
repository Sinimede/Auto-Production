import sys
import os

# Add src to python path to allow imports like 'from src.core...'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.pdm.app import main

if __name__ == "__main__":
    main()
