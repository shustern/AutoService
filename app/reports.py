from html import escape
import os
import struct

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
        <div><b>Мастер:</b> {escape(order.mechanic.name if order.mechanic else 'не назначен')}</div>
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
        return _render_order_pdf(order)
    return None


def _render_order_pdf(order: WorkOrder) -> bytes:
    font_path = _find_pdf_font()
    font = _TrueTypeFont(font_path)
    page = _PdfPage(font)

    page.text(40, 802, f"Заказ-наряд #{order.id}", 22, bold=True)
    page.text(40, 774, f"Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}", 11)
    page.text(40, 756, f"Статус: {order.status.value}", 11)
    page.text(40, 738, f"Клиент: {order.client.name} ({order.client.phone})", 11)
    page.text(40, 720, f"Автомобиль: {order.car.model} / {order.car.license_plate}", 11)
    page.text(40, 702, f"Мастер: {order.mechanic.name if order.mechanic else 'не назначен'}", 11)

    y = 666
    y = page.section_table(
        "Работы",
        ["Наименование", "Кол-во", "Н/ч", "Ставка", "Сумма"],
        [
            [
                item.work.name,
                str(item.quantity),
                f"{item.work.standard_hours:g}",
                _money(item.work.hourly_rate),
                _money(item.work.standard_hours * item.work.hourly_rate * item.quantity),
            ]
            for item in order.works
        ],
        [235, 55, 55, 90, 90],
        y,
        empty_text="Работы не добавлены",
    )

    y = page.section_table(
        "Запчасти",
        ["Наименование", "Артикул", "Резерв", "Исп.", "Цена", "Сумма"],
        [
            [
                item.part.name,
                item.part.sku or "",
                f"{item.quantity_reserved:g}",
                f"{item.quantity_used:g}",
                _money(item.part.price),
                _money(item.part.price * item.quantity_used),
            ]
            for item in order.parts
        ],
        [180, 80, 55, 45, 80, 85],
        y,
        empty_text="Запчасти не добавлены",
    )

    page.line(40, max(y - 8, 64), 555, max(y - 8, 64), color=(0.75, 0.78, 0.82))
    page.text(390, max(y - 34, 42), f"Итого: {_money(order.total_cost)}", 16, bold=True)
    return page.build()


def _find_pdf_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\times.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError("Не найден системный TTF-шрифт для PDF")


