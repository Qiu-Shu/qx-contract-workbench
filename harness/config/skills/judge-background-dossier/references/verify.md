# 版式复核

脚本只保证字符与列宽，分页要另外验。表格被切断、标题孤零零留在页底，这两种毛病只有看分页才能发现。

## Windows（装了 Word 时）

把下面脚本存成 check.ps1，路径改成实际文件，用 PowerShell 运行。结果写到同目录的 layout.txt。

```powershell
$src = "D:\path\某某法官背调与开庭提纲.docx"
Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Open($src, $false, $true)
$doc.Repaginate()
$out = New-Object System.Collections.ArrayList
[void]$out.Add("总页数 " + $doc.ComputeStatistics(2))
$lastpg = -1
foreach ($p in $doc.Paragraphs) {
  $pg = $p.Range.Information(3)
  $t = ($p.Range.Text -replace "[`r`n`t]", " ").Trim()
  if ($t.Length -gt 18) { $t = $t.Substring(0,18) }
  if ($pg -ne $lastpg) { $lastpg = $pg; [void]$out.Add("第 " + $pg + " 页起始：" + $t) }
}
$doc.Close(0)
$word.Quit()
Set-Content -Path "layout.txt" -Value $out -Encoding UTF8
```

判读方法：

- 每页起始段落若是二级标题，说明该标题落在了页首，正常。
- 若某页起始是正文中段且上一页结尾是标题，说明标题孤行，回内容稿调整长度或加 pagebreak。
- 附表一的表题若出现在某页末尾而表格主体在下一页，说明 caption 与 table 被拆开，加 pagebreak。
- 总页数落在七到九页为宜。超过十页多半是条目太碎或表格留白过多。

## 无 Word 时

用 WPS 或 Word 打开后导出 PDF，看分页。或用 LibreOffice 命令行：

```
soffice --headless --convert-to pdf 某某法官背调与开庭提纲.docx
```

再翻 PDF 的页尾与页首。这一步只是替代方案，判断标准与上面四条相同。

## 常见问题

- 表格跨页。原因是表格行数多且前面内容占满当页。解决办法是把附表整体前移一页（加 pagebreak），不要压缩行高。
- 附表二最后一行被切。结论一页纸十行，行高二十六磅，加上表题与表头刚好一页，若正文内容挤占导致溢出，给附表二前也加 pagebreak。
- 字数很多但页数很少。检查是不是误用了十进制行距而不是倍数行距。
