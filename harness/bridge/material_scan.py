"""Keep local OCR evidence, joining only clearly aligned pieces of one row."""
import json
import math
import re
from threading import Lock

_OCR_LOCK=Lock()
_OCR_ENGINE=None


def _local_recognize(image,use_cls=True):
    """Reuse the bundled OCR models, allowing page rotation to be scored without crop flips."""
    global _OCR_ENGINE
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    with _OCR_LOCK:
        if _OCR_ENGINE is None:_OCR_ENGINE=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
        result,_=_OCR_ENGINE(np.asarray(image.convert('RGB'))[:,:,::-1],use_cls=use_cls)
        return result or []


def location_label(source):
    """Human-readable source coordinates, without treating layout as evidence."""
    location=source.get('location','')
    match=re.match(r'(?:page|image):(\d+):ocr-row:(\d+):',location)
    if match:
        parsed=source_layout(source)
        grid=parsed[1].get('scan_grid') if parsed else None
        if grid:return f'第{match[1]}页，表格{grid["table_id"]}第{grid["physical_row"]}行（识别行{match[2]}）'
        return f'第{match[1]}页，识别行{match[2]}'
    match=re.search(r'/tbl\[(\d+)\]/tr\[(\d+)\]:grid:',location)
    if match:
        tables=re.findall(r'/tbl\[(\d+)\]',location.split(':grid:',1)[0])
        return f'Word表格{"/".join(tables)}，第{match[2]}行'
    match=re.match(r'xlsx:sheet:\d+:row:(\d+):layout:',location)
    if match:
        try:
            info=json.loads(location.split(':layout:',1)[1].rsplit(':chars:',1)[0])
            return f'工作表“{info.get("sheet_name", "") }”第{match[1]}行'
        except (ValueError,IndexError,TypeError):return f'工作表第{match[1]}行'
    return ''


def source_layout(source):
    location=source.get('location','')
    match=re.fullmatch(r'((?:page|image):\d+):ocr-row:(\d+):layout:(\{.*\}):chars:(\d+)-\d+',location)
    if not match:return None
    try:return match,json.loads(match[3])
    except (ValueError,TypeError):return None


def source_warnings(source):
    location=source.get('location','')
    if location.startswith('xlsx:') and ':row:' in location:
        try:
            info=json.loads(location.split(':layout:',1)[1].rsplit(':chars:',1)[0])
            if any(c.get('formula') or c.get('date_format') or c.get('type')=='e' for c in info.get('cells',[])):
                return ['本表格行含公式缓存、日期序列或错误值，保留原值和单元格位置，核对该行后再作参数核算。']
        except (ValueError,IndexError,TypeError):return ['本表格行定位信息不完整，保留文字供核对。']
    if ':ocr-row:' not in source.get('location',''):return []
    parsed=source_layout(source)
    if parsed is None or parsed[1].get('flags'):
        return ['本扫描行的文字置信度或位置需核对；保留原文，暂停本行参数核算。']
    return []


def printed_table_label(text):
    return text.strip() in ('项目\t内容','字段\t值','续表') or bool(re.fullmatch(
        r'第\s*\d+\s*页(?:\s*[/／，,]?\s*共\s*\d+\s*页)?',text.strip()))


def adjacent_sheet_rows(previous,current):
    pattern=r'(xlsx:sheet:\d+):row:(\d+):layout:\{.*\}:chars:0-\d+'
    left=re.fullmatch(pattern,previous.get('location',''))
    right=re.fullmatch(pattern,current.get('location',''))
    return bool(left and right and left[1]==right[1] and int(right[2])==int(left[2])+1)


def adjacent_rows(previous,current):
    left,right=source_layout(previous),source_layout(current)
    if not left or not right:return False
    a,la=left;b,lb=right
    if (a[1]!=b[1] or int(b[2])!=int(a[2])+1 or a[4]!='0' or b[4]!='0' or la.get('flags') or lb.get('flags')
            or la.get('row_linking_uncertain') or lb.get('row_linking_uncertain')):return False
    boxes_a=[_bounds(box) for box in la.get('boxes',[])]
    boxes_b=[_bounds(box) for box in lb.get('boxes',[])]
    if not boxes_a or not boxes_b or None in boxes_a or None in boxes_b:return False
    bottom=max(box[3] for box in boxes_a);top=min(box[1] for box in boxes_b)
    height=max(box[3]-box[1] for box in boxes_a+boxes_b)
    return 0<=top-bottom<=3*height