class _TrueTypeFont:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as file:
            self.data = file.read()
        self.tables = self._read_tables()
        self.units_per_em, self.bbox = self._read_head()
        self.ascent, self.descent, self.number_of_h_metrics = self._read_hhea()
        self.advances = self._read_hmtx()
        self.cmap = self._read_cmap()
        self.used_glyphs = {0}

    def glyph_id(self, char: str) -> int:
        gid = self.cmap.get(ord(char), self.cmap.get(ord("?"), 0))
        self.used_glyphs.add(gid)
        return gid

    def width(self, gid: int) -> int:
        if gid < len(self.advances):
            return max(1, round(self.advances[gid] * 1000 / self.units_per_em))
        return 500

    def text_hex(self, value: str) -> str:
        return "".join(f"{self.glyph_id(char):04X}" for char in value)

    def _table(self, tag: str) -> bytes:
        offset, length = self.tables[tag]
        return self.data[offset:offset + length]

    def _read_tables(self):
        num_tables = struct.unpack(">H", self.data[4:6])[0]
        tables = {}
        offset = 12
        for _ in range(num_tables):
            tag = self.data[offset:offset + 4].decode("latin1")
            table_offset, length = struct.unpack(">II", self.data[offset + 8:offset + 16])
            tables[tag] = (table_offset, length)
            offset += 16
        return tables

    def _read_head(self):
        table = self._table("head")
        units = struct.unpack(">H", table[18:20])[0]
        bbox = struct.unpack(">hhhh", table[36:44])
        return units, bbox

    def _read_hhea(self):
        table = self._table("hhea")
        ascent, descent = struct.unpack(">hh", table[4:8])
        metrics = struct.unpack(">H", table[34:36])[0]
        return ascent, descent, metrics

    def _read_hmtx(self):
        table = self._table("hmtx")
        advances = []
        for index in range(self.number_of_h_metrics):
            advances.append(struct.unpack(">H", table[index * 4:index * 4 + 2])[0])
        return advances

    def _read_cmap(self):
        table = self._table("cmap")
        count = struct.unpack(">H", table[2:4])[0]
        records = []
        for index in range(count):
            start = 4 + index * 8
            platform, encoding, offset = struct.unpack(">HHI", table[start:start + 8])
            fmt = struct.unpack(">H", table[offset:offset + 2])[0]
            records.append((platform, encoding, fmt, offset))

        for platform, encoding, fmt, offset in records:
            if fmt == 12 and platform == 3:
                return self._parse_cmap12(table[offset:])
        for platform, encoding, fmt, offset in records:
            if fmt == 4 and platform == 3:
                return self._parse_cmap4(table[offset:])
        raise RuntimeError("Шрифт не содержит подходящую cmap-таблицу")

    def _parse_cmap12(self, data):
        groups = struct.unpack(">I", data[12:16])[0]
        cmap = {}
        pos = 16
        for _ in range(groups):
            start_char, end_char, start_gid = struct.unpack(">III", data[pos:pos + 12])
            for code in range(start_char, end_char + 1):
                cmap[code] = start_gid + (code - start_char)
            pos += 12
        return cmap

    def _parse_cmap4(self, data):
        seg_count = struct.unpack(">H", data[6:8])[0] // 2
        end_pos = 14
        start_pos = end_pos + seg_count * 2 + 2
        delta_pos = start_pos + seg_count * 2
        range_pos = delta_pos + seg_count * 2
        cmap = {}
        for index in range(seg_count):
            end_code = struct.unpack(">H", data[end_pos + index * 2:end_pos + index * 2 + 2])[0]
            start_code = struct.unpack(">H", data[start_pos + index * 2:start_pos + index * 2 + 2])[0]
            delta = struct.unpack(">h", data[delta_pos + index * 2:delta_pos + index * 2 + 2])[0]
            range_offset = struct.unpack(">H", data[range_pos + index * 2:range_pos + index * 2 + 2])[0]
            for code in range(start_code, end_code + 1):
                if code == 0xFFFF:
                    continue
                if range_offset == 0:
                    gid = (code + delta) & 0xFFFF
                else:
                    glyph_offset = range_pos + index * 2 + range_offset + (code - start_code) * 2
                    if glyph_offset + 2 > len(data):
                        continue
                    gid = struct.unpack(">H", data[glyph_offset:glyph_offset + 2])[0]
                    if gid:
                        gid = (gid + delta) & 0xFFFF
                cmap[code] = gid
        return cmap


