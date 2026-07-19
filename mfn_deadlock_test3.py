import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import threading
import time
import concurrent.futures
import requests

def test():
    def spam_requests():
        while True:
            try:
                requests.get("http://localhost:12345", timeout=0.01)
            except Exception:
                pass

    t = threading.Thread(target=spam_requests, daemon=True)
    t.start()

    # Do we deadlock?
    urls = [f"http://example.com/{i}" for i in range(10)]

    def mock_download(url):
        try:
            requests.get("http://localhost:12345", timeout=0.01)
        except Exception:
            pass
        return b"%PDF"

    mfn_pdf._download_pdf = mock_download
    mfn_pdf.extract_pdf_text = lambda x: ("Hello", 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(mfn_pdf.fetch_extract_isolated, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures, timeout=5):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
