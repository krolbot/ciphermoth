#import <AppKit/AppKit.h>
// Observers live for the application lifetime. Notifications carry no data into Rust.
void cm_observe_lock(void (*lock)(void)) {
    NSNotificationCenter *workspace = NSWorkspace.sharedWorkspace.notificationCenter;
    for (NSString *name in @[NSWorkspaceWillSleepNotification,
                            NSWorkspaceScreensDidSleepNotification,
                            NSWorkspaceSessionDidResignActiveNotification]) {
        [workspace addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification * _Nonnull note) { (void)note; lock(); }];
    }
    // This system notification is not a documented API. Screen sleep and
    // session resignation above are supported fallbacks; it can only lock.
    [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsLocked"
        object:nil queue:nil usingBlock:^(NSNotification * _Nonnull note) { (void)note; lock(); }];
}
long cm_clipboard_generation(void) {
    @autoreleasepool { return NSPasteboard.generalPasteboard.changeCount; }
}

#if CM_QA
void cm_test_sleep_notification(void) {
    [NSWorkspace.sharedWorkspace.notificationCenter postNotificationName:NSWorkspaceWillSleepNotification object:NSWorkspace.sharedWorkspace];
}
#endif
