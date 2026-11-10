"""Conservative native-PDF visibility evidence, not visual equivalence or OCR.

Supports ordinary opaque device-color text and straight stroked table borders.
Text on light/unknown colors, opacity/blending, clipping, shading, Form painting,
unimplemented ExtGState attributes, curved strokes, and later paths overlapping
text require visual review of the whole page. Fill/stroke/mixed text modes use
their actual paint colors; mixed modes conservatively require both contrasts.
The interpreter observes decoded operators and resources, including q/Q and
nested streams; searching raw PDF bytes would miss compressed content.
"""
import math

from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdftypes import dict_value, resolve1, stream_value
from pdfminer.psparser import literal_name
from pdfminer.utils import apply_matrix_pt
from pdfplumber.page import PDFPageAggregatorWithMarkedContent


def _device_brightness(color, space):
    values = (color,) if isinstance(color, (int, float)) else color
    if not isinstance(values, (tuple, list)) or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values
    ):
        return None
    name = getattr(space, 'name', None)
    if name == 'DeviceGray' and len(values) == 1:
        brightness = values[0]
    elif name == 'DeviceRGB' and len(values) == 3:
        brightness = sum(v * weight for v, weight in zip(values, (.2126, .7152, .0722)))
    elif name == 'DeviceCMYK' and len(values) == 4:
        brightness = sum((1 - min(1, v + values[3])) * weight
            for v, weight in zip(values[:3], (.2126, .7152, .0722)))
    else:
        return None
    return brightness


def _intersects(first, second):
    return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]


class VisibilityAggregator(PDFPageAggregatorWithMarkedContent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visual_reasons = set()
        self.text_boxes = []
        self.background_boxes = []
        self._text_brightness = ()

    def render_string(self, textstate, seq, ncs, graphicstate):
        mode = textstate.render
        if mode not in {0, 1, 2}:
            self.visual_reasons.add('TEXT_RENDERING_REQUIRES_CONFIRMATION')
        colors = []
        if mode in {0, 2}:
            colors.append((graphicstate.ncolor, ncs))
        if mode in {1, 2}:
            colors.append((graphicstate.scolor, graphicstate.scs))
        brightnesses = tuple(_device_brightness(color, space) for color, space in colors)
        if any(brightness is None or brightness > .85 for brightness in brightnesses):
            self.visual_reasons.add('PDF_TEXT_COLOR_REQUIRES_CONFIRMATION')
        previous = self._text_brightness
        self._text_brightness = brightnesses
        try:
            return super().render_string(textstate, seq, ncs, graphicstate)
        finally:
            self._text_brightness = previous

    def render_char(self, *args, **kwargs):
        advance = super().render_char(*args, **kwargs)
        char = self.cur_item._objs[-1]
        if char.get_text().strip():
            if any(_intersects(char.bbox, box) and any(background is None or brightness is None
                or abs(background - brightness) < .35 for brightness in self._text_brightness)
                for box, background in self.background_boxes):
                self.visual_reasons.add('PDF_TEXT_BACKGROUND_REQUIRES_CONFIRMATION')
            self.text_boxes.append(char.bbox)
        return advance

    def paint_path(self, gstate, stroke, fill, evenodd, path):
        if stroke and any(op[0] not in {'m', 'l', 'h'} for op in path):
            # c/v/y are not straight segments. Endpoint boxes cannot certify
            # control-point geometry, caps or joins; no curve solver is in scope.
            self.visual_reasons.add('PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION')
        points = [apply_matrix_pt(self.ctm, (float(x), float(y)))
            for op in path for x, y in zip(op[1::2], op[2::2])]
        if points:
            bbox = (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))
            if fill:
                if any(_intersects(bbox, box) for box in self.text_boxes):
                    self.visual_reasons.add('PDF_TEXT_OCCLUSION_REQUIRES_CONFIRMATION')
                self.background_boxes.append((bbox, _device_brightness(gstate.ncolor, gstate.ncs)))
            if stroke and self.text_boxes:
                scale = max(math.hypot(*self.ctm[:2]), math.hypot(*self.ctm[2:4]))
                radius = max(.25, gstate.linewidth * scale / 2)
                start = last = None
                for op in path:
                    target = start if op[0] == 'h' else apply_matrix_pt(self.ctm, (float(op[-2]), float(op[-1])))
                    if op[0] == 'm':
                        start = target
                    elif last is not None and target is not None:
                        # Segment bounding boxes preserve ordinary rectangular
                        # borders; using the whole rectangle would flag its text.
                        segment = (min(last[0], target[0]) - radius, min(last[1], target[1]) - radius,
                            max(last[0], target[0]) + radius, max(last[1], target[1]) + radius)
                        if any(_intersects(segment, box) for box in self.text_boxes):
                            self.visual_reasons.add('PDF_TEXT_OCCLUSION_REQUIRES_CONFIRMATION')
                    last = target
        return super().paint_path(gstate, stroke, fill, evenodd, path)


class VisibilityInterpreter(PDFPageInterpreter):
    def _effect(self):
        self.device.visual_reasons.add('PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION')

    def do_gs(self, name):
        # pdfminer does not implement ExtGState. Observe actual resource use;
        # unused resources confer no risk and do not cause global downgrades.
        try:
            state = dict_value(resolve1(dict_value(self.resources.get('ExtGState', {}))[literal_name(name)]))
        except (KeyError, TypeError, ValueError):
            self._effect()
            return
        # Only Type is metadata. Even familiar paint keys such as LW/LC/LJ/D
        # are unimplemented by do_gs; treating them as harmless loses actual
        # widths/caps/joins and can miss an opaque stroke covering the text.
        harmless = {'Type'}
        for key, raw in state.items():
            value = resolve1(raw)
            if key in {'ca', 'CA'}:
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value != 1:
                    self.device.visual_reasons.add('PDF_TRANSPARENCY_REQUIRES_CONFIRMATION')
            elif key == 'BM':
                if literal_name(value) not in {'Normal', 'Compatible'}:
                    self._effect()
            elif key == 'SMask':
                if literal_name(value) != 'None':
                    self._effect()
            elif key not in harmless:
                self._effect()
        return super().do_gs(name)

    def do_W(self):
        self._effect()
        return super().do_W()

    def do_W_a(self):
        self._effect()
        return super().do_W_a()

    def do_sh(self, name):
        self._effect()
        return super().do_sh(name)

    def do_BDC(self, tag, props):
        if literal_name(tag) == 'OC':
            self._effect()
        return super().do_BDC(tag, props)

    def do_Do(self, name):
        try:
            obj = stream_value(self.xobjmap[literal_name(name)])
            if literal_name(obj.get('Subtype')) != 'Image':
                # Form BBox clipping, inherited state and transparency groups
                # are not certified by the native extractor in this slice.
                self._effect()
        except (KeyError, TypeError, ValueError):
            self._effect()
        return super().do_Do(name)


def outside_visible_page(chars, page):
    """Use pdfplumber's rotation-adjusted top-origin MediaBox/CropBox."""
    boxes = (page.mediabox, page.cropbox)
    if any(len(box) != 4 or not all(math.isfinite(v) for v in box)
        or box[2] <= box[0] or box[3] <= box[1] for box in boxes):
        return True
    left, top = max(box[0] for box in boxes), max(box[1] for box in boxes)
    right, bottom = min(box[2] for box in boxes), min(box[3] for box in boxes)
    return any(char['x0'] < left or char['top'] < top or char['x1'] > right or char['bottom'] > bottom
        for char in chars)
