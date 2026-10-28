#import <Cocoa/Cocoa.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>


@interface SnapshotSaver : NSObject <NSApplicationDelegate>
@property NSStatusItem *statusItem;
@property NSTask *connection;
@property BOOL stopping;
@end

@implementation SnapshotSaver
- (void)setStatus:(NSString *)title {
    self.statusItem.button.title = title;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    self.statusItem = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
    [self setStatus:@"结构快照 · 连接中"];
    NSMenu *menu = [NSMenu new];
    NSMenuItem *quit = [[NSMenuItem alloc] initWithTitle:@"退出保存助手" action:@selector(quitHelper:) keyEquivalent:@""];
    quit.target = self; [menu addItem:quit]; self.statusItem.menu = menu;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ [self watch]; });
}
- (void)quitHelper:(id)sender { self.stopping = YES; [self.connection terminate]; [NSApp terminate:nil]; }
- (void)applicationWillTerminate:(NSNotification *)notification { self.stopping = YES; [self.connection terminate]; }
- (NSString *)save:(NSData *)data name:(NSString *)name {
    [NSApp activateIgnoringOtherApps:YES];
    NSSavePanel *panel = [NSSavePanel savePanel];
    panel.title = @"保存结构图像或动画"; panel.nameFieldStringValue = name;
    panel.allowedContentTypes = @[[UTType typeWithFilenameExtension:name.pathExtension]];
    panel.canCreateDirectories = YES;
    panel.directoryURL = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    if ([panel runModal] != NSModalResponseOK) return @"cancelled";
    NSError *error = nil;
    if (![data writeToURL:panel.URL options:NSDataWritingAtomic error:&error]) {
        NSAlert *alert = [NSAlert new]; alert.messageText = @"保存失败"; alert.informativeText = error.localizedDescription;
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
    dispatch_sync(dispatch_get_main_queue(), ^{ result = [self save:image name:name]; });
    return result;
}
- (void)watch {
    while (!self.stopping) {
        @autoreleasepool {
            NSTask *task = [NSTask new]; NSPipe *output = [NSPipe pipe]; NSPipe *input = [NSPipe pipe];
            self.connection = task;
            task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/ssh"];
            task.arguments = @[@"-o", @"BatchMode=yes", @"-o", @"ConnectTimeout=15", @"-o", @"ServerAliveInterval=15", @"-o", @"ServerAliveCountMax=2", @"nd3",
                               @"python3 -u /data/home/yangl/.local/share/codex-structure-viewer/plugin/snapshot_queue.py"];
            task.standardOutput = output; task.standardInput = input;
            task.standardError = [NSFileHandle fileHandleWithNullDevice];
            if ([task launchAndReturnError:nil]) {
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
                            if ([message[@"kind"] isEqual:@"ready"]) {
                                dispatch_async(dispatch_get_main_queue(), ^{ [self setStatus:@"结构快照 · nd3"]; }); continue;
                            }
                            NSString *identifier = message[@"id"];
                            if (![message[@"kind"] isEqual:@"snapshot"] || ![identifier isKindOfClass:NSString.class] || ![[NSUUID alloc] initWithUUIDString:identifier]) continue;
                            NSString *status = [self receive:message];
                            NSData *reply = [NSJSONSerialization dataWithJSONObject:@{@"id":identifier,@"status":status} options:0 error:nil];
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
