"""Generate independently fictional materials; no client data or model calls."""
from pathlib import Path
import sys
from docx import Document


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    contents = {
        '虚构设备采购合同.docx': [
            '设备采购合同（独立虚构产品验收样本，所有主体与交易均为虚构）',
            '甲方：星禾模拟采购有限公司。乙方：远岚模拟设备有限公司。',
            '第一条：甲方向乙方购买办公扫描设备10台，总价人民币100000元，型号及技术指标双方另行协商。',
            '第二条：甲方在签约后3日内支付全部价款。乙方收到款项后适时交付，交付日期由乙方决定。',
            '第三条：货物送至甲方所在地即视为验收合格，甲方不得提出质量异议。质保期限未约定。',
            '第四条：乙方承担的全部赔偿不超过合同总价的10%；甲方逾期付款，每日按合同总价的1%支付违约金。',
            '第五条：争议由乙方所在地有管辖权的法院处理。本合同无附件。签订日期为2026年9月1日。',
        ],
        '虚构案件陈述与凭证.docx': [
            '独立虚构案件材料；以下客户陈述、材料记载和对方主张尚未核实。',
            '客户陈述：星禾模拟采购有限公司在2026年9月1日与远岚模拟设备有限公司签订设备采购合同。',
            '模拟银行回单记载：2026年9月3日，星禾模拟采购有限公司向远岚模拟设备有限公司支付100000元，备注设备款。此为虚构文本，不是银行真实凭证。',
            '模拟送货单记载：2026年10月8日送达6台扫描设备，4台未交付；收货人只签收数量。',
            '客户陈述：2026年10月10日试运行发现2台无法启动，已发催告；目前没有检测报告或完整邮件原件。',
            '对方主张：全部10台已交付，设备损坏是甲方使用不当，但尚未提供其余4台的签收记录。',
            '客户希望请求继续交付剩余4台并修理故障设备。双方注册地址、统一社会信用代码、联系人、明确损失数额和可确定管辖的地址待补。',
        ],
    }
    for name, paragraphs in contents.items():
        target = root / name
        if target.exists():
            raise FileExistsError(target)
        document = Document()
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
        document.save(target)


if __name__ == '__main__':
    main()
