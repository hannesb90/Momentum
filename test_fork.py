import multiprocessing as mp
import threading
import time

def worker(q):
    q.put("ok")

def thread_func():
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    p = ctx.Process(target=worker, args=(q,))
    p.start()
    print("started process", p.pid)
    print(q.get())
    p.join()

if __name__ == "__main__":
    t1 = threading.Thread(target=thread_func)
    t2 = threading.Thread(target=thread_func)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
