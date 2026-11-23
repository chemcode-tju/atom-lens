#import <Cocoa/Cocoa.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>


@interface SnapshotSaver : NSObject <NSApplicationDelegate>
@property NSStatusItem *statusItem;
@property NSTask *connection;
@property BOOL stopping;
@property NSTextField *configField;
@property NSComboBox *hostField;
@property NSTextField *queueField;
@property NSMenuItem *settingsItem;
@property NSMenu *hostMenu;

@end

@implementation SnapshotSaver
- (NSURL *)pythonURL {
    NSString *path = [NSBundle.mainBundle pathForResource:@"python-executable" ofType:@"txt"];
    NSString *python = path ? [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] : nil;
    python = [python stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    return [NSURL fileURLWithPath:python.length ? python : @"/usr/bin/python3"];
}
- (void)setStatus:(NSString *)title {
    self.statusItem.button.title = title;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    self.statusItem = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
    [self setStatus:@"结构快照 · 连接中"];
    NSMenu *menu = [NSMenu new]; menu.autoenablesItems = NO;
    self.settingsItem = [[NSMenuItem alloc] initWithTitle:@"添加独立连接…" action:@selector(configure:) keyEquivalent:@""];
    self.settingsItem.target = self; [menu addItem:self.settingsItem];
    self.hostMenu = [NSMenu new];
    NSMenuItem *hostList = [[NSMenuItem alloc] initWithTitle:@"服务器" action:nil keyEquivalent:@""];
    hostList.submenu = self.hostMenu; [menu addItem:hostList];
    [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *quit = [[NSMenuItem alloc] initWithTitle:@"退出保存助手" action:@selector(quitHelper:) keyEquivalent:@""];
    quit.target = self; [menu addItem:quit]; self.statusItem.menu = menu;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ [self watch]; });
}
- (void)showHosts:(NSArray *)hosts {
    [self.hostMenu removeAllItems];
    NSMutableArray *online = [NSMutableArray array];
    for (NSDictionary *profile in hosts) {
        BOOL ready = [profile[@"ready"] boolValue];
        NSString *host = profile[@"host"];
        if (ready) [online addObject:host];
        NSString *mode = [profile[@"automatic"] boolValue] ? @"自动" : @"独立配置";
        NSString *status = ready ? @"已连接" : [profile[@"missing"] boolValue] ? @"未安装查看器" : @"未连接";
        NSString *title = [NSString stringWithFormat:@"%@ · %@ · %@",host,mode,status];
        NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:title action:@selector(configure:) keyEquivalent:@""];
        item.target = self; item.representedObject = profile; [self.hostMenu addItem:item];
    }
    NSString *summary = online.count==1 ? online.firstObject :
        online.count ? [NSString stringWithFormat:@"%lu 台已连接",(unsigned long)online.count] : @"等待远程连接";
    [self setStatus:[@"结构快照 · " stringByAppendingString:summary]];
}
- (id)runSetup:(NSDictionary *)request error:(NSString **)message {
    NSTask *task = [NSTask new]; NSPipe *output = [NSPipe pipe], *input = [NSPipe pipe];
    task.executableURL = [self pythonURL];
    task.arguments = @[@"-E", @"-s", @"-B", [NSBundle.mainBundle pathForResource:@"connection" ofType:@"py"]];
    task.standardInput = input; task.standardOutput = output; task.standardError = output;
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) { *message = error.localizedDescription; return nil; }
    [input.fileHandleForWriting writeData:[NSJSONSerialization dataWithJSONObject:request options:0 error:nil]];
    [input.fileHandleForWriting closeFile];
    NSData *data = [output.fileHandleForReading readDataToEndOfFile];
    [task waitUntilExit];
    id result = task.terminationStatus == 0 ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    if (!result) *message = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"SSH 配置失败";
    return result;
}
- (void)refreshHosts {
    NSString *error;
    NSArray *hosts = [self runSetup:@{@"action":@"aliases", @"config":self.configField.stringValue} error:&error];
    NSString *selected = self.hostField.stringValue;
    [self.hostField removeAllItems];
    if (hosts) [self.hostField addItemsWithObjectValues:hosts];
    self.hostField.stringValue = selected;
    self.hostField.toolTip = hosts ? nil : error;
}
- (void)browseConfig:(id)sender {
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.showsHiddenFiles = YES; panel.canChooseDirectories = NO;
    panel.directoryURL = [NSURL fileURLWithPath:[self.configField.stringValue.stringByExpandingTildeInPath stringByDeletingLastPathComponent]];
    if ([panel runModal] == NSModalResponseOK) {
        self.configField.stringValue = panel.URL.path;
        [self refreshHosts];
    }
}
- (void)showError:(NSString *)message {
    NSAlert *alert = [NSAlert new]; alert.messageText = @"SSH 连接设置失败";
    alert.informativeText = message; [NSApp activateIgnoringOtherApps:YES]; [alert runModal];
}
- (void)configure:(id)sender {
    NSDictionary *old = [sender representedObject];
    NSAlert *alert = [NSAlert new]; alert.messageText = @"独立 SSH 连接设置";
    alert.informativeText = @"Codex 活跃的远程主机会自动识别。需要固定连接或自定义队列路径时，在这里单独配置该服务器。";
    [alert addButtonWithTitle:@"安装脚本并连接"]; [alert addButtonWithTitle:@"取消"];
    BOOL custom = old && ![old[@"automatic"] boolValue];
    if (custom) [alert addButtonWithTitle:@"移除独立配置"];
    NSView *form = [[NSView alloc] initWithFrame:NSMakeRect(0,0,400,104)];
    self.configField = [NSTextField textFieldWithString:old[@"config"] ?: @"~/.ssh/config"];
    self.hostField = [[NSComboBox alloc] initWithFrame:NSMakeRect(85,38,305,24)];
    self.hostField.stringValue = old[@"host"] ?: @"";
    self.queueField = [NSTextField textFieldWithString:old[@"queue"] ?: @"~/.local/share/structure-viewer/snapshot-queue.pyz"];
    self.configField.frame = NSMakeRect(85,72,240,24);
    self.configField.target = self; self.configField.action = @selector(configEntered:);
    self.queueField.frame = NSMakeRect(85,4,305,24);
    NSArray *fields = @[self.configField,self.hostField,self.queueField];
    NSArray *labels = @[@"SSH 配置", @"主机别名", @"远程脚本"];
    for (NSUInteger i=0;i<fields.count;i++) {
        NSControl *field=fields[i]; NSTextField *label=[NSTextField labelWithString:labels[i]];
        label.frame=NSMakeRect(0,field.frame.origin.y+3,82,20); field.accessibilityLabel=labels[i];
        [form addSubview:label]; [form addSubview:field];
    }
    NSButton *browse=[NSButton buttonWithTitle:@"选择…" target:self action:@selector(browseConfig:)];
    browse.frame=NSMakeRect(329,70,68,28); [form addSubview:browse];
    if (old) {self.configField.editable=NO; self.hostField.enabled=NO; browse.enabled=NO;}
    [self refreshHosts]; alert.accessoryView=form;
    [NSApp activateIgnoringOtherApps:YES];
    NSModalResponse choice=[alert runModal];
    if (custom && choice==NSAlertThirdButtonReturn) {
        NSString *error;
        if (![self runSetup:@{@"action":@"remove",@"config":old[@"config"],@"host":old[@"host"]} error:&error]) [self showError:error];
        return;
    }
    if (choice != NSAlertFirstButtonReturn) return;
    NSDictionary *request=@{@"action":@"install",@"config":self.configField.stringValue,@"host":self.hostField.stringValue,@"queue":self.queueField.stringValue};
    self.settingsItem.enabled=NO;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0), ^{
        NSString *error; id installed=[self runSetup:request error:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.settingsItem.enabled=YES;
            if (!installed) [self showError:error];
        });
    });
}
- (void)configEntered:(id)sender { [self refreshHosts]; }
- (void)quitHelper:(id)sender { self.stopping = YES; [self.connection terminate]; [NSApp terminate:nil]; }
- (void)applicationWillTerminate:(NSNotification *)notification { self.stopping = YES; [self.connection terminate]; }
- (NSString *)save:(NSData *)data name:(NSString *)name language:(NSString *)language {
    BOOL english = [language isEqualToString:@"en"];
    [NSApp activateIgnoringOtherApps:YES];
    NSSavePanel *panel = [NSSavePanel savePanel];
    panel.title = english ? @"Save structure image or animation" : @"保存结构图像或动画";
    panel.prompt = english ? @"Save" : @"保存";
    panel.nameFieldLabel = english ? @"Save As:" : @"存储为："; panel.nameFieldStringValue = name;
    panel.allowedContentTypes = @[[UTType typeWithFilenameExtension:name.pathExtension]];
    panel.canCreateDirectories = YES;
    panel.directoryURL = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    if ([panel runModal] != NSModalResponseOK) return @"cancelled";
    NSError *error = nil;
    if (![data writeToURL:panel.URL options:NSDataWritingAtomic error:&error]) {
        NSAlert *alert = [NSAlert new]; alert.messageText = english ? @"Save failed" : @"保存失败"; alert.informativeText = error.localizedDescription;
        [alert runModal]; return @"error";
    }
    return @"saved";
}
- (NSString *)receive:(NSDictionary *)snapshot {
    NSString *name = snapshot[@"name"], *encoded = snapshot[@"data"];
    NSData *image = [encoded isKindOfClass:NSString.class] ? [[NSData alloc] initWithBase64EncodedString:encoded options:0] : nil;
    NSDictionary *signatures = @{@"png": @[@137,@80,@78,@71,@13,@10,@26,@10], @"jpeg": @[@255,@216,@255], @"pdf": @[@37,@80,@68,@70,@45], @"gif": @[@71,@73,@70,@56]};
    NSArray *signature = [name isKindOfClass:NSString.class] ? signatures[name.pathExtension] : nil;
    BOOL movie = [@[@"mp4",@"mov"] containsObject:name.pathExtension];
    BOOL valid = image.length && (signature || movie) &&
                 [name isEqualToString:name.lastPathComponent] && image.length >= signature.count;
    for (NSUInteger i = 0; valid && i < signature.count; i++) valid = ((const unsigned char *)image.bytes)[i] == [signature[i] unsignedCharValue];
    if (movie) valid = valid && image.length >= 12 && memcmp(((const char *)image.bytes)+4, "ftyp", 4) == 0;
    if (!valid) return @"error";
    __block NSString *result;
    dispatch_sync(dispatch_get_main_queue(), ^{ result = [self save:image name:name language:snapshot[@"language"]]; });
    return result;
}
- (void)watch {
    while (!self.stopping) {
        @autoreleasepool {
            NSTask *task = [NSTask new]; NSPipe *output = [NSPipe pipe]; NSPipe *input = [NSPipe pipe];
            self.connection = task;
            task.executableURL = [self pythonURL];
            task.arguments = @[@"-E", @"-s", @"-B", @"-u", [NSBundle.mainBundle pathForResource:@"broker" ofType:@"py"]];
            task.standardOutput = output; task.standardInput = input;
            task.standardError = [NSFileHandle fileHandleWithNullDevice];
            if ([task launchAndReturnError:nil]) {
                if (self.stopping) [task terminate];
                NSMutableData *buffer = [NSMutableData new];
                @try {
                    while (!self.stopping) {
                        NSData *block = [output.fileHandleForReading availableData];
                        if (!block.length) break;
                        [buffer appendData:block];
                        while (YES) {
                            NSRange newline = [buffer rangeOfData:[NSData dataWithBytes:"\n" length:1] options:0 range:NSMakeRange(0,buffer.length)];
                            if (newline.location == NSNotFound) break;
                            NSData *line = [buffer subdataWithRange:NSMakeRange(0,newline.location)];
                            [buffer replaceBytesInRange:NSMakeRange(0,newline.location+1) withBytes:NULL length:0];
                            NSDictionary *message = [NSJSONSerialization JSONObjectWithData:line options:0 error:nil];
                            if (![message isKindOfClass:NSDictionary.class]) continue;
                            if ([message[@"kind"] isEqual:@"hosts"]) {
                                dispatch_async(dispatch_get_main_queue(), ^{ [self showHosts:message[@"hosts"]]; }); continue;
                            }
                            NSString *identifier = message[@"id"];
                            if (![message[@"kind"] isEqual:@"snapshot"] || ![identifier isKindOfClass:NSString.class] || ![[NSUUID alloc] initWithUUIDString:identifier]) continue;
                            NSString *status = [self receive:message];
                            NSData *reply = [NSJSONSerialization dataWithJSONObject:@{@"id":identifier,@"route":message[@"route"],@"status":status} options:0 error:nil];
                            [input.fileHandleForWriting writeData:reply];
                            [input.fileHandleForWriting writeData:[NSData dataWithBytes:"\n" length:1]];
                        }
                    }
                } @catch (NSException *exception) { /* SSH was interrupted; reconnect below. */ }
                [input.fileHandleForWriting closeFile];
                if (task.running) [task terminate];
                [task waitUntilExit];
            }
            self.connection = nil;
            dispatch_async(dispatch_get_main_queue(), ^{ [self setStatus:@"结构快照 · 未连接"]; });
            if (!self.stopping) [NSThread sleepForTimeInterval:5];
        }
    }
}
@end

int main(void) {
    @autoreleasepool {
        NSApplication *application = [NSApplication sharedApplication];
        SnapshotSaver *delegate = [SnapshotSaver new]; application.delegate = delegate;
        [application run];
    }
    return 0;
}
