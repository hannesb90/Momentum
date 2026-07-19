import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import queue

def test():
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    q = ctx.Queue()

    # Run the real worker but pass fake URL and intercept my_download and my_extract globally

    def my_download(url):
        print("Mock downloading inside worker...")
        return b"%PDF"

    mfn_pdf._download_pdf = my_download

    def my_extract(b):
        return ("Hello World", 1)

    mfn_pdf.extract_pdf_text = my_extract

    p = ctx.Process(target=mfn_pdf._fetch_extract_worker, args=("http://example.com", q))
    p.start()

    try:
        status, payload = q.get(timeout=2)
        print(f"Got: {status} {payload}")
    except queue.Empty:
        print("Timeout getting from queue")

    p.join(1)

if __name__ == "__main__":
    test()
