"""Keep the first OCR reading; local crop disagreement is evidence, not autocorrection."""
import math
import re
from PIL import ImageOps,ImageFilter


def _normalized(text):
    return re.sub(r'\s+','',text).translate(str.maketrans('：；，（）',':;,()'))


def review_blocks(image,blocks,recognize,maximum=12):
    reviews={};warnings=[];attempted=0
    for index,block in enumerate(blocks):
        try:
            box,text,score=block[:3]
            if not isinstance(text,str) or not 0<=float(score)<=1:continue
            weak=float(score)<.75
            if not weak and not re.search(r'[0-9一二三四五六七八九十百年月日元不未无否]',text):continue
            xs,ys=zip(*box)
            if not all(math.isfinite(float(v)) for v in (*xs,*ys)):continue
            left,top=max(0,math.floor(min(xs))-8),max(0,math.floor(min(ys))-8)
            right,bottom=min(image.width,math.ceil(max(xs))+8),min(image.height,math.ceil(max(ys))+8)
            if right<=left or bottom<=top:continue
        except (ValueError,TypeError,IndexError):continue
        if attempted>=maximum:
            warnings.append('本页重要文字超过局部重识别数量上限，其余保留初识文字；未标注差异不代表已经核实。');break
        attempted+=1;candidates=[];agreements=[]
        crop=image.crop((left,top,right,bottom))
        scale=min(3,2400/max(crop.size))
        enlarged=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))))
        crop.close()
        try:
            for mode in (('rgb','gray','sharpen') if weak else ('rgb','gray')):
                view=enlarged.copy() if mode=='rgb' else ImageOps.autocontrast(ImageOps.grayscale(enlarged)).convert('RGB')
                if mode=='sharpen':
                    sharpened=view.filter(ImageFilter.UnsharpMask(radius=2,percent=150,threshold=3));view.close();view=sharpened
                try:
                    found=recognize(view)
                    parts=[b for b in found if len(b)>=3 and isinstance(b[1],str) and b[1].strip()]
                    if not parts or any(not .75<=float(b[2])<=1 for b in parts):continue
                    # Crops contain one original line; keep recognizer order, never reorder words by a language guess.
                    value=' '.join(b[1] for b in parts)
                    if weak and _normalized(value)==_normalized(text) and min(float(b[2]) for b in parts)>=.9:
                        agreements.append({'text':value,'mode':mode,'score':min(float(b[2]) for b in parts)})
                    if _normalized(value)!=_normalized(text):
                        quantity=r'(?:[0-9]+(?:\.[0-9]+)?|[零〇一二两三四五六七八九十百]+)\s*(年|个月|月|日|元)'
                        incomplete=bool(re.search(quantity,text) and _normalized(value) in
                                        {_normalized(re.sub(quantity,r'\1',text)),_normalized(re.sub(quantity,'',text))})
                        candidates.append({'text':value,'mode':mode,'score':min(float(b[2]) for b in parts),'incomplete_quantity':incomplete})
                except Exception:
                    warnings.append('有局部重识别未完成，原识别文字仍保留；未将重识别失败当作全页不可用。')
                finally:view.close()
        finally:enlarged.close()
        if candidates or weak:
            conflict=any(not c['incomplete_quantity'] for c in candidates)
            reviews[index]={'original':text,'candidates':candidates,'applied':False,
                           'requires_check':conflict or (weak and len(agreements)<2),'crop_box':[left,top,right,bottom]}
            if weak:reviews[index].update(agreements=agreements,locally_supported=len(agreements)>=2 and not conflict)
    return reviews,list(dict.fromkeys(warnings))
