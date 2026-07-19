import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import threading
import time
import concurrent.futures

def test():
    # Keep the original mfn_pdf logic mostly intact, but mock _download_pdf and extract
    pdf_bytes = b"%PDF"
    def my_download(url):
        time.sleep(0.1)
        return pdf_bytes
    mfn_pdf._download_pdf = my_download

    def my_extract(b):
        return ("Hello", 1)
    mfn_pdf.extract_pdf_text = my_extract

    # We want to create a situation where `fork` deadlocks.
    # Let's introduce a background thread that frequently acquires the `logging` lock
    import logging
    log = logging.getLogger("dummy")

    def spam_logging():
        while True:
            log.info("spam")

    t = threading.Thread(target=spam_logging, daemon=True)
    t.start()

    urls = [f"http://example.com/{i}" for i in range(10)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(mfn_pdf.fetch_extract_isolated, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures, timeout=5):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
