"""Independent fictional scan gold; images are generated locally, never downloaded."""
from io import BytesIO

TITLE = '完全虚构劳动合同明细表'
HEADERS = ['劳动者', '合同期限', '合同工资']
FIRST = [['周明', '24个月', '12000元'], ['李华', '36个月', '15000元']]
SECOND = [['陈平', '12个月', '9000元'], ['赵宁', '48个月', '18000元']]
OTHER = [['王安', '18个月', '8000元'], ['周明', '24个月', '12000元']]


def table_image(title, rows):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1200, 620), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 36)
    draw.text((65, 65), title, font=font, fill='black')
    xs = [60, 420, 780, 1140]
    ys = [170 + i * 90 for i in range(len(rows) + 1)]
    for x in xs: draw.line((x, ys[0], x, ys[-1]), fill='black', width=3)
    for y in ys: draw.line((xs[0], y, xs[-1], y), fill='black', width=3)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            draw.text((xs[c] + 20, ys[r] + 22), value, font=font, fill='black')
    return image


def continued_pdf(destination):
    images = [table_image(TITLE, [HEADERS, *FIRST]),
              table_image(TITLE + '（续表）', SECOND),
              table_image('完全虚构另一份明细表', OTHER)]
    try: images[0].save(destination, format='PDF', resolution=144, save_all=True, append_images=images[1:])
    finally:
        for image in images: image.close()


def native_pdf():
    text = b'BT /F1 18 Tf 30 275 Td (SYNTHETIC-NATIVE-2026) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 310] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(text)).encode() + b' >>\nstream\n' + text + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    raw = bytearray(b'%PDF-1.4\n'); offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(raw)); raw.extend(f'{number} 0 obj\n'.encode() + body + b'\nendobj\n')
    start = len(raw); raw.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets: raw.extend(f'{offset:010d} 00000 n \n'.encode())
    raw.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    return bytes(raw)


def mixed_pdf(destination):
    import pypdfium2 as pdfium
    image = table_image('完全虚构混合页面', [HEADERS, FIRST[0]])
    jpeg = BytesIO()
    try: image.save(jpeg, format='JPEG', quality=95)
    finally: image.close()
    with pdfium.PdfDocument(native_pdf()) as document:
        page = document[0]
        bitmap = pdfium.PdfImage.new(document)
        bitmap.load_jpeg(BytesIO(jpeg.getvalue()))
        bitmap.set_matrix(pdfium.PdfMatrix(600, 0, 0, 260, 0, 0))
        page.insert_obj(bitmap); page.gen_content(); page.close(); document.save(destination)


def inline_mixed_pdf(destination):
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (450, 60), 'white')
    ImageDraw.Draw(image).text((5, 3), 'SCANNED BODY', font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 40), fill='black')
    jpeg = BytesIO()
    try: image.save(jpeg, format='JPEG', quality=95)
    finally: image.close()
    with pdfium.PdfDocument(native_pdf()) as document:
        page = document[0]; bitmap = pdfium.PdfImage.new(document)
        bitmap.load_jpeg(BytesIO(jpeg.getvalue()))
        bitmap.set_matrix(pdfium.PdfMatrix(225, 0, 0, 30, 350, 264))
        page.insert_obj(bitmap); page.gen_content(); page.close(); document.save(destination)
