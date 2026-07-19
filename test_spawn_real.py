import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf

def test():
    pdf_bytes = b"%PDF"

    # We must patch at the module level for spawn to see it?
    # Actually spawn starts a fresh Python process, so our monkey patches in the parent WON'T BE SEEN by the child!
    # Ah! That's why mock didn't work for spawn!

    pass

if __name__ == "__main__":
    print("Testing")
