"""Use visible ruled cells to group OCR words; never infer missing words or borderless spans."""
from bisect import bisect_right


def _clusters(values,gap=3):
    groups=[]
    for value in values:
        value=int(value)
        if groups and value-groups[-1][-1]<=gap:groups[-1].append(value)
        else:groups.append([value])
    return [round(sum(group)/len(group)) for group in groups]


def detect_cells(image):
    import cv2
    import numpy as np
    gray=np.asarray(image.convert('L'))
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,31,12)
    height,width=gray.shape
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(20,width//30)),np.uint8))
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(15,height//50),1),np.uint8))
    components=cv2.dilate(cv2.bitwise_or(horizontal,vertical),np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(components,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    rectangles=sorted((cv2.boundingRect(c) for c in contours),key=lambda b:(b[1],b[0]))
    tables=[]
    for x,y,w,h in rectangles:
        if w<max(120,width*.2) or h<60:continue
        ys=_clusters(np.flatnonzero(np.count_nonzero(horizontal[y:y+h,x:x+w],axis=1)>=max(20,width//30))+y)
        if len(ys)<3:continue
        boundaries=[]
        for number,(top,bottom) in enumerate(zip(ys,ys[1:]),1):
            if bottom-top<10:continue
            xs=_clusters(np.flatnonzero(np.count_nonzero(vertical[top+3:bottom-2,x:x+w],axis=0)>=(bottom-top-5)*.65)+x)
            if len(xs)<2:continue
            boundaries.append((number,top,bottom,xs))
        # Only row-spanning rules define columns. Repeated short glyph strokes can
        # accumulate enough ink over a whole table to look like phantom columns.
        all_x=_clusters(sorted({edge for _,_,_,xs in boundaries for edge in xs}))
        if len(all_x)<3:continue
        bands=[];band_rows=[];previous={}
        for number,top,bottom,xs in boundaries:
            cells=[]
            for left,right in zip(xs,xs[1:]):
                a=min(range(len(all_x)),key=lambda i:abs(all_x[i]-left))
                b=min(range(len(all_x)),key=lambda i:abs(all_x[i]-right))
                if b<=a or abs(all_x[a]-left)>5 or abs(all_x[b]-right)>5:continue
                extent=(a+1,b)
                boundary=np.count_nonzero(np.any(horizontal[max(0,top-2):top+3,left+3:right-2],axis=0))/max(1,right-left-5)
                if boundary<.2 and extent in previous:
                    cell=previous[extent];cell['box'][3]=bottom;cell['end_row']=number
                else:
                    cell={'start_col':a+1,'end_col':b,'box':[left,top,right,bottom],
                          'physical_row':number,'end_row':number,'table_id':len(tables)+1}
                cells.append(cell)
            if cells:bands.append((top,bottom,cells));band_rows.append(number)
            previous={(c['start_col'],c['end_col']):c for c in cells}
        if bands:tables.append({'box':[x,y,x+w,y+h],'bands':bands,'band_rows':band_rows,'tops':[b[0] for b in bands]})
    return tables


def regroup(ordered,image):
    if not hasattr(image,'convert'):return ordered,[]
    try:tables=detect_cells(image)
    except Exception:return ordered,['扫描表格线提取未完成，文字与原位置仍保留，其他材料继续处理。']
    if not tables:return ordered,[]
    def cell_for(item):
        if item['bounds'] is None:return None
        left,top,right,bottom=item['bounds'];cx=(left+right)/2;cy=(top+bottom)/2
        pad_x=min(12,max(3,(right-left)*.08));pad_y=min(12,max(3,(bottom-top)*.12))
        for table in tables:
            x1,y1,x2,y2=table['box']
            if not x1<=cx<=x2 or not y1<=cy<=y2:continue
            index=bisect_right(table['tops'],cy)-1
            if index<0:continue
            _,end,cells=table['bands'][index]
            if cy>end:continue
            found=[c for c in cells if c['box'][0]+1<cx<c['box'][2]-1 and
                   left>=c['box'][0]-pad_x and right<=c['box'][2]+pad_x and
                   top>=c['box'][1]-pad_y and bottom<=c['box'][3]+pad_y]
            if len(found)==1:return found[0]
        return None
    def containing_band(item):
        if item['bounds'] is None:return None
        left,top,right,bottom=item['bounds'];cx=(left+right)/2;cy=(top+bottom)/2
        for table_id,table in enumerate(tables,1):
            x1,y1,x2,y2=table['box']
            if not x1<=cx<=x2 or not y1<=cy<=y2:continue
            index=bisect_right(table['tops'],cy)-1
            if index>=0 and cy<=table['bands'][index][1]:
                return table_id,table['band_rows'][index]
        return None
    untouched=[];grouped={};prepared=[];blocked=set()
    for group in ordered:
        cells=[cell_for(item) for item in group]
        keys={(c['table_id'],c['physical_row']) for c in cells if c}
        if any(c is None for c in cells):
            blocked.update(k for item in group if (k:=containing_band(item)) is not None)
        prepared.append((group,cells,keys))
    for group,cells,keys in prepared:
        if any(c is None for c in cells) or keys&blocked:
            untouched.append(group);continue
        for item,cell in zip(group,cells):
            key=(cell['table_id'],cell['physical_row'])
            grouped.setdefault(key,[]).append({**item,'scan_cell':cell})
    for group in grouped.values():
        group.sort(key=lambda item:(item['scan_cell']['start_col'],item['bounds'][1],item['bounds'][0]))
        untouched.append(group)
    untouched.sort(key=lambda group:min((i['scan_cell']['box'][1] if 'scan_cell' in i else i['bounds'][1] if i['bounds'] else float('inf')) for i in group))
    return untouched,[]


def grid_metadata(group):
    if not all('scan_cell' in item for item in group):return None
    cells={};offset=0
    for item in group:
        cell=item['scan_cell'];key=(cell['start_col'],cell['end_col'])
        if key not in cells:cells[key]={**cell,'text_start':offset,'text_end':offset+len(item['text']),'flags':list(item['flags'])}
        else:
            cells[key]['text_end']=offset+len(item['text']);cells[key]['flags'].extend(item['flags'])
        offset+=len(item['text'])+1
    first=group[0]['scan_cell']
    return dict(table_id=first['table_id'],physical_row=first['physical_row'],cells=list(cells.values()))
