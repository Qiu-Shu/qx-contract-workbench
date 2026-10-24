"""Rebuild an independent fictional native-text PDF (development tool only).

Uses the Codex bundled ReportLab, not a product runtime dependency. No input
documents, network, OCR, JavaScript, annotations or embedded attachments.
"""
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas


def main():
    target = Path(__file__).with_name('native-sales.pdf')
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    canvas = Canvas(str(target), pagesize=(595, 842), invariant=1, pageCompression=0)
    canvas.setTitle('Synthetic task PDF v1')
    canvas.setAuthor('Independent synthetic fixture')
    pages = (
        ('独立虚构买卖合同', '仅用于软件合成验收，不能用于真实交易。',
         '甲方：虚构甲公司', '乙方：虚构乙公司', '价款：13750元',
         '交付：签订后十日内交付虚构设备。'),
        ('独立虚构买卖合同 - 第二页', '仅用于软件合成验收，不能用于真实交易。',
         '预付款：20000元', '付款：双方另行核对付款金额。',
         '争议：提交虚构地人民法院处理。'),
    )
    for number, lines in enumerate(pages, 1):
        canvas.setFont('STSong-Light', 17)
        canvas.drawString(54, 780, lines[0])
        canvas.setFont('STSong-Light', 12)
        for index, line in enumerate(lines[1:]):
            canvas.drawString(54, 731 - index * 35, line)
        canvas.drawString(54, 64, f'独立虚构样本  第{number}页 / 共2页')
        canvas.showPage()
    canvas.save()
    print(target)


if __name__ == '__main__':
    main()
