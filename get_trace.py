import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import queue
import time

def test():
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    q = ctx.Queue()

    def my_worker(url, q):
        try:
            print("Running in worker...")
            q.put(("ok", "test"))
        except Exception as e:
            q.put(("error", str(e)))

    p = ctx.Process(target=my_worker, args=("test", q))
    p.start()

    print(q.get())
    p.join()

if __name__ == "__main__":
    test()
