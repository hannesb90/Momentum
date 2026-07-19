import multiprocessing as mp
import threading
import time

def child_worker():
    print("child starting")
    import sys # try to import
    print("child done")

def thread_forker():
    for _ in range(10):
        ctx = mp.get_context("fork")
        p = ctx.Process(target=child_worker)
        p.start()
        p.join()

def thread_importer():
    for _ in range(100):
        import xml.etree.ElementTree
        import html.parser
        import urllib.request
        time.sleep(0.01)

if __name__ == "__main__":
    t1 = threading.Thread(target=thread_forker)
    t2 = threading.Thread(target=thread_importer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("All done")