class _PdfPage:
    def __init__(self, font: _TrueTypeFont):
        self.font = font
        self.commands = []

    def text(self, x, y, value, size=11, bold=False, color=(0.08, 0.11, 0.16)):
        if not value:
            return
        self.commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg")
        self.commands.append(f"BT /F1 {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm <{self.font.text_hex(str(value))}> Tj ET")
        if bold:
            self.commands.append(f"BT /F1 {size} Tf 1 0 0 1 {x + 0.35:.2f} {y:.2f} Tm <{self.font.text_hex(str(value))}> Tj ET")

    def rect(self, x, y, width, height, fill=(1, 1, 1), stroke=(0.82, 0.84, 0.88)):
        self.commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        self.commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re B")

    def line(self, x1, y1, x2, y2, color=(0.82, 0.84, 0.88)):
        self.commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG")
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def section_table(self, title, headers, rows, widths, y, empty_text):
        self.text(40, y, title, 15, bold=True)
        y -= 26
        row_height = 24
        x = 40
        for header, width in zip(headers, widths):
            self.rect(x, y, width, row_height, fill=(0.94, 0.96, 0.98))
            self.text(x + 5, y + 8, header, 8, bold=True, color=(0.35, 0.40, 0.48))
            x += width
        y -= row_height

        if not rows:
            self.rect(40, y, sum(widths), row_height)
            self.text(46, y + 8, empty_text, 10)
            return y - 46

        for row in rows:
            wrapped = [_wrap_pdf_text(str(cell), max(8, int(width / 5.6))) for cell, width in zip(row, widths)]
            height = max(row_height, 15 * max(len(lines) for lines in wrapped) + 10)
            if y - height < 70:
                self.text(40, y - 14, "Продолжение таблицы не помещается на страницу", 9, color=(0.55, 0.20, 0.18))
                return 58
            x = 40
            for lines, width in zip(wrapped, widths):
                self.rect(x, y - height + row_height, width, height)
                for index, line in enumerate(lines[:4]):
                    self.text(x + 5, y + 7 - index * 13, line, 8.5)
                x += width
            y -= height
        return y - 34

    def build(self) -> bytes:
        content = "\n".join(self.commands).encode("ascii")
        return _build_pdf_document(content, self.font)


def _wrap_pdf_text(value: str, width: int):
    words = value.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _build_pdf_document(content: bytes, font: _TrueTypeFont) -> bytes:
    font_file_obj = 8
    descriptor_obj = 7
    cidfont_obj = 6
    tounicode_obj = 5
    type0_obj = 4
    content_obj = 3
    page_obj = 2
    pages_obj = 9
    catalog_obj = 1

    used = sorted(font.used_glyphs)
    widths = " ".join(f"{gid} [{font.width(gid)}]" for gid in used if gid)
    bbox = " ".join(str(round(value * 1000 / font.units_per_em)) for value in font.bbox)
    ascent = round(font.ascent * 1000 / font.units_per_em)
    descent = round(font.descent * 1000 / font.units_per_em)

    objects = {
        catalog_obj: b"<< /Type /Catalog /Pages 9 0 R >>",
        page_obj: b"<< /Type /Page /Parent 9 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 3 0 R >>",
        content_obj: _pdf_stream(content),
        type0_obj: b"<< /Type /Font /Subtype /Type0 /BaseFont /ArialEmbedded /Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 5 0 R >>",
        tounicode_obj: _pdf_stream(_to_unicode_cmap(font).encode("ascii")),
        cidfont_obj: f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ArialEmbedded /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 7 0 R /W [ {widths} ] /CIDToGIDMap /Identity >>".encode("ascii"),
        descriptor_obj: f"<< /Type /FontDescriptor /FontName /ArialEmbedded /Flags 32 /FontBBox [{bbox}] /Ascent {ascent} /Descent {descent} /CapHeight {ascent} /ItalicAngle 0 /StemV 80 /FontFile2 8 0 R >>".encode("ascii"),
        font_file_obj: _pdf_stream(font.data),
        pages_obj: b"<< /Type /Pages /Kids [2 0 R] /Count 1 >>",
    }
    return _build_pdf([objects[index] for index in range(1, 10)])


def _pdf_stream(data: bytes) -> bytes:
    return b"<< /Length " + str(len(data)).encode("ascii") + b" >>\nstream\n" + data + b"\nendstream"


def _to_unicode_cmap(font: _TrueTypeFont) -> str:
    reverse = {}
    for codepoint, gid in font.cmap.items():
        if gid in font.used_glyphs and gid not in reverse:
            reverse[gid] = codepoint
    pairs = sorted(reverse.items())
    chunks = []
    for index in range(0, len(pairs), 100):
        part = pairs[index:index + 100]
        body = "\n".join(f"<{gid:04X}> <{codepoint:04X}>" for gid, codepoint in part)
        chunks.append(f"{len(part)} beginbfchar\n{body}\nendbfchar")
    return "\n".join([
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /ArialEmbedded-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
        *chunks,
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ])


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
