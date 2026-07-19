import sys
from pathlib import Path
sys.path.insert(0, str(Path("momentum_ml").resolve()))
from altdata import mfn_pdf

def test():
    # Make a tiny real PDF file to let spawn worker download it from a local server
    pass

if __name__ == "__main__":
    import threading
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "application/pdf")
            self.end_headers()
            self.wfile.write(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n/Resources <<\n/Font <<\n/F1 5 0 R\n>>\n>>\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 24 Tf\n100 100 Td\n(Hello World) Tj\nET\nendstream\nendobj\n5 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000216 00000 n\n0000000305 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n393\n%%EOF")

    httpd = socketserver.TCPServer(("", 12345), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    print(mfn_pdf.fetch_extract_isolated("http://localhost:12345/test.pdf"))
