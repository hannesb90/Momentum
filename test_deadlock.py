import multiprocessing as mp
import threading
import time
import sys

lock = threading.Lock()

def worker(q):
    q.put("worker started")
    with lock:
        q.put("worker got lock")

def thread_func():
    with lock:
        ctx = mp.get_context("fork")
        q = ctx.Queue()
        p = ctx.Process(target=worker, args=(q,))
        p.start()
        time.sleep(1) # hold lock while child starts

    print("parent waiting for child")
    print(q.get())
    print(q.get(timeout=2))
    p.join()

if __name__ == "__main__":
    t = threading.Thread(target=thread_func)
    t.start()
    t.join()
