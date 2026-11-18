# 打包成 macOS App

## 结构

```
立丰脱敏.app/
└── Contents/
    ├── MacOS/立丰脱敏          # Swift 外壳（WKWebView）
    └── Resources/
        ├── server.py           # 本地服务
        ├── web/                # 前端
        ├── engine/             # 脱敏引擎
        └── runtime/            # 可移植 Python
            ├── bin/python3
            └── lib/python3.13/...
```

外壳会优先用 `Resources/runtime/bin/python3` 和 `Resources/engine`；
两者都在时，**不会**去读外部目录，避免「装了新版却跑旧代码」。

## 关键：runtime 必须能脱离本机

venv 的 `bin/python3` 是指向绝对路径的符号链接，直接拷走等于没拷。
必须换成**真实二进制 + 完整标准库**：

```bash
# 1. 拷真实二进制（消掉符号链接）
cp "$(readlink -f runtime/bin/python3)" runtime/bin/python3

# 2. 拷标准库（venv 里只有 site-packages）
cp -R /path/to/base/lib/python3.13/{encodings,importlib,json,re,...} runtime/lib/python3.13/

# 3. 删掉 pyvenv.cfg，让它按自身目录找库
rm runtime/pyvenv.cfg
```

验证：

```bash
env -i HOME=/tmp/fakehome PATH=/usr/bin:/bin \
  runtime/bin/python3 -E -s -c "import docx, pymupdf, PIL, openpyxl; print('ok')"
```

`env -i` 是为了剥掉本机的 PYTHONPATH 与虚拟环境变量——能跑通才算真可移植。

## 签名

先删掉所有缓存，否则签名会被后续写入破坏：

```bash
find . -name __pycache__ -type d -exec rm -rf {} +
find . -name '*.pyc' -delete
codesign --force --deep --sign - 立丰脱敏.app
codesign --verify --deep --strict 立丰脱敏.app
```

⚠️ 顺序不能颠倒：**签名后不要再运行包内的 Python**。
一跑就会重新生成 `.pyc`，解压后 `codesign --verify` 会报
`a sealed resource is missing or invalid`。

功能验证要放在签名之前，或者用另一份副本做。

## 分发

```bash
zip -r -y -X 立丰脱敏-<日期>-Apple芯片.zip 立丰脱敏.app
```

只支持 Apple 芯片（arm64）。首次打开需按住 Control 点图标 →「打开」，
绕过 Gatekeeper（adhoc 签名没有公证）。