def _json_value(value):
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [_json_value(part) for part in value]
    if isinstance(value, dict):
        return {str(key): _json_value(part) for key, part in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _bounds(box):
    try:
        if len(box) != 4 or any(len(point) != 2 for point in box):
            return None
        points = [(float(x), float(y)) for x, y in box]
        if not all(math.isfinite(value) for point in points for value in point):
            return None
        xs, ys = zip(*points)
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
        height = bottom - top
        if right <= left or height <= 0:
            return None
        # Rotated, crossed or unusually skewed boxes stay separate rather than imply a row.
        tl, tr, br, bl = points
        if not (tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]):
            return None
        if max(abs(tl[1] - tr[1]), abs(bl[1] - br[1])) > height * .25:
            return None
        return left, top, right, bottom
    except (TypeError, ValueError, OverflowError):
        return None


def _orientation_score(blocks):
    horizontal=vertical=0
    for block in blocks:
        try:
            bounds=_bounds(block[0]);text=block[1];score=float(block[2])
            if not bounds or not isinstance(text,str) or not .75<=score<=1:continue
            left,top,right,bottom=bounds
            if bottom-top>2*(right-left) and len(text.strip())>3:vertical+=len(text.strip())
            else:horizontal+=len(text.strip())*score
        except (TypeError,ValueError,IndexError,KeyError):continue
    return horizontal,vertical


def _oriented_blocks(image,recognize,recognize_orientation=None):
    original=recognize(image)
    best=original;rotation=0;size=list(image.size) if hasattr(image,'size') else None;warnings=[]
    score,vertical=_orientation_score(original)
    has_text=any(isinstance(b,(list,tuple)) and len(b)>1 and isinstance(b[1],str) and b[1].strip() for b in original)
    original_length=sum(len(b[1].strip()) for b in original if isinstance(b,(list,tuple)) and len(b)>1 and isinstance(b[1],str))
    # Only empty or predominantly sideways pages need extra local OCR passes.
    if hasattr(image,'rotate') and (not has_text or vertical>score):
        for angle in (90,180,270):
            frame=image.rotate(angle,expand=True)
            try:
                candidate=(recognize_orientation or recognize)(frame);candidate_score,_=_orientation_score(candidate)
                candidate_length=sum(len(b[1].strip()) for b in candidate if isinstance(b,(list,tuple)) and len(b)>1 and isinstance(b[1],str))
                if candidate_score>score and candidate_length>=original_length*.8:
                    best,score,rotation,size=candidate,candidate_score,angle,list(frame.size)
            except Exception:
                warnings.append('页面方向恢复有一次未完成；已保留当前可读文字，其他页继续处理。')
            finally:frame.close()
    if rotation:warnings.append(f'本页识别图像逆时针旋转{rotation}度；文字框坐标对应旋转后的图像，原文件未改动。')
    return best,rotation,size,list(dict.fromkeys(warnings))


def _native_duplicate(block, regions, rotation, size):
    """Text equality alone cannot distinguish another printed occurrence on the page."""
    try:
        text=re.sub(r'\s+','',block[1]);bounds=_bounds(_json_value(block[0]))
    except (IndexError,TypeError,KeyError):return False
    if not text or bounds is None:return False
    width,height=size
    def point(x,y):
        if rotation==90:return y,width-x
        if rotation==180:return width-x,height-y
        if rotation==270:return height-y,x
        return x,y
    left,top,right,bottom=bounds;area=(right-left)*(bottom-top)
    for region in regions:
        if text!=re.sub(r'\s+','',region['text']):continue
        x1,y1,x2,y2=region['box']
        corners=[point(x,y) for x,y in ((x1,y1),(x2,y1),(x2,y2),(x1,y2))]
        xs,ys=zip(*corners);a,b,c,d=min(xs),min(ys),max(xs),max(ys)
        other=(c-a)*(d-b)
        overlap=max(0,min(right,c)-max(left,a))*max(0,min(bottom,d)-max(top,b))
        if min(area,other)>0 and overlap>=.8*min(area,other) and overlap>=.6*max(area,other):return True
    return False


