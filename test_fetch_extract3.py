import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf

def test():
    pdf_bytes = b"%PDF"

    def my_download(url):
        print("Mock downloading...")
        return pdf_bytes

    mfn_pdf._download_pdf = my_download

    def my_extract(b):
        return ("Hello World", 1)

    mfn_pdf.extract_pdf_text = my_extract

    print("running original function...")
    print(mfn_pdf.fetch_extract_isolated("http://example.com"))

if __name__ == "__main__":
    test()
