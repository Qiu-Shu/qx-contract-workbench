// 立丰脱敏 —— 原生窗口宿主
// 职责：启动本地服务（若未运行）→ 开一个原生窗口加载界面 → 支持拖文件到窗口/图标
// 全部本地回环，不联网。

import Cocoa
import WebKit

let HOME = FileManager.default.homeDirectoryForCurrentUser.path
let APP_DIR = Bundle.main.bundlePath
let RES = APP_DIR + "/Contents/Resources"
let SERVER = RES + "/server.py"
// 真正的业务代码放在 App 外面：改脚本不用重签 App，
// 而 ad-hoc 签名每次重签都会让 macOS 把 App 当新应用、重置隐私授权。
// 外部目录存在就优先用；不存在则退回包内那份（分发给别人时就是这个形态）。
let CODE_DIR = HOME + "/Library/Application Support/立丰脱敏/runtime-code"
let CODE_SERVER = FileManager.default.fileExists(atPath: CODE_DIR + "/server.py")
    ? CODE_DIR + "/server.py"
    : RES + "/server.py"
let SUPPORT = HOME + "/Library/Application Support/立丰脱敏"
let WORK_INBOX = SUPPORT + "/工作区/待处理"
let VENV_PY = FileManager.default.isExecutableFile(atPath: RES + "/runtime/bin/python3")
    ? RES + "/runtime/bin/python3"
    : HOME + "/.workbuddy/binaries/python/envs/default/bin/python3"
// 分发包（发给别人电脑）自带 Python，对方机器上没有 ~/.workbuddy。
// 包内 runtime 存在就绝不去碰本机 venv —— 否则会挑到一个缺库的解释器，
// 表现是图片/扫描 PDF 全报 No module named 'PIL'。
let BUNDLED = FileManager.default.isExecutableFile(atPath: RES + "/runtime/bin/python3")
let PORT = 8791
let BASE = "http://127.0.0.1:\(PORT)"

func findPython() -> String {
    let cands = [VENV_PY, "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
    for p in cands where FileManager.default.isExecutableFile(atPath: p) { return p }
    return "/usr/bin/python3"
}

func serviceUp() -> Bool {
    // 用同步请求探活，避免异步复杂度
    guard let url = URL(string: BASE + "/api/status") else { return false }
    var ok = false
    let sem = DispatchSemaphore(value: 0)
    var req = URLRequest(url: url)
    req.timeoutInterval = 1.5
    req.cachePolicy = .reloadIgnoringLocalCacheData
    let cfg = URLSessionConfiguration.ephemeral
    cfg.connectionProxyDictionary = [:]     // 禁用系统代理，直连本机回环
    let sess = URLSession(configuration: cfg)
    sess.dataTask(with: req) { _, resp, _ in
        ok = (resp as? HTTPURLResponse)?.statusCode == 200
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + 2.0)
    return ok
}

func startService() {
    guard FileManager.default.fileExists(atPath: CODE_SERVER) else { return }
    let py = findPython()
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: py)
    proc.arguments = [CODE_SERVER]
    var env = ProcessInfo.processInfo.environment
    env["LF_CODE_DIR"] = (CODE_SERVER == RES + "/server.py") ? RES : CODE_DIR
    // 告诉引擎脚本用哪个解释器与哪个引擎目录 —— 分发包里两者都在包内，
    // 不能靠 ~/.workbuddy 那种本机路径去猜（对方机器上根本没有）。
    env["DESENSITIZE_PYTHON"] = py
    env["LF_ENGINE_DIR"] = RES + "/engine"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    env.removeValue(forKey: "HTTP_PROXY");  env.removeValue(forKey: "http_proxy")
    env.removeValue(forKey: "HTTPS_PROXY"); env.removeValue(forKey: "https_proxy")
    proc.environment = env
    // 日志落盘，便于排查。
    // 原来写 ~/.workbuddy/binaries/ollama/logs/ —— 那是本机 WorkBuddy 的目录，
    // 发给别人的电脑上不存在，createFile 会静默失败，日志直接进黑洞。
    // 改成用户标准的 ~/Library/Logs/，任何 Mac 都有。
    let logDir = HOME + "/Library/Logs"
    try? FileManager.default.createDirectory(atPath: logDir, withIntermediateDirectories: true)
    let logPath = logDir + "/立丰脱敏.log"
    FileManager.default.createFile(atPath: logPath, contents: nil)
    if let fh = FileHandle(forWritingAtPath: logPath) {
        fh.seekToEndOfFile()
        proc.standardOutput = fh
        proc.standardError = fh
    }
    do { try proc.run() } catch { NSLog("启动服务失败: \(error)") }
}

