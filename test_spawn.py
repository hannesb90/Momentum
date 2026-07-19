import multiprocessing as mp
import threading
import time

lock = threading.Lock()

def child_worker(q):
    q.put("child started")
    q.put("child done")

def process_isolated():
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=child_worker, args=(q,))
    p.start()

    try:
        print(q.get(timeout=2))
        print(q.get(timeout=2))
    except Exception as e:
        print("timeout in parent")

    p.terminate()
    p.join()

def thread_func():
    while True:
        with lock:
            time.sleep(0.01)

if __name__ == "__main__":
    t = threading.Thread(target=thread_func)
    t.daemon = True
    t.start()

    for _ in range(5):
        process_isolated()
