import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf
import threading
import concurrent.futures
import time

def test():
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n/Resources <<\n/Font <<\n/F1 5 0 R\n>>\n>>\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 24 Tf\n100 100 Td\n(Hello World) Tj\nET\nendstream\nendobj\n5 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000216 00000 n\n0000000305 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n393\n%%EOF"

    def my_download(url):
        return pdf_bytes

    mfn_pdf._download_pdf = my_download

    # Run fetch_extract_isolated in a ThreadPoolExecutor
    # to simulate backfill calling it while another thread handles pace locking

    lock = threading.Lock()
    def process_candidate(url):
        with lock:
            time.sleep(0.01) # paced
        return mfn_pdf.fetch_extract_isolated(url)

    urls = [f"http://example.com/{i}" for i in range(10)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(process_candidate, url): url for url in urls}
        for f in concurrent.futures.as_completed(futures):
            print(futures[f], f.result())

if __name__ == "__main__":
    test()
