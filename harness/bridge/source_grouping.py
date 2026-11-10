"""Keep proposed subject associations explicit without rewriting source entries."""
def group_sources(rows, groups):
    if not isinstance(groups,list) or not 1<=len(groups)<=20:
        raise ValueError('source_groups须为1至20组。')
    def valid(index):
        return type(index) is int and 0<=index<len(rows)
    prepared,usage=[],{}
    lines=['逐事项来源分组（关联由调用方提出，未经事实认证）',
           '同组不证明法律关系成立；不同组不证明彼此独立。未分组来源仍保留，原摘录编号不重排。']
    for number,group in enumerate(groups,1):
        if not isinstance(group,dict) or set(group)!={'subject_entry','entries'}:
            raise ValueError('分组只接受subject_entry和entries。')
        subject,indices=group['subject_entry'],group['entries']
        if (not valid(subject) or not isinstance(indices,list) or not 1<=len(indices)<=40
            or any(not valid(i) for i in indices) or len(set(indices))!=len(indices)
            or subject not in indices):
            raise ValueError('分组编号须为本批entries有效不重复的0起始索引，且包括subject_entry。')
        prepared.append({**group,'subject_quote':rows[subject]['contextual_quote'],'association_verified':False})
        lines.extend(['',f'分组{number}｜主题来源摘录{subject+1}（按句界恢复）：'+rows[subject]['contextual_quote']])
        seen=set()
        for index in indices:
            usage.setdefault(index,[]).append(number)
            row=rows[index];ref=row['citation']
            key=(ref['path'],ref['sha256'],ref['chunk'],row['contextual_quote'])
            if key in seen:
                lines.append(f'来源摘录{index+1}与本组已展示原文相同；保留索引，不重复正文。')
                continue
            seen.add(key)
            lines.append(f'来源摘录{index+1}（按句界恢复）：'+row['contextual_quote'])
            lines.append(f'出处：{ref["path"]}；片段{ref["chunk"]}；SHA-256 {ref["sha256"]}')
    unassigned=[i for i in range(len(rows)) if i not in usage]
    shared=[i for i,used in usage.items() if len(used)>1]
    lines.append('未分组来源摘录：'+('、'.join(str(i+1) for i in unassigned) or '无（仅指本批选入条目）'))
    for index in unassigned:
        row=rows[index];ref=row['citation']
        lines.append(f'来源摘录{index+1}（按句界恢复）：'+row['contextual_quote'])
        lines.append(f'出处：{ref["path"]}；片段{ref["chunk"]}；SHA-256 {ref["sha256"]}')
    if shared:
        lines.append('多组共享来源摘录：'+'、'.join(str(i+1) for i in shared)+'；须核对关系，不能复制为多个独立事件。')
    return {'groups':prepared,'unassigned_entries':unassigned,'shared_entries':shared},'\n'.join(lines)
