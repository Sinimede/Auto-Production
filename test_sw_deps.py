import os
import sys
# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'src')))

from core.solidworks import SolidWorksClient

def test_deps(file_path):
    sw = SolidWorksClient()
    try:
        sw.connect()
        print(f"Checking dependencies for: {file_path}")
        deps = sw.get_dependencies(file_path)
        if not deps:
            print("No dependencies found by SolidWorks.")
        else:
            print(f"Found {len(deps)} dependencies:")
            for d in deps:
                print(f" - {d}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test with a known assembly path
    # Example: r"C:\Users\Micael\Desktop\Auto Production\18026.00.903.SLDASM"
    path = input("Cole aqui o caminho completo de um .SLDASM: ").strip('"')
    test_deps(path)
