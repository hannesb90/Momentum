import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf

def test():
    import concurrent.futures
    import threading
    import time

    pdf_bytes = b"%PDF"
    def my_download(url):
        return pdf_bytes
    mfn_pdf._download_pdf = my_download

    def my_extract(b):
        return ("Hello World", 1)
    mfn_pdf.extract_pdf_text = my_extract

    # We mock fetch_extract_isolated entirely? No, we want to see why it hangs in ThreadPool

    urls = ["http://example.com/1", "http://example.com/2", "http://example.com/3"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(mfn_pdf.fetch_extract_isolated, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
