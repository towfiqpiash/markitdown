import AppKit
import WebKit
import Foundation
import Network

@main
class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate, WKScriptMessageHandler {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var serverPort: Int = 8000
    var serverURL: URL?

    func applicationDidFinishLaunching(_ aNotification: Notification) {
        setupMenu()
        findAvailablePort()
        startPythonBackend()
        setupWindow()
        loadServerURL()
    }

    func setupMenu() {
        let mainMenu = NSMenu()

        // Application Menu
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenuItem.submenu = appMenu

        let appName = "convert2md"
        appMenu.addItem(withTitle: "About \(appName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")

        let hideOthers = NSMenuItem(title: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(hideOthers)

        appMenu.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Edit Menu (Standard macOS Copy/Paste/Select All)
        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "Edit")
        editMenuItem.submenu = editMenu

        editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        // View Menu (Reload)
        let viewMenuItem = NSMenuItem()
        mainMenu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "View")
        viewMenuItem.submenu = viewMenu

        let reloadItem = NSMenuItem(title: "Reload Page", action: #selector(reloadWebView), keyEquivalent: "r")
        reloadItem.target = self
        viewMenu.addItem(reloadItem)

        // Window Menu
        let windowMenuItem = NSMenuItem()
        mainMenu.addItem(windowMenuItem)
        let windowMenu = NSMenu(title: "Window")
        windowMenuItem.submenu = windowMenu
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = windowMenu
    }

    @objc func reloadWebView() {
        webView?.reload()
    }

    func findAvailablePort() {
        // Try default 8000 or find open port
        for port in 8000...8099 {
            if isPortAvailable(port: UInt16(port)) {
                self.serverPort = port
                break
            }
        }
        self.serverURL = URL(string: "http://127.0.0.1:\(serverPort)")
    }

