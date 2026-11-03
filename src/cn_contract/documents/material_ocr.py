"""Bundled Chinese/English ONNX models; inference uses local image pixels only."""
from threading import Lock

_lock = Lock()
_engine = None


def recognize(image):
    global _engine
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    with _lock:
        if _engine is None:
            _engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        result, _ = _engine(np.asarray(image.convert('RGB'))[:, :, ::-1])
        return result or []
