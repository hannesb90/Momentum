import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import threading
import time
import concurrent.futures

def test():
    import urllib.request

    # We want to create a situation where `fork` deadlocks.
    # Let's introduce a background thread that frequently does urllib requests (it uses locks internally)

    def spam_urllib():
        while True:
            try:
                urllib.request.urlopen("http://localhost:12345", timeout=0.01)
            except Exception:
                pass

    t = threading.Thread(target=spam_urllib, daemon=True)
    t.start()

    # Do we deadlock?
    urls = [f"http://example.com/{i}" for i in range(10)]

    def mock_download(url):
        time.sleep(0.1)
        return b"%PDF"

    mfn_pdf._download_pdf = mock_download
    mfn_pdf.extract_pdf_text = lambda x: ("Hello", 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(mfn_pdf.fetch_extract_isolated, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures, timeout=5):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