    func isPortAvailable(port: in_port_t) -> Bool {
        let socketFileDescriptor = socket(AF_INET, SOCK_STREAM, 0)
        if socketFileDescriptor == -1 {
            return false
        }
        defer {
            close(socketFileDescriptor)
        }

        var addr = sockaddr_in()
        addr.sin_len = __uint8_t(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")

        return withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(socketFileDescriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }

    func startPythonBackend() {
        let process = Process()
        self.serverProcess = process

        // Locate python binary
        let fm = FileManager.default
        let bundlePath = Bundle.main.bundlePath
        let resourcePath = Bundle.main.resourcePath ?? bundlePath

        var pythonExecutable = "/usr/bin/python3"

        // Check relative venv or workspace venv paths
        let potentialPythons = [
            "\(resourcePath)/venv/bin/python3",
            "\(bundlePath)/Contents/Resources/venv/bin/python3",
            "\(bundlePath)/../../.venv/bin/python3",
            "/Users/towfiq/ClaudeProjects/markitdown/.venv/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3"
        ]

        for path in potentialPythons {
            if fm.fileExists(atPath: path) {
                pythonExecutable = path
                break
            }
        }

        process.executableURL = URL(fileURLWithPath: pythonExecutable)
        process.arguments = ["-m", "markitdown_ui", "--port", "\(serverPort)", "--host", "127.0.0.1"]

        var env = ProcessInfo.processInfo.environment
        let PYTHONPATH = "\(resourcePath):\(bundlePath)/../../packages/markitdown-ui/src:\(bundlePath)/../../packages/markitdown/src"
        if let existingPyPath = env["PYTHONPATH"] {
            env["PYTHONPATH"] = "\(PYTHONPATH):\(existingPyPath)"
        } else {
            env["PYTHONPATH"] = PYTHONPATH
        }
        process.environment = env

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
            print("Started MarkItDown backend process on port \(serverPort) with PID \(process.processIdentifier)")
        } catch {
            print("Failed to start MarkItDown backend process: \(error)")
        }
    }

    func setupWindow() {
        let windowSize = NSSize(width: 820, height: 680)
        let screenSize = NSScreen.main?.visibleFrame.size ?? NSSize(width: 1400, height: 900)
        let rect = NSRect(
            x: (screenSize.width - windowSize.width) / 2,
            y: (screenSize.height - windowSize.height) / 2,
            width: windowSize.width,
            height: windowSize.height
        )

        let mask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        window = NSWindow(contentRect: rect, styleMask: mask, backing: .buffered, defer: false)
        window.title = "convert2md"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.minSize = NSSize(width: 360, height: 480)
        window.delegate = self
        window.center()

        // Add native macOS translucency effect
        let visualEffect = NSVisualEffectView(frame: window.contentView!.bounds)
        visualEffect.autoresizingMask = [.width, .height]
        visualEffect.material = .underWindowBackground
        visualEffect.blendingMode = .behindWindow
        visualEffect.state = .active
        window.contentView?.addSubview(visualEffect)

        let contentController = WKUserContentController()
        contentController.add(self, name: "copyText")
        contentController.add(self, name: "saveFile")
        contentController.add(self, name: "openSystemSettings")
        contentController.add(self, name: "readClipboardText")
        contentController.add(self, name: "toggleZoom")

        let webConfiguration = WKWebViewConfiguration()
        webConfiguration.userContentController = contentController
        webConfiguration.preferences.setValue(true, forKey: "developerExtrasEnabled")

        webView = DraggableWebView(frame: window.contentView!.bounds, configuration: webConfiguration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "copyText", let text = message.body as? String {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(text, forType: .string)
        } else if message.name == "saveFile", let dict = message.body as? [String: String] {
            let filename = dict["filename"] ?? "output.md"
            let content = dict["content"] ?? ""

            let savePanel = NSSavePanel()
            savePanel.nameFieldStringValue = filename
            savePanel.begin { result in
                if result == .OK, let url = savePanel.url {
                    try? content.write(to: url, atomically: true, encoding: .utf8)
                }
            }
        } else if message.name == "openSystemSettings" {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
                NSWorkspace.shared.open(url)
            }
        } else if message.name == "toggleZoom" {
            window.zoom(nil)
        } else if message.name == "readClipboardText" {
            let text = NSPasteboard.general.string(forType: .string) ?? ""
            // Encode as a single-element JSON array so it can be safely spread as a JS string argument.
            if let data = try? JSONSerialization.data(withJSONObject: [text]),
               let json = String(data: data, encoding: .utf8) {
                let js = "window.__nativeClipboardResult && window.__nativeClipboardResult(...\(json))"
                webView.evaluateJavaScript(js, completionHandler: nil)
            }
        }
    }

    func loadServerURL() {
        guard let url = serverURL else { return }

        // Poll server until ready
        func checkAndLoad(attemptsLeft: Int) {
            var request = URLRequest(url: url)
            request.timeoutInterval = 1.0

            let task = URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
                DispatchQueue.main.async {
                    if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                        self?.webView.load(URLRequest(url: url))
                    } else if attemptsLeft > 0 {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                            checkAndLoad(attemptsLeft: attemptsLeft - 1)
                        }
                    } else {
                        // Fallback load
                        self?.webView.load(URLRequest(url: url))
                    }
                }
            }
            task.resume()
        }

        checkAndLoad(attemptsLeft: 20)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let process = serverProcess, process.isRunning {
            print("Terminating MarkItDown backend process (PID \(process.processIdentifier))")
            process.terminate()
            // Wait up to 1s for exit
            let startTime = Date()
            while process.isRunning && Date().timeIntervalSince(startTime) < 1.0 {
                usleep(50000)
            }
            if process.isRunning {
                kill(process.processIdentifier, SIGKILL)
            }
        }
    }

    // Handle webview open panel (file dialogs)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let openPanel = NSOpenPanel()
        openPanel.allowsMultipleSelection = parameters.allowsMultipleSelection
        openPanel.canChooseDirectories = parameters.allowsDirectories
        openPanel.begin { result in
            if result == .OK {
                completionHandler(openPanel.urls)
            } else {
                completionHandler(nil)
            }
        }
    }
}

class DraggableWebView: WKWebView {
    override var mouseDownCanMoveWindow: Bool {
        return true
    }
}
