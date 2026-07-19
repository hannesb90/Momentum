import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import queue
import time

def test():
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    q = ctx.Queue()

    def worker(q):
        try:
            print("Worker starting...")
            q.put(("ok", ("hello", 1)))
            print("Worker done putting.")
        except Exception as e:
            print(f"Worker error: {e}")

    p = ctx.Process(target=worker, args=(q,))
    p.start()

    try:
        status, payload = q.get(timeout=2)
        print(f"Got: {status} {payload}")
    except queue.Empty:
        print("Timeout getting from queue")

    p.join(1)

if __name__ == "__main__":
    test()
