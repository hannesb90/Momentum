import multiprocessing as mp
import threading
import time
import requests

def child_worker(q):
    print("child started")
    import sys
    print("child sys loaded")
    import csv
    print("child csv loaded")
    import ssl
    print("child ssl loaded")
    try:
        r = requests.get("https://google.com", timeout=2)
        print("child request loaded")
    except Exception as e:
        print(f"child request failed {e}")
    q.put("child done")

def process_isolated():
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    p = ctx.Process(target=child_worker, args=(q,))
    p.start()

    try:
        print(q.get(timeout=2))
    except Exception as e:
        print("timeout in parent")

    p.terminate()
    p.join()

if __name__ == "__main__":
    process_isolated()
