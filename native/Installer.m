#import <Cocoa/Cocoa.h>

extern NSString *AtomLensText(NSString *zh, NSString *en);

@interface AtomLensInstaller : NSObject <NSApplicationDelegate>
@property NSWindow *window;
@property NSButton *installButton;
@property NSButton *helperCheckbox;
@property NSButton *codexButton;
@property NSButton *detailsButton;
@property NSTextField *status;
@property NSProgressIndicator *progress;
@property NSString *log;
@property BOOL busy;
@property NSString *language;
@end

@implementation AtomLensInstaller
- (NSTextField *)label:(NSString *)text frame:(NSRect)frame size:(CGFloat)size {
    NSTextField *label = [NSTextField wrappingLabelWithString:text];
    label.frame = frame;
    label.font = [NSFont systemFontOfSize:size];
    [self.window.contentView addSubview:label];
    return label;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    if (self.window) { [self.window makeKeyAndOrderFront:nil]; return; }
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 600, 450)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
        backing:NSBackingStoreBuffered defer:NO];
    self.language = AtomLensText(@"zh-CN", @"en");
    self.window.title = AtomLensText(@"Atom Lens · Codex 插件", @"Atom Lens · Codex Plugin");
    self.window.releasedWhenClosed = NO;
    self.window.titlebarAppearsTransparent = YES;
    NSImageView *icon = [[NSImageView alloc] initWithFrame:NSMakeRect(52, 306, 96, 96)];
    icon.image = [NSImage imageNamed:NSImageNameApplicationIcon];
    icon.imageScaling = NSImageScaleProportionallyUpOrDown;
    [self.window.contentView addSubview:icon];
    NSTextField *title = [self label:@"Atom Lens" frame:NSMakeRect(168, 353, 380, 42) size:30];
    title.font = [NSFont systemFontOfSize:30 weight:NSFontWeightSemibold];
    [self label:AtomLensText(@"Codex 插件", @"Codex Plugin") frame:NSMakeRect(168, 314, 380, 38) size:14];
    self.helperCheckbox = [NSButton checkboxWithTitle:AtomLensText(@"同时安装远程保存助手", @"Install the remote export helper") target:nil action:nil];
    self.helperCheckbox.frame = NSMakeRect(50, 193, 460, 25);
    [self.window.contentView addSubview:self.helperCheckbox];
    self.status = [self label:@"" frame:NSMakeRect(52, 103, 496, 44) size:13];
    self.status.textColor = NSColor.secondaryLabelColor;
    self.progress = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(52, 78, 496, 3)];
    self.progress.style = NSProgressIndicatorStyleBar;
    self.progress.indeterminate = YES; self.progress.hidden = YES;
    [self.window.contentView addSubview:self.progress];
    self.installButton = [NSButton buttonWithTitle:AtomLensText(@"安装到 Codex", @"Install for Codex") target:self action:@selector(install:)];
    self.installButton.frame = NSMakeRect(392, 30, 158, 34);
    self.installButton.keyEquivalent = @"\r";
    [self.window.contentView addSubview:self.installButton];
    self.codexButton = [NSButton buttonWithTitle:AtomLensText(@"打开 Codex", @"Open Codex") target:self action:@selector(openCodex:)];
    self.codexButton.frame = NSMakeRect(255, 30, 130, 34);
    [self.window.contentView addSubview:self.codexButton];
    self.detailsButton = [NSButton buttonWithTitle:AtomLensText(@"查看详情", @"Details") target:self action:@selector(showDetails:)];
    self.detailsButton.frame = NSMakeRect(48, 30, 104, 34); self.detailsButton.enabled = NO;
    [self.window.contentView addSubview:self.detailsButton];
    [self.window center]; [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}