@available(macOS 10.13, *)
func ensureOllama() {
    // 本地千问没起来时顺手拉起（识敏要用），失败不影响规则脱敏。
    // 分发包不带模型：对方机器上没有 ~/.workbuddy/binaries/ollama，
    // isExecutableFile 直接 false 就返回，不会卡、不会报错。
    guard !BUNDLED else { return }
    let bin = HOME + "/.workbuddy/binaries/ollama/ollama"
    guard FileManager.default.isExecutableFile(atPath: bin) else { return }
    guard let url = URL(string: "http://127.0.0.1:11434/api/version") else { return }
    var ok = false
    let sem = DispatchSemaphore(value: 0)
    var req = URLRequest(url: url); req.timeoutInterval = 1.0
    let cfg = URLSessionConfiguration.ephemeral
    cfg.connectionProxyDictionary = [:]
    URLSession(configuration: cfg).dataTask(with: req) { _, r, _ in
        ok = (r as? HTTPURLResponse)?.statusCode == 200
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + 1.5)
    if ok { return }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: bin)
    p.arguments = ["serve"]
    var env = ProcessInfo.processInfo.environment
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    env["OLLAMA_MODELS"] = HOME + "/.workbuddy/binaries/ollama/models"
    env["OLLAMA_NO_CLOUD"] = "1"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    p.environment = env
    try? p.run()
}

