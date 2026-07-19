import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import threading
import time
import concurrent.futures

def test():
    pdf_bytes = b"%PDF"
    def my_download(url):
        time.sleep(0.1)
        return pdf_bytes
    mfn_pdf._download_pdf = my_download

    def my_extract(b):
        return ("Hello World", 1)
    mfn_pdf.extract_pdf_text = my_extract

    urls = [f"http://example.com/{i}" for i in range(10)]

    lock = threading.Lock()
    def background():
        while True:
            with lock:
                time.sleep(0.01)
    t = threading.Thread(target=background, daemon=True)
    t.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        def paced_process(url):
            with lock:
                time.sleep(0.01)
            return mfn_pdf.fetch_extract_isolated(url)

        futures = {executor.submit(paced_process, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
