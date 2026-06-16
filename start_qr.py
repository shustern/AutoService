import html
import socket
import threading
import webbrowser
from pathlib import Path

import qrcode
import qrcode.image.svg

from app.api import create_app


HOST = "0.0.0.0"
PORT = 5000
OUTPUT_DIR = Path(__file__).resolve().parent / "qr_access"


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        sock.close()


def create_qr_page(url):
    OUTPUT_DIR.mkdir(exist_ok=True)
    qr_path = OUTPUT_DIR / "auto_service_qr.svg"
    page_path = OUTPUT_DIR / "open_on_phone.html"

    qr = qrcode.QRCode(version=None, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(qr_path)

    safe_url = html.escape(url, quote=True)
    page_path.write_text(
        f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QR-доступ к автосервису</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: #f3f4f6;
      color: #111827;
      font-family: Arial, sans-serif;
    }}
    main {{
      width: min(460px, 100%);
      padding: 32px;
      text-align: center;
      background: white;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      box-shadow: 0 12px 35px rgba(17, 24, 39, 0.12);
    }}
    h1 {{ margin: 0 0 12px; font-size: 26px; }}
    p {{ margin: 8px 0 20px; color: #4b5563; line-height: 1.5; }}
    img {{ width: min(300px, 100%); height: auto; }}
    a {{ display: block; margin-top: 18px; color: #075985; font-weight: 700; }}
    small {{ display: block; margin-top: 18px; color: #6b7280; line-height: 1.45; }}
  </style>
</head>
<body>
  <main>
    <h1>Автосервис на телефоне</h1>
    <p>Подключите телефон к той же Wi-Fi сети и отсканируйте QR-код.</p>
    <img src="auto_service_qr.svg" alt="QR-код для открытия системы">
    <a href="{safe_url}">{safe_url}</a>
    <small>Не закрывайте окно запуска на компьютере, пока работаете с телефона.</small>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return page_path


if __name__ == "__main__":
    local_url = f"http://{get_local_ip()}:{PORT}"
    qr_page = create_qr_page(local_url)

    print()
    print("QR access is ready:")
    print(local_url)
    print("Phone and computer must be connected to the same Wi-Fi network.")
    print("Keep this window open while using the app.")
    print()

    threading.Timer(1.0, webbrowser.open, args=(qr_page.as_uri(),)).start()
    create_app().run(host=HOST, port=PORT, debug=False, use_reloader=False)