def ocr_rows(image, page=1, prefix='page', recognize=None, native_regions=()):
    """Return ({value, location, page} rows, warnings) without dropping uncertain text.

    Location layout JSON contains aligned original ``boxes`` and ``scores`` arrays,
    and row-specific ``flags``. Recognition errors remain the caller's responsibility.
    """
    orientation=None;review_locally=recognize is None
    if recognize is None:
        from cn_contract.documents.material_ocr import recognize
        orientation=lambda frame:_local_recognize(frame,use_cls=False)
    blocks,rotation,image_size,warnings = _oriented_blocks(image,recognize,orientation)
    recovery=None
    if review_locally and not any(isinstance(b,(list,tuple)) and len(b)>1 and isinstance(b[1],str) and b[1].strip() for b in blocks):
        from PIL import ImageOps,ImageFilter
        # Only an empty reading may be replaced by an enhanced-image candidate; existing words stay intact.
        for mode in ('contrast','contrast_sharpen'):
            frame=ImageOps.autocontrast(ImageOps.grayscale(image)).convert('RGB')
            if mode=='contrast_sharpen':
                sharpened=frame.filter(ImageFilter.UnsharpMask(radius=2,percent=150,threshold=3));frame.close();frame=sharpened
            try:
                candidate,angle,size,issues=_oriented_blocks(frame,_local_recognize,orientation)
                warnings.extend(issues)
                if any(isinstance(b,(list,tuple)) and len(b)>1 and isinstance(b[1],str) and b[1].strip() for b in candidate):
                    blocks,rotation,image_size=candidate,angle,size
                    recovery={'initial_ocr_empty':True,'mode':mode,'source_modified':False}
                    warnings.append('初识未读到文字，已从本机对比度增强图像提取候选；原件未修改，仍须核对数字、日期和否定词。')
                    break
            except Exception:
                warnings.append('本机增强重识别未完成，原件保留；其他页继续处理。')
            finally:frame.close()
    if native_regions:
        blocks=[block for block in blocks if not _native_duplicate(block,native_regions,rotation,image.size)]
    reviews={}
    if review_locally:
        from material_ocr_review import review_blocks
        review_image=image.rotate(rotation,expand=True) if rotation else image
        try:
            reviews,review_warnings=review_blocks(review_image,blocks,_local_recognize)
            warnings.extend(f'{prefix}:{page} {warning}' for warning in review_warnings)
        finally:
            if rotation:review_image.close()
    positioned, unpositioned = [], []
    for index, block in enumerate(blocks):
        try:
            text = block[1]
        except (TypeError, IndexError, KeyError):
            warnings.append(f'{prefix}:{page}:ocr-block:{index + 1} 识别块缺少文字，其他文字已保留。')
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            box = _json_value(block[0])
        except (TypeError, IndexError, KeyError):
            box = None
        try:
            score = _json_value(block[2])
        except (TypeError, IndexError, KeyError):
            score = None
        flags = []
        if index in reviews and reviews[index]['requires_check'] and reviews[index]['candidates']:flags.append('recognition_disagreement')
        try:
            confidence = float(score)
            if isinstance(score, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                flags.append('invalid_confidence')
            elif confidence < .75:
                if not reviews.get(index,{}).get('locally_supported'):flags.append('low_confidence')
        except (TypeError, ValueError, OverflowError):
            flags.append('invalid_confidence')
        bounds = _bounds(box)
        if bounds and bounds[3]-bounds[1]>2*(bounds[2]-bounds[0]) and len(text.strip())>3:
            flags.append('sideways_geometry')
        item = dict(text=text, box=box, score=score, bounds=bounds, flags=flags, index=index)
        if bounds is None:
            flags.append('uncertain_geometry')
            unpositioned.append(item)
        else:
            positioned.append(item)

    # Sort plus a sweep avoids comparing every pair on dense scanned tables.
    positioned.sort(key=lambda item: ((item['bounds'][1] + item['bounds'][3]) / 2,
                                      item['bounds'][0], item['index']))
    groups = []
    current = []
    for item in positioned:
        left, top, right, bottom = item['bounds']
        height, center = bottom - top, (top + bottom) / 2
        if current:
            next_top, next_bottom = max(common_top, top), min(common_bottom, bottom)
            next_min, next_max = min(min_height, height), max(max_height, height)
            next_low, next_high = min(low_center, center), max(high_center, center)
            same_row = (next_max <= 1.4 * next_min and
                        next_bottom - next_top >= .7 * next_max and
                        next_high - next_low <= .25 * next_min)
            if not same_row:
                groups.append(current)
                current = []
        if not current:
            common_top, common_bottom = top, bottom
            min_height = max_height = height
            low_center = high_center = center
        else:
            common_top, common_bottom = next_top, next_bottom
            min_height, max_height = next_min, next_max
            low_center, high_center = next_low, next_high
        current.append(item)
    if current:
        groups.append(current)

    ordered = []
    for group in groups:
        group.sort(key=lambda item: (item['bounds'][0], item['index']))
        if any(a['bounds'][2] > b['bounds'][0] for a, b in zip(group, group[1:])):
            for item in group:
                item['flags'].append('overlapping_geometry')
                ordered.append([item])
        else:
            ordered.append(group)
    ordered.extend([item] for item in unpositioned)

    from material_scan_grid import regroup,grid_metadata
    grid_image=image.rotate(rotation,expand=True) if rotation and hasattr(image,'rotate') else image
    try:ordered,grid_warnings=regroup(ordered,grid_image)
    finally:
        if grid_image is not image:grid_image.close()
    warnings.extend(grid_warnings)

    content_rows=[n for n,group in enumerate(ordered,1) if any(item['flags'] for item in group)
                  or not printed_table_label('\t'.join(item['text'] for item in group))]
    rows = []
    reasons = {'low_confidence': '含低置信度文字，请核对原件',
               'invalid_confidence': '置信度缺失或异常，请核对原件',
               'uncertain_geometry': '位置不可靠，已单独保留文字，未推断行列关系',
               'sideways_geometry': '文字方向尚不明确，保留文字和位置供核对',
               'recognition_disagreement': '初识与局部重识别不一致，未自动替换文字，仅本行需核对',
               'overlapping_geometry': '文字框重叠，已单独保留文字，未推断行列关系'}
    for number, group in enumerate(ordered, 1):
        flags = list(dict.fromkeys(flag for item in group for flag in item['flags']))
        location = f'{prefix}:{page}:ocr-row:{number}'
        layout = dict(boxes=[item['box'] for item in group],
                      scores=[item['score'] for item in group], flags=flags,
                      image_size=image_size, row_count=len(ordered),
                      content_first_row=content_rows[0] if content_rows else 0,content_last_row=content_rows[-1] if content_rows else 0,
                      text_length=len('\t'.join(item['text'] for item in group)))
        if rotation:layout['rotation_degrees']=rotation
        if recovery:layout['page_recovery']=recovery
        grid=grid_metadata(group)
        if grid:layout['scan_grid']=grid
        row_reviews=[reviews[item['index']] for item in group if item['index'] in reviews]
        if row_reviews:layout['ocr_reviews']=row_reviews
        if unpositioned:layout['row_linking_uncertain']=True
        rows.append(dict(value='\t'.join(item['text'] for item in group), page=page,
                         location=location + ':layout:' + json.dumps(
                             layout, ensure_ascii=False, separators=(',', ':'), allow_nan=False)))
        for flag in flags:
            warnings.append(f'{location} {reasons[flag]}。')
        for review in row_reviews:
            if review.get('locally_supported'):
                warnings.append(f'{location} 低置信度初识“{review["original"]}”经至少两种局部图像处理得到相同高置信度读数，原文未替换；可作条件候选，仍不是事实确认。')
                continue
            if not review['candidates']:
                warnings.append(f'{location} 低置信度初识“{review["original"]}”的局部重识别未形成足够支持，原文保留，仅相关行需核对。')
                continue
            candidates=' / '.join(dict.fromkeys(c['text'] for c in review['candidates']))
            suffix='原文未替换。' if review['requires_check'] else '局部重识别未读完整数值，不据此否定初识或暂停本行核算。'
            warnings.append(f'{location} 初识“{review["original"]}”；局部重识别候选“{candidates}”；{suffix}')
    from material_headers import annotate_headers
    annotate_headers(rows)
    return rows, warnings
