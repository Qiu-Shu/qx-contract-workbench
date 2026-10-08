"""Explicit 48-page LOCAL synthetic engineering observation, never legal gold."""
import argparse,hashlib,json,time
from datetime import datetime,timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageEnhance
from cn_contract.documents.ocr_process import run_ocr_page
from cn_contract.domain import OCRPageSource
from cn_contract.security import ServiceError
from cn_contract.documents.ocr_candidates import page_bitmap

DIGITS={
 '0':[(2,0),(0,2),(0,8),(2,10),(5,10),(7,8),(7,2),(5,0),(2,0)],
 '1':[(1,2),(4,0),(4,10)],'2':[(0,2),(2,0),(6,0),(7,3),(0,10),(7,10)],
 '3':[(0,0),(6,0),(4,5),(7,7),(6,10),(0,10)],'4':[(6,10),(6,0),(0,7),(8,7)],
 '5':[(7,0),(0,0),(0,5),(6,5),(7,8),(5,10),(0,10)],
 '6':[(7,0),(2,0),(0,4),(0,9),(5,10),(7,8),(6,5),(0,5)],
 '7':[(0,0),(7,0),(3,10)],'8':[(3,5),(0,2),(2,0),(6,0),(7,2),(3,5),(0,8),(2,10),(6,10),(7,8),(3,5)],
 '9':[(7,5),(1,5),(0,2),(2,0),(6,0),(7,2),(7,8),(5,10),(0,10)]}

def generate(destination):
    destination.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',40)
    rows=[];images=[]
    for group in ('clear','skew','blur','low_contrast','occluded','synthetic_handwriting'):
        for index in range(8):
            page=len(rows)+1;amount=str(28460+page*13);date=f'2026-10-{index+10:02}'
            image=Image.new('RGB',(1200,400),'white');draw=ImageDraw.Draw(image)
            draw.text((30,20),'独立虚构材料 '+str(page),font=font,fill='black')
            if group=='synthetic_handwriting':
                draw.text((30,115),'价款',font=font,fill='black')
                for n,ch in enumerate(amount):
                    points=[(160+n*50+x*4+y*.12,120+y*5) for x,y in DIGITS[ch]]
                    draw.line(points,fill='black',width=3,joint='curve')
                draw.text((445,115),'元',font=font,fill='black')
            else:draw.text((30,115),'价款 '+amount+' 元',font=font,fill='black')
            draw.text((30,220),'不得自动验收 '+date,font=font,fill='black')
            if group=='skew':image=image.rotate(4+index*.5,fillcolor='white',resample=Image.Resampling.BICUBIC)
            elif group=='blur':image=image.filter(ImageFilter.GaussianBlur(1.5+index*.2))
            elif group=='low_contrast':image=ImageEnhance.Contrast(image).enhance(.12+index*.01)
            elif group=='occluded':ImageDraw.Draw(image).rectangle((125,110,240+index*8,172),fill='white')
            name=f'{page:02}-{group}.png';path=destination/name;image.save(path)
            raw=path.read_bytes();images.append(image)
            rows.append(dict(page=page,group=group,path=name,sha256=hashlib.sha256(raw).hexdigest(),
                expected=[amount,'不得自动验收',date],expected_bbox=[30,110,600,280]))
    pdf=destination/'independent-48-pages.pdf'
    images[0].save(pdf,save_all=True,append_images=images[1:],resolution=144,creationDate='D:20261008000000Z',modDate='D:20261008000000Z')
    manifest={'scope':'independent_synthetic_engineering_only','handwriting':'independent vector strokes, not human handwriting quality validation',
        'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':rows}
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--generate-only',action='store_true')
    args=parser.parse_args();root=args.output.resolve()
    if root.exists():raise ValueError('fresh evidence directory required')
    manifest=generate(root)
    if args.generate_only:return
    observations=[]
    for row in manifest['pages']:
        raw,width,height,bw,bh=page_bitmap((root/'independent-48-pages.pdf').read_bytes(),row['page'])
        started=time.monotonic()
        source=OCRPageSource(document_version_id=UUID('4c68c5c5-1f35-447b-95fb-6646f66f1948'),document_sha256=manifest['pdf_sha256'],
            page=row['page'],page_width_points=width,page_height_points=height,bitmap_width=bw,bitmap_height=bh,
            bitmap_sha256=hashlib.sha256(raw).hexdigest(),coordinate_space='rendered_page_top_left')
        observation={'page':row['page'],'group':row['group'],'prediction_started':True,'input':'rendered_immutable_pdf_page',
            'bitmap_sha256':source.bitmap_sha256}
        try:
            result=run_ocr_page(raw,source.model_dump(mode='python'))
            (root/f"result-{row['page']:02}.json").write_text(result.model_dump_json(indent=2),encoding='utf-8')
            recognized=''.join(''.join(block.raw_text.split()) for block in result.blocks)
            correct=all(''.join(expected.split()) in recognized for expected in row['expected'])
            observation.update(status='CORRECT' if correct else 'INCORRECT_CANDIDATE',recognized=recognized,blocks=len(result.blocks))
        except ServiceError as error:observation.update(status='BLOCKED',code=error.code)
        except Exception as error:observation.update(status='ERROR',error_type=type(error).__name__)
        observation['seconds']=round(time.monotonic()-started,3);observations.append(observation)
        (root/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(observation,ensure_ascii=False),flush=True)
    summary={'pages':len(observations),'correct':sum(r['status']=='CORRECT' for r in observations),
        'incorrect':sum(r['status']=='INCORRECT_CANDIDATE' for r in observations),'blocked':sum(r['status']=='BLOCKED' for r in observations),
        'errors':sum(r['status']=='ERROR' for r in observations),'finished_utc':datetime.now(timezone.utc).isoformat()}
    summary['clear_positive']=sum(r['group']=='clear' and r['status']=='CORRECT' for r in observations)
    (root/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
    raise SystemExit(0 if summary['clear_positive'] and not summary['errors'] else 1)

if __name__=='__main__':main()
