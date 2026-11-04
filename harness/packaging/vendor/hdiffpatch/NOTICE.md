# HDiffPatch 第三方材料

本软件的增量安装复用 **HDiffPatch 5.1.3 官方 Windows x64 `hpatchz.exe`**，未修改该二进制。完整来源、固定下载摘要、两个工具摘要及许可证来源见 [vendor.json](vendor.json)。`hdiffz.exe` 仅用于构建补丁，不是客户安装时所需的工具。此目录只存许可证和来源说明，不存工具二进制或整份上游源码。

已实测固定发布包的 `-v`、`-h`，并让 `hdiffz` 生成合成补丁后由固定 `hpatchz` 还原：zlib/ldef 兼容流、bzip2/pbzip2、LZMA/LZMA2、Zstandard、7zXZ/VCDIFF，以及 crc32、fadler64、MD5、xxh3、xxh128，共 13 组通过。这证明对应格式可用，不证明每个静态链接库的精确版本。

HDiffPatch v5.1.3 的 `hpatchz.c` 默认启用 zlib、bzip2、LZMA/LZMA2、Zstandard、7zXZ 解码及上述校验插件；Windows `HPatchZ.vcxproj` 引用相应构建项目，并直接编译 libmd5，xxHash 由校验插件引用。本目录保留这些组件的许可证原文：

| 文件 | 内容 |
| --- | --- |
| `LICENSE` | HDiffPatch 上游完整 MIT 许可证，附带的 libdivsufsort 许可原样保留。 |
| `zlib-LICENSE.txt` | zlib 版权及许可原文。 |
| `bzip2-LICENSE.txt` | bzip2/libbzip2 版权及许可原文。 |
| `lzma-SDK-LICENSE.txt` | LZMA SDK 文档的 LICENSE 小节原文，Igor Pavlov 的公共领域声明。 |
| `zstd-LICENSE.txt` | Zstandard 的 BSD 许可证选项原文。 |
| `libmd5-LICENSE.txt` | libmd5 `md5.h` 首部许可注释原文。 |
| `xxHash-LICENSE.txt` | xxHash 的 BSD 2-Clause 许可证原文。 |
| `libdeflate-COPYING.txt` | Windows 构建项目还引用 libdeflate，故保留其 MIT 许可原文；不据此宣称该官方 hpatchz 二进制一定包含其所有代码。 |

上游 `hpatchz.c` 默认选择 zlib 解码器，libdeflate 替代开关默认关闭；用 libdeflate 生成的兼容 deflate 流可由 zlib 解码，因此格式测试不能确认 libdeflate 的实际静态链接情况。除构建项目引用外，本次未独立确认其代码是否进入最终补丁程序。

上游发布包未随附完整依赖 SBOM；v5.1.3 的构建工作流按依赖分支头克隆，没有固定依赖提交。因此 `vendor.json` 中各许可证的提交号是本次取回许可文本的固定来源，**不是**声称官方二进制使用了这些精确提交或对应库版本。未据此作“所有二进制内容已完成许可审计”的结论。

本项目实际生成补丁使用 Zstandard 与 xxh128；仍保留官方预编译引擎所支持/构建引用组件的上述材料。所有许可证保留其作者署名和免责条款；提取注释或文档小节的文件已在来源清单注明范围。
