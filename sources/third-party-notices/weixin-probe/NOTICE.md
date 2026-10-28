# Weixin connection probe attribution

The isolated Python probe adapts protocol request shapes, login states, and AES key
decoding from Tencent/openclaw-weixin, commit
`874637a0dbc24050f72d1385add4fc6170a2d726` (package 2.4.10), inspected 2026-10-28.
No OpenClaw package, SDK, upstream logging, persistence, or retry loop is included.
The probe adds bounded downloads, exact self-peer binding, an expected-file digest,
and one fixed reply only after both exact file verification and an explicit per-process
challenge. Only the first valid command context is held in memory while waiting for
the file. It is not business integration.

Source: https://github.com/Tencent/openclaw-weixin/tree/874637a0dbc24050f72d1385add4fc6170a2d726

Referenced/adapted files: `docs/protocol.md`, `src/api/api.ts`,
`src/auth/login-qr.ts`, `src/cdn/pic-decrypt.ts`, `src/cdn/aes-ecb.ts`.
The file length check follows `src/api/types.ts` (`FileItem.len?: string`) and
`src/messaging/send.ts` (`len: String(uploaded.fileSize)`) at the same pin.
These client definitions do not guarantee every server response shape; unsupported
length representations stop the probe before any download.

License source: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/LICENSE

## Original license

Tencent is pleased to support the open source community by making openclaw-weixin available.

Copyright (C) 2026 Tencent.  All rights reserved.

openclaw-weixin is licensed under the MIT.


Terms of the MIT:
--------------------------------------------------------------------
Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
