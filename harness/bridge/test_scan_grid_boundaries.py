"""Controlled OCR input, real ruled pixels: text strokes must not invent columns."""
import json

import pytest

from material_scan import ocr_rows


@pytest.mark.parametrize('merged_header', [False, True])
def test_ruled_columns_ignore_short_text_strokes_and_keep_real_spans(merged_header):
    pytest.importorskip('cv2')
    from PIL import Image, ImageDraw

    image = Image.new('RGB', (1200, 620), 'white')
    draw = ImageDraw.Draw(image)
    xs = [60, 420, 780, 1140]; ys = [170, 260, 350, 440]
    for x in xs:
        draw.line((x, 260 if merged_header and x == 420 else 170, x, 440), fill='black', width=3)
    for y in ys: draw.line((60, y, 1140, y), fill='black', width=3)
    # Repeated glyph-like vertical ink lasts less than one row, but adds up over a table.
    for x in (140, 500, 860):
        for top in (205, 295, 385): draw.line((x, top, x, top + 32), fill='black', width=2)
    values = ([['基本信息', None, '合同工资']] if merged_header else [['劳动者', '合同期限', '合同工资']])
    values += [['周明', '24个月', '12000元'], ['李华', '36个月', '15000元']]
    blocks = []
    for row, cells in enumerate(values):
        for col, value in enumerate(cells):
            if value is None: continue
            x, y = xs[col] + 20, ys[row] + 25
            blocks.append(([[x, y], [x + 140, y], [x + 140, y + 35], [x, y + 35]], value, .99))
    try: rows, warnings = ocr_rows(image, recognize=lambda _: blocks)
    finally: image.close()
    assert not warnings
    assert [r['value'] for r in rows] == ['\t'.join(v for v in row if v is not None) for row in values]
    metadata = [json.loads(r['location'].split(':layout:', 1)[1]) for r in rows]
    assert [(c['start_col'], c['end_col']) for c in metadata[0]['scan_grid']['cells']] == (
        [(1, 2), (3, 3)] if merged_header else [(1, 1), (2, 2), (3, 3)])
    for info in metadata[1:]:
        assert [(c['start_col'], c['end_col']) for c in info['scan_grid']['cells']] == [(1, 1), (2, 2), (3, 3)]
        assert not info.get('header_candidate')
        assert [b['headers'][-1]['value'] for b in info['header_bindings']] == (
            ['基本信息', '基本信息', '合同工资'] if merged_header else ['劳动者', '合同期限', '合同工资'])