class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    // ⚡ 2026-11-11：去水印要能「单独用一个窗口」，不挤占主界面。
    //   前端点「去水印」走 window.open()，WKWebView 会回调
    //   createWebViewWith；不实现这个方法，window.open 会被**静默忽略**，
    //   用户点了按钮像没反应 —— 这是 WKWebView 的默认行为，不是 JS 写错了。
    //   必须持有窗口引用，否则 ARC 一回收窗口就消失。
    var extraWindows: [NSWindow] = []

    func applicationDidFinishLaunching(_ note: Notification) {
        // 确保工作目录存在
        try? FileManager.default.createDirectory(atPath: WORK_INBOX,
            withIntermediateDirectories: true)

        if !serviceUp() {
            startService()
            // 等服务起来（最多 8 秒）
            for _ in 0..<16 {
                if serviceUp() { break }
                Thread.sleep(forTimeInterval: 0.5)
            }
        }
        ensureOllama()

        let rect = NSRect(x: 0, y: 0, width: 900, height: 760)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "立丰脱敏"
        window.center()
        window.setFrameAutosaveName("LifengDesensitizeWindow")
        window.minSize = NSSize(width: 720, height: 560)

        let cfg = WKWebViewConfiguration()
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = WKWebView(frame: rect, configuration: cfg)
        webView.uiDelegate = self
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        window.contentView = webView

        // 不要在这里 registerForDraggedTypes：
        // 一旦注册却没实现 draggingEntered / performDragOperation，
        // AppKit 会把拖进来的文件当成"我能接但不处理"，直接吞掉，
        // 网页里的 drop 事件根本收不到——表现就是"拖进去没反应/说不支持"。
        // 文件拖放交给 WKWebView 自己转成 HTML5 drop 事件处理（index.html 有完整实现）。

        loadUI()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func loadUI() {
        if let url = URL(string: BASE + "/index.html") {
            webView.load(URLRequest(url: url))
        }
    }

    // ---- 独立窗口（去水印等工具页）----
    // 前端 window.open(url, '_blank', ...) 会走到这里。
    // 返回的 WKWebView 由系统用 action.request 自动加载，不用再手动 load。
    func webView(_ webView: WKWebView,
                 createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        // targetFrame 非空说明是普通跳转，不该开新窗
        guard navigationAction.targetFrame == nil else { return nil }

        // 顺手清掉已经关掉的窗口，避免数组只增不减
        extraWindows.removeAll { !$0.isVisible }

        let req = navigationAction.request
        let title = (req.url?.lastPathComponent ?? "").contains("watermark")
            ? "立丰去水印" : "立丰脱敏 · 工具"

        let rect = NSRect(x: 0, y: 0, width: 940, height: 820)
        let w = NSWindow(contentRect: rect,
                         styleMask: [.titled, .closable, .miniaturizable, .resizable],
                         backing: .buffered, defer: false)
        w.title = title
        w.minSize = NSSize(width: 720, height: 600)
        // 相对主窗口往右下错开一点，别完全盖住
        if let mf = window?.frame {
            w.setFrameOrigin(NSPoint(x: mf.origin.x + 40, y: mf.origin.y - 40))
        } else {
            w.center()
        }
        w.setFrameAutosaveName(title == "立丰去水印" ? "LifengWatermarkWindow" : "LifengToolWindow")

        let v = WKWebView(frame: rect, configuration: configuration)
        v.uiDelegate = self
        v.navigationDelegate = self
        v.setValue(false, forKey: "drawsBackground")
        w.contentView = v
        w.isReleasedWhenClosed = false      // 交给 extraWindows 管，关掉后不能野指针

        extraWindows.append(w)
        w.makeKeyAndOrderFront(nil)
        return v
    }

    // ---- JS 对话框 ----
    // 之前只声明了 WKUIDelegate 却没实现这几个方法，后果是网页里的
    // alert() 静默消失、confirm() 直接当取消 —— 用户点「清除」看着毫无反应，
    // 其实是被 confirm 吃掉了。这里补上原生面板。
    func webView(_ webView: WKWebView,
                 runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "好")
        if let w = window {
            a.beginSheetModal(for: w) { _ in completionHandler() }
        } else {
            a.runModal()
            completionHandler()
        }
    }

    func webView(_ webView: WKWebView,
                 runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "确定")
        a.addButton(withTitle: "取消")
        if let w = window {
            a.beginSheetModal(for: w) { r in
                completionHandler(r == .alertFirstButtonReturn)
            }
        } else {
            completionHandler(a.runModal() == .alertFirstButtonReturn)
        }
    }

    func webView(_ webView: WKWebView,
                 runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert()
        a.messageText = prompt
        a.addButton(withTitle: "确定")
        a.addButton(withTitle: "取消")
        let tf = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
        tf.stringValue = defaultText ?? ""
        a.accessoryView = tf
        if let w = window {
            a.beginSheetModal(for: w) { r in
                completionHandler(r == .alertFirstButtonReturn ? tf.stringValue : nil)
            }
        } else {
            completionHandler(a.runModal() == .alertFirstButtonReturn ? tf.stringValue : nil)
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // 拖文件到 Dock 图标
    func application(_ application: NSApplication, open urls: [URL]) {
        forward(urls.map { $0.path })
    }

    func forward(_ paths: [String]) {
        guard !paths.isEmpty else { return }
        let payload = ["paths": paths]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let url = URL(string: BASE + "/api/process") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        URLSession.shared.dataTask(with: req) { _, _, _ in
            DispatchQueue.main.async { self.loadUI() }
        }.resume()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)

// 菜单（保证 Cmd+Q / Cmd+W 可用）
let mainMenu = NSMenu()
let appItem = NSMenuItem()
mainMenu.addItem(appItem)
let appMenu = NSMenu()
appMenu.addItem(withTitle: "关于 立丰脱敏", action: nil, keyEquivalent: "")
appMenu.addItem(NSMenuItem.separator())
appMenu.addItem(withTitle: "隐藏 立丰脱敏", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
appMenu.addItem(withTitle: "退出 立丰脱敏", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
appItem.submenu = appMenu
app.mainMenu = mainMenu

app.run()