- (BOOL)runScript:(NSString *)script output:(NSString **)output {
    NSString *resources = NSBundle.mainBundle.resourcePath;
    NSTask *task = [NSTask new]; NSPipe *pipe = [NSPipe pipe];
    task.executableURL = [NSURL fileURLWithPath:[resources stringByAppendingPathComponent:@"python/bin/python3"]];
    task.arguments = @[@"-I", @"-B", [resources stringByAppendingPathComponent:script]];
    task.currentDirectoryURL = [NSURL fileURLWithPath:resources];
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    [environment removeObjectForKey:@"PYTHONHOME"];
    [environment removeObjectForKey:@"PYTHONPATH"];
    environment[@"PATH"] = [@"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" stringByAppendingString:environment[@"PATH"] ?: @""];
    environment[@"PYTHONUTF8"] = @"1";
    environment[@"PYTHONDONTWRITEBYTECODE"] = @"1";
    task.environment = environment;
    task.standardOutput = pipe; task.standardError = pipe;
    task.standardInput = NSFileHandle.fileHandleWithNullDevice;
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        *output = error.localizedDescription;
        return NO;
    }
    NSData *data = [pipe.fileHandleForReading readDataToEndOfFile];
    [task waitUntilExit];
    *output = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: AtomLensText(@"无法读取安装结果。", @"Could not read the installation result.");
    return task.terminationStatus == 0;
}
- (void)install:(id)sender {
    if (self.busy) return;
    NSString *location = NSBundle.mainBundle.bundlePath;
    if ([location hasPrefix:@"/Volumes/"] || [location containsString:@"/AppTranslocation/"]) {
        self.status.stringValue = AtomLensText(@"请先将 Atom Lens 拖入 Applications 文件夹，再从那里打开并安装。", @"Move Atom Lens to Applications, then reopen it and install the plugin.");
        return;
    }
    self.busy = YES; self.installButton.enabled = NO; self.helperCheckbox.enabled = NO;
    [self.window standardWindowButton:NSWindowCloseButton].enabled = NO;
    self.codexButton.enabled = NO; self.detailsButton.enabled = NO;
    BOOL helper = self.helperCheckbox.state == NSControlStateValueOn;
    self.status.stringValue = AtomLensText(@"正在安装，请稍候…", @"Installing…");
    self.progress.hidden = NO; [self.progress startAnimation:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSString *installLog = @"", *helperLog = @"";
        BOOL installed = [self runScript:@"install.py" output:&installLog];
        BOOL helperInstalled = !helper || !installed || [self runScript:@"native/install_helper.py" output:&helperLog];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.log = [NSString stringWithFormat:@"%@\n%@", installLog, helperLog];
            [self.progress stopAnimation:nil]; self.progress.hidden = YES;
            self.busy = NO; self.installButton.enabled = YES; self.helperCheckbox.enabled = YES;
            [self.window standardWindowButton:NSWindowCloseButton].enabled = YES;
            self.codexButton.enabled = YES; self.detailsButton.enabled = YES;
            if (installed) {
                self.installButton.title = AtomLensText(@"重新安装", @"Reinstall");
                self.status.stringValue = helperInstalled ? AtomLensText(@"安装完成。请回到 Codex，重新打开聊天。\n请保留 Applications 中的 Atom Lens。", @"Installed. Reopen the chat in Codex. Keep Atom Lens in Applications.") : AtomLensText(@"插件已安装；保存助手安装未完成。\n可先使用查看器，详情中可查看原因。", @"Plugin installed. The export helper failed. See Details.");
            } else {
                self.status.stringValue = [installLog containsString:@"Codex CLI"] ? AtomLensText(@"未找到可用的 Codex。请先安装或更新 Codex，再重试。", @"Install or update Codex, then try again.") : AtomLensText(@"安装未完成。请查看详情，修复后重试。", @"Installation failed. See Details.");
            }
        });
    });
}
- (void)showDetails:(id)sender {
    NSAlert *alert = [NSAlert new]; alert.messageText = AtomLensText(@"安装详情", @"Installation Details");
    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(0, 0, 500, 250)];
    scroll.hasVerticalScroller = YES;
    NSTextView *text = [[NSTextView alloc] initWithFrame:scroll.bounds];
    text.editable = NO; text.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightRegular];
    text.string = self.log ?: AtomLensText(@"尚无安装记录。", @"No installation log."); scroll.documentView = text;
    alert.accessoryView = scroll; [alert addButtonWithTitle:AtomLensText(@"关闭", @"Close")];
    [alert beginSheetModalForWindow:self.window completionHandler:nil];
}
- (void)openCodex:(id)sender {
    for (NSString *directory in @[@"/Applications", [NSHomeDirectory() stringByAppendingPathComponent:@"Applications"]]) {
        for (NSString *name in @[@"Codex.app", @"ChatGPT.app"]) {
            NSString *path = [directory stringByAppendingPathComponent:name];
            if ([NSFileManager.defaultManager fileExistsAtPath:path]) {
                [NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:path]];
                return;
            }
        }
    }
    self.status.stringValue = AtomLensText(@"未找到 Codex 桌面应用，请先安装 Codex。", @"Codex was not found. Install Codex first.");
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (self.busy) { NSBeep(); return NSTerminateCancel; }
    return NSTerminateNow;
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }
@end

static AtomLensInstaller *installer;
void ShowAtomLensInstaller(void) {
    if (installer && !installer.busy && ![installer.language isEqualToString:AtomLensText(@"zh-CN", @"en")]) {
        [installer.window close];
        installer = nil;
    }
    if (!installer) installer = [AtomLensInstaller new];
    [installer applicationDidFinishLaunching:[NSNotification notificationWithName:NSApplicationDidFinishLaunchingNotification object:NSApp]];
}
BOOL AtomLensInstallationBusy(void) {
    return installer.busy;
}

void RefreshAtomLensInstallerLanguage(void) {
    if (installer.window.visible && !installer.busy) ShowAtomLensInstaller();
}
