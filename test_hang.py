import concurrent.futures
import time
import requests
import multiprocessing as mp
import threading

def worker(url, q):
    try:
        r = requests.get(url, timeout=5)
        q.put(("ok", len(r.content)))
    except Exception as e:
        q.put(("error", str(e)))

def process_isolated(url):
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    p = ctx.Process(target=worker, args=(url, q))
    p.start()

    deadline = time.time() + 10
    result = None
    while time.time() < deadline:
        try:
            status, payload = q.get(timeout=0.5)
            result = payload
            break
        except Exception:
            if not p.is_alive():
                break

    if p.is_alive():
        p.terminate()
    p.join(1)
    q.close()
    try:
        q.join_thread()
    except Exception:
        pass
    print(f"Done processing {url}")
    return result

def main():
    urls = ["https://example.com"] * 10
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process_isolated, url) for url in urls]
        for f in concurrent.futures.as_completed(futures):
            f.result()

if __name__ == "__main__":
    main()
