#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

extern void ShowAtomLensInstaller(void);
extern BOOL AtomLensInstallationBusy(void);
extern void RefreshAtomLensInstallerLanguage(void);

static NSString *const AtomLensLanguageKey = @"AtomLensInterfaceLanguage";

NSString *AtomLensText(NSString *zh, NSString *en) {
    return [[NSUserDefaults.standardUserDefaults stringForKey:AtomLensLanguageKey] isEqualToString:@"en"] ? en : zh;
}

@interface AtomLensDesktop : NSObject <NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate>
@property NSWindow *window;
@property WKWebView *web;
@property NSTask *backend;
@property NSPipe *input;
@property NSURL *baseURL;
@property NSArray<NSString *> *pendingFiles;
@property BOOL ready;
@end

@implementation AtomLensDesktop
- (void)createMenus {
    NSMenu *bar = [NSMenu new];
    NSMenuItem *application = [NSMenuItem new]; [bar addItem:application];
    NSMenu *appMenu = [NSMenu new]; application.submenu = appMenu;
    [appMenu addItemWithTitle:AtomLensText(@"关于 Atom Lens", @"About Atom Lens") action:@selector(orderFrontStandardAboutPanel:) keyEquivalent:@""];
    [appMenu addItemWithTitle:AtomLensText(@"Codex 插件…", @"Codex Plugin…") action:@selector(showInstaller:) keyEquivalent:@","];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:AtomLensText(@"退出 Atom Lens", @"Quit Atom Lens") action:@selector(terminate:) keyEquivalent:@"q"];
    NSMenuItem *file = [NSMenuItem new]; [bar addItem:file]; file.submenu = [[NSMenu alloc] initWithTitle:AtomLensText(@"文件", @"File")];
    [file.submenu addItemWithTitle:AtomLensText(@"打开…", @"Open…") action:@selector(openDocument:) keyEquivalent:@"o"];
    [file.submenu addItemWithTitle:AtomLensText(@"服务器…", @"Servers…") action:@selector(showServers:) keyEquivalent:@"k"];
    NSMenuItem *edit = [NSMenuItem new]; [bar addItem:edit]; edit.submenu = [[NSMenu alloc] initWithTitle:AtomLensText(@"编辑", @"Edit")];
    for (NSArray *item in @[@[@"撤销",@"Undo",@"undo:",@"z"],@[@"剪切",@"Cut",@"cut:",@"x"],@[@"拷贝",@"Copy",@"copy:",@"c"],@[@"粘贴",@"Paste",@"paste:",@"v"],@[@"全选",@"Select All",@"selectAll:",@"a"]]) {
        [edit.submenu addItemWithTitle:AtomLensText(item[0], item[1]) action:NSSelectorFromString(item[2]) keyEquivalent:item[3]];
    }
    NSApp.mainMenu = bar;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    [self createMenus];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1160, 780)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskFullSizeContentView
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Atom Lens"; self.window.minSize = NSMakeSize(850, 600);
    self.window.titlebarAppearsTransparent = YES;
    self.window.titleVisibility = NSWindowTitleHidden;
    self.window.releasedWhenClosed = NO;
    WKWebViewConfiguration *configuration = [WKWebViewConfiguration new];
    [configuration.userContentController addScriptMessageHandler:self name:@"atomLens"];
    self.web = [[WKWebView alloc] initWithFrame:self.window.contentView.bounds configuration:configuration];
    self.web.translatesAutoresizingMaskIntoConstraints = NO;
    self.web.navigationDelegate = self; self.web.UIDelegate = self;
    [self.window.contentView addSubview:self.web];
    NSLayoutGuide *layout = self.window.contentLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.web.topAnchor constraintEqualToAnchor:layout.topAnchor],
        [self.web.bottomAnchor constraintEqualToAnchor:layout.bottomAnchor],
        [self.web.leadingAnchor constraintEqualToAnchor:layout.leadingAnchor],
        [self.web.trailingAnchor constraintEqualToAnchor:layout.trailingAnchor],
    ]];
    [self.window center]; [self.window makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
    NSString *loading = [NSString stringWithFormat:@"<html><body style='font:15px -apple-system;padding:36px'>%@</body></html>", AtomLensText(@"正在启动 Atom Lens…", @"Starting Atom Lens…")];
    [self.web loadHTMLString:loading baseURL:nil];
    [self startBackend];
}
- (void)startBackend {
    NSString *resources = NSBundle.mainBundle.resourcePath;
    self.backend = [NSTask new]; self.input = [NSPipe pipe]; NSPipe *output = [NSPipe pipe];
    self.backend.executableURL = [NSURL fileURLWithPath:[resources stringByAppendingPathComponent:@"python/bin/python3"]];
    self.backend.arguments = @[@"-I", @"-B", @"-u", [resources stringByAppendingPathComponent:@"native/desktop_host.py"]];
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    [environment removeObjectForKey:@"PYTHONHOME"]; [environment removeObjectForKey:@"PYTHONPATH"];
    environment[@"PYTHONDONTWRITEBYTECODE"] = @"1"; environment[@"PYTHONUTF8"] = @"1";
    environment[@"PATH"] = [@"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" stringByAppendingString:environment[@"PATH"] ?: @""];
    self.backend.environment = environment;
    self.backend.standardInput = self.input; self.backend.standardOutput = output;
    self.backend.standardError = [NSFileHandle fileHandleWithStandardError];
    NSError *error = nil;
    if (![self.backend launchAndReturnError:&error]) { [self showError:error.localizedDescription]; return; }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSMutableData *line = [NSMutableData new];
        while (line.length < 4096) {
            NSData *byte = [output.fileHandleForReading readDataOfLength:1];
            if (!byte.length || ((const char *)byte.bytes)[0] == '\n') break;
            [line appendData:byte];
        }
        NSString *address = [[NSString alloc] initWithData:line encoding:NSUTF8StringEncoding];
        dispatch_async(dispatch_get_main_queue(), ^{
            NSURL *url = [NSURL URLWithString:address ?: @""];
            if (![url.host isEqualToString:@"127.0.0.1"] || ![url.scheme isEqualToString:@"http"] || !url.port) {
                [self showError:AtomLensText(@"内置运行环境未能启动。请重新打开 Atom Lens。", @"The bundled runtime did not start. Reopen Atom Lens.")]; return;
            }
            self.baseURL = url;
            [self.web loadRequest:[NSURLRequest requestWithURL:url]];
        });
    });
}
- (void)showError:(NSString *)message {
    NSAlert *alert = [NSAlert new]; alert.messageText = @"Atom Lens";
    alert.informativeText = message; [alert beginSheetModalForWindow:self.window completionHandler:nil];
}
- (void)respond:(id)identifier value:(NSDictionary *)value {
    NSData *json = [NSJSONSerialization dataWithJSONObject:@[identifier ?: @0, value] options:0 error:nil];
    NSString *payload = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    [self.web evaluateJavaScript:[NSString stringWithFormat:@"window.atomLensNativeResult(...%@)", payload] completionHandler:nil];
}
- (void)openPanelAt:(NSString *)directory completion:(void (^)(NSArray<NSString *> *))completion {
    NSOpenPanel *panel = [NSOpenPanel openPanel]; panel.canChooseDirectories = YES;
    panel.allowsMultipleSelection = YES; panel.prompt = AtomLensText(@"打开", @"Open");
    BOOL isDirectory = NO;
    if ([directory isKindOfClass:NSString.class] && directory.isAbsolutePath &&
        [NSFileManager.defaultManager fileExistsAtPath:directory isDirectory:&isDirectory] && isDirectory) {
        panel.directoryURL = [NSURL fileURLWithPath:directory isDirectory:YES];
    }
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        NSMutableArray *paths = [NSMutableArray new];
        if (response == NSModalResponseOK) for (NSURL *url in panel.URLs) [paths addObject:url.path];
        completion(paths);
    }];
}
- (void)deliverFiles:(NSArray<NSString *> *)paths {
    if (!paths.count) return;
    if (!self.ready) { self.pendingFiles = paths; return; }
    NSString *json = [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:paths options:0 error:nil] encoding:NSUTF8StringEncoding];
    [self.web evaluateJavaScript:[NSString stringWithFormat:@"window.atomLensOpenPaths(%@)", json] completionHandler:nil];
}
- (void)openDocument:(id)sender {
    if (self.ready) [self.web evaluateJavaScript:@"window.atomLensOpenLocal?.()" completionHandler:nil];
}
- (void)showInstaller:(id)sender { ShowAtomLensInstaller(); }
- (void)showServers:(id)sender { [self.web evaluateJavaScript:@"window.atomLensShowServers?.()" completionHandler:nil]; }
- (void)application:(NSApplication *)application openFiles:(NSArray<NSString *> *)filenames {
    [self deliverFiles:filenames]; [application replyToOpenOrPrint:NSApplicationDelegateReplySuccess];
}
- (void)userContentController:(WKUserContentController *)controller didReceiveScriptMessage:(WKScriptMessage *)message {
    if (!message.frameInfo.mainFrame || ![message.body isKindOfClass:NSDictionary.class] ||
        ![message.frameInfo.request.URL.host isEqualToString:@"127.0.0.1"] ||
        ![message.frameInfo.request.URL.port isEqual:self.baseURL.port]) return;
    NSString *action = message.body[@"action"]; id identifier = message.body[@"id"];
    if ([action isEqualToString:@"ready"]) { self.ready = YES; [self deliverFiles:self.pendingFiles]; self.pendingFiles = nil; }
    else if ([action isEqualToString:@"readLanguage"]) {
        [self respond:identifier value:@{@"language":AtomLensText(@"zh-CN", @"en")}];
    } else if ([action isEqualToString:@"setLanguage"]) {
        id language = message.body[@"language"];
        if ([@[@"en", @"zh-CN"] containsObject:language ?: NSNull.null]) {
            [NSUserDefaults.standardUserDefaults setObject:language forKey:AtomLensLanguageKey];
            [self createMenus];
            RefreshAtomLensInstallerLanguage();
        }
    }
    else if ([action isEqualToString:@"setAppearance"]) {
        id mode = message.body[@"mode"], dark = message.body[@"dark"];
        if (![@[@"light", @"dark", @"system"] containsObject:mode ?: NSNull.null] || ![dark isKindOfClass:NSNumber.class]) return;
        self.window.appearance = [mode isEqual:@"system"] ? nil : [NSAppearance appearanceNamed:[mode isEqual:@"dark"] ? NSAppearanceNameDarkAqua : NSAppearanceNameAqua];
        self.window.backgroundColor = [dark boolValue] ? [NSColor colorWithSRGBRed:21.0/255 green:21.0/255 blue:23.0/255 alpha:1.0] : NSColor.whiteColor;
    }
    else if ([action isEqualToString:@"openFiles"]) {
        [self openPanelAt:message.body[@"directory"] completion:^(NSArray *paths) { [self respond:identifier value:@{@"paths":paths}]; }];
    } else if ([action isEqualToString:@"chooseDirectory"]) {
        NSOpenPanel *panel = [NSOpenPanel openPanel]; panel.canChooseFiles = NO; panel.canChooseDirectories = YES;
        panel.canCreateDirectories = YES; panel.prompt = AtomLensText(@"保存到此目录", @"Save Here");
        [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
            [self respond:identifier value:@{@"path":response == NSModalResponseOK ? panel.URL.path : @""}];
        }];
    } else if ([action isEqualToString:@"installCodex"]) {
        ShowAtomLensInstaller(); [self respond:identifier value:@{}];
    }
}
- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)action decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURL *url = action.request.URL;
    BOOL allowed = [url.scheme isEqualToString:@"about"] ||
        ([url.host isEqualToString:@"127.0.0.1"] && [url.port isEqual:self.baseURL.port] && [url.path hasPrefix:self.baseURL.path]);
    decisionHandler(allowed ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel);
}
- (void)webView:(WKWebView *)webView runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(NSArray<NSURL *> *))completionHandler {
    NSOpenPanel *panel = [NSOpenPanel openPanel]; panel.allowsMultipleSelection = parameters.allowsMultipleSelection;
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) { completionHandler(response == NSModalResponseOK ? panel.URLs : nil); }];
}
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    if (error.code != NSURLErrorCancelled) [self showError:error.localizedDescription];
}
- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    if (error.code != NSURLErrorCancelled) [self showError:error.localizedDescription];
}
- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView {
    [self showError:AtomLensText(@"查看窗口意外退出，请重新打开 Atom Lens。", @"The viewer closed unexpectedly. Reopen Atom Lens.")];
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (AtomLensInstallationBusy()) { NSBeep(); return NSTerminateCancel; }
    return NSTerminateNow;
}
- (void)applicationWillTerminate:(NSNotification *)notification {
    [self.input.fileHandleForWriting closeFile];
    // Closing stdin lets the host release local and SSH child processes.
    if (self.backend.running) {
        dispatch_semaphore_t finished = dispatch_semaphore_create(0);
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ [self.backend waitUntilExit]; dispatch_semaphore_signal(finished); });
        if (dispatch_semaphore_wait(finished, dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC))) [self.backend terminate];
    }
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        AtomLensDesktop *delegate = [AtomLensDesktop new]; app.delegate = delegate; [app run];
    }
    return 0;
}
