"""Copied into a private AppContainer job. No application imports or case DB."""
import json,os
from pathlib import Path


def main():
    request=json.loads(Path('request.json').read_text(encoding='utf-8'))
    if set(request)!={'image','model_root'} or request['image']!='input.png' or request['model_root']!=os.environ['QX_MODELS']:
        raise ValueError('fixed inputs required')
    from paddleocr import PaddleOCR
    # Native Paddle file readers on Windows cannot open this project's Unicode
    # absolute path. Parent verifies private copies; ASCII relative paths work.
    root=Path('models')
    pipeline=PaddleOCR(device='cpu',cpu_threads=2,enable_mkldnn=False,
        text_detection_model_name='PP-OCRv5_mobile_det',text_detection_model_dir=str(root/'PP-OCRv5_mobile_det'),
        text_recognition_model_name='PP-OCRv5_mobile_rec',text_recognition_model_dir=str(root/'PP-OCRv5_mobile_rec'),
        use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
    results=list(pipeline.predict('input.png'))
    if len(results)!=1:raise ValueError('one page required')
    result=results[0]
    texts=result['rec_texts'];scores=result['rec_scores'];polys=result['rec_polys']
    if not len(texts)==len(scores)==len(polys) or len(texts)>2000:raise ValueError('bounded blocks required')
    blocks=[dict(raw_text=str(t),confidence=float(s),polygon=p.tolist() if hasattr(p,'tolist') else p)
        for t,s,p in zip(texts,scores,polys)]
    return {'status':'ok','blocks':blocks}


if __name__=='__main__':
    # stdout/stderr are private bounded job files, not protocol or public logs.
    import sys
    with Path('worker.log').open('w',encoding='utf-8') as log:
        sys.stdout=sys.stderr=log
        try: result=main()
        except Exception as error:
            import traceback
            traceback.print_exc(file=log)
            result={'status':'error','type':type(error).__name__,'message':str(error)[:1200]}
    data=json.dumps(result,ensure_ascii=False,allow_nan=False)
    if len(data.encode())>2_000_000:raise ValueError('output limit')
    Path('output.json').write_text(data,encoding='utf-8')
