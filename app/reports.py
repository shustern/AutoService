from html import escape

from app.models import WorkOrder


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ") + " руб."


def _render_order_html(order: WorkOrder) -> str:
    works_rows = []
    for item in order.works:
        work = item.work
        price = work.standard_hours * work.hourly_rate * item.quantity
        works_rows.append(
            "<tr>"
            f"<td>{escape(work.name)}</td>"
            f"<td>{item.quantity}</td>"
            f"<td>{work.standard_hours:g}</td>"
            f"<td>{_money(work.hourly_rate)}</td>"
            f"<td>{_money(price)}</td>"
            "</tr>"
        )

    parts_rows = []
    for item in order.parts:
        part = item.part
        price = part.price * item.quantity_used
        parts_rows.append(
            "<tr>"
            f"<td>{escape(part.name)}</td>"
            f"<td>{escape(part.sku or '')}</td>"
            f"<td>{item.quantity_reserved:g}</td>"
            f"<td>{item.quantity_used:g}</td>"
            f"<td>{_money(part.price)}</td>"
            f"<td>{_money(price)}</td>"
            "</tr>"
        )

    works_table = "".join(works_rows) or '<tr><td colspan="5">Работы не добавлены</td></tr>'
    parts_table = "".join(parts_rows) or '<tr><td colspan="6">Запчасти не добавлены</td></tr>'

    return f"""<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Заказ-наряд #{order.id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; }}
        h1 {{ margin-bottom: 8px; }}
        .meta {{ margin-bottom: 24px; line-height: 1.5; }}
        table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
        th {{ background: #f3f3f3; }}
        .total {{ font-size: 20px; font-weight: bold; text-align: right; }}
    </style>
</head>
<body>
    <h1>Заказ-наряд #{order.id}</h1>
    <div class="meta">
        <div><b>Дата:</b> {order.created_at.strftime('%d.%m.%Y %H:%M')}</div>
        <div><b>Статус:</b> {escape(order.status.value)}</div>
        <div><b>Клиент:</b> {escape(order.client.name)} ({escape(order.client.phone)})</div>
        <div><b>Автомобиль:</b> {escape(order.car.model)} / {escape(order.car.license_plate)}</div>
    </div>

    <h2>Работы</h2>
    <table>
        <thead>
            <tr><th>Наименование</th><th>Кол-во</th><th>Нормо-часы</th><th>Ставка</th><th>Сумма</th></tr>
        </thead>
        <tbody>{works_table}</tbody>
    </table>

    <h2>Запчасти</h2>
    <table>
        <thead>
            <tr><th>Наименование</th><th>Артикул</th><th>Резерв</th><th>Использовано</th><th>Цена</th><th>Сумма</th></tr>
        </thead>
        <tbody>{parts_table}</tbody>
    </table>

    <div class="total">Итого: {_money(order.total_cost)}</div>
</body>
</html>"""


def generate_order_document(order_id: int, fmt: str = "html"):
    """Сформировать печатную форму заказ-наряда."""
    order = WorkOrder.query.get(order_id)
    if not order:
        return None

    html = _render_order_html(order)
    if fmt == "html":
        return html
    if fmt == "pdf":
        # Минимальный PDF без внешних зависимостей. Для печати с HTML-разметкой
        # можно подключить WeasyPrint или xhtml2pdf.
        text = (
            f"Заказ-наряд #{order.id}\n"
            f"Клиент: {order.client.name}\n"
            f"Автомобиль: {order.car.model} / {order.car.license_plate}\n"
            f"Статус: {order.status.value}\n"
            f"Итого: {_money(order.total_cost)}"
        )
        stream = "BT /F1 12 Tf 72 760 Td " + _pdf_escape(text).replace("\n", ") Tj T* (") + ") Tj ET"
        content = stream.encode("cp1251", errors="replace")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
        ]
        return _build_pdf(objects)
    return None


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(objects: list[bytes]) -> bytes:
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii")
    )
    return bytes(pdf)
