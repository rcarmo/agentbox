---
applyTo: "**/*.swift"
---

# Swift macOS Application Instructions

## General Guidelines

- Target macOS 13+ and Swift 5.9+ for modern concurrency features
- Use Swift Package Manager for dependency management
- Prefer Foundation and AppKit/SwiftUI built-ins over external dependencies
- Build CLI-only executables with native windowing via NSPanel

## Concurrency Model

### MainActor Isolation

- Use `@MainActor` **only** for ViewModels and UI coordinators (AppDelegate)
- **Never** annotate long-running operations (file I/O, scanning) with `@MainActor`
- Heavy work runs on background threads; pass results to MainActor at the end

```swift
// WRONG: Blocks UI during scan
@MainActor
func scan(path: String) async -> DataNode? {
    // Expensive file I/O runs on main thread
}

// CORRECT: Background work, assign to ViewModel on MainActor
func scan(path: String) async -> DataNode? {
    let result = scanDirectory(url, depth: 0)  // Background thread
    return result  // Immutable Sendable struct, safe to pass
}

// In caller:
Task.detached {
    let tree = await scanner.scan(path: path)
    await MainActor.run {
        viewModel.root = tree  // Simple assignment
    }
}
```

### Immutable Sendable Data Structures

- Create **one immutable `Sendable` struct** for your data model
- Use `let` properties—immutable structs are automatically `Sendable`
- The ViewModel holds the data via `@Published`; no type conversion needed

```swift
/// Immutable data node - Sendable, works everywhere
struct DataNode: Sendable, Identifiable {
    let id: UUID
    let name: String
    let size: Int64
    let children: [DataNode]
}

/// ViewModel holds the Sendable data on MainActor
@MainActor
final class ViewModel: ObservableObject {
    @Published var root: DataNode?
    @Published var isLoading = false
}
```

**Why this works:**
- Immutable structs are `Sendable` by default (no mutable state)
- No conversion overhead—same type on background and UI threads
- SwiftUI efficiently diffs struct changes via `Equatable`

### Progressive Updates (Live UI During Processing)

If you need to update the UI while processing (e.g., show graph building in real-time), structures must be mutable and concurrency must be handled explicitly:

```swift
// Actor protects mutable state during building
actor TreeBuilder {
    private var root: MutableNode?
    
    func insert(_ item: Item) {
        root?.add(item)
    }
    
    func snapshot() -> DataNode {
        root?.toImmutable() ?? .empty
    }
}

// Throttled UI updates during processing
Task.detached {
    let builder = TreeBuilder()
    var count = 0
    
    for item in items {
        await builder.insert(item)
        count += 1
        
        // Update UI every 100 items
        if count % 100 == 0 {
            let snapshot = await builder.snapshot()
            await MainActor.run {
                viewModel.root = snapshot
            }
        }
    }
    
    // Final update
    let final = await builder.snapshot()
    await MainActor.run { viewModel.root = final }
}
```

**Rule of thumb**: Start with immutable batch updates. Add progressive updates only if UX requires seeing live progress.

### Task Management

- Use `Task.detached(priority: .userInitiated)` for CPU-intensive work
- Avoid `Progress` objects during scans—they add overhead on every file
- If progress indication is needed, use throttled callbacks (every 100+ items)

```swift
Task.detached(priority: .userInitiated) { [scanner] in
    let result = await scanner.scan(path: path)
    await MainActor.run {
        viewModel.root = result  // Direct assignment
    }
}
```

## SwiftUI Canvas Rendering

### Efficient Drawing

- Use SwiftUI `Canvas` for complex visualizations (charts, diagrams)
- Canvas provides GPU-accelerated immediate-mode drawing
- Avoid creating many SwiftUI views for data-heavy displays

```swift
Canvas { context, size in
    drawNode(
        context: context,
        node: root,
        center: center,
        startAngle: 0,
        endAngle: 360,
        depth: 1
    )
}
```

### Hit Testing

- Implement manual hit testing for Canvas-based interactions
- Cache geometry calculations where possible

```swift
private func hitTest(
    location: CGPoint,
    root: FileNode,
    center: CGPoint,
    ringWidth: CGFloat
) -> FileNode? {
    let dx = location.x - center.x
    let dy = location.y - center.y
    let distance = sqrt(dx * dx + dy * dy)
    let angle = atan2(dy, dx) * 180 / .pi
    // ... geometric hit detection
}
```

## Floating Window Pattern

### NSPanel for Utility Windows

- Use `NSPanel` with `utilityWindow` style for floating tools
- Configure as accessory app to hide dock icon

```swift
final class FloatingPanel: NSPanel {
    init(contentRect: NSRect, viewModel: ViewModel) {
        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, 
                        .utilityWindow, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isMovableByWindowBackground = true
        hidesOnDeactivate = false
        titlebarAppearsTransparent = true
    }
}

// In AppDelegate
NSApp.setActivationPolicy(.accessory)  // Hide dock icon
```

## FSEvents File Watching

### Proper FSEvents Setup

- Use absolute paths for FSEvents (required by the API)
- Include `kFSEventStreamCreateFlagFileEvents` for file-level notifications
- Implement debouncing to avoid rapid callbacks

```swift
let flags = UInt32(
    kFSEventStreamCreateFlagUseCFTypes |
    kFSEventStreamCreateFlagFileEvents |
    kFSEventStreamCreateFlagNoDefer |
    kFSEventStreamCreateFlagWatchRoot
)

// Type-safe callback handling
stream = FSEventStreamCreate(
    nil,
    { _, info, numEvents, eventPaths, eventFlags, _ in
        let pathsPtr = unsafeBitCast(eventPaths, to: NSArray.self)
        // Handle events with debounce
    },
    &context,
    pathsToWatch as CFArray,
    FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
    0.5,  // latency for batching
    flags
)

FSEventStreamSetDispatchQueue(stream, DispatchQueue.main)
FSEventStreamStart(stream)
```

## Animations

### SwiftUI Animation Patterns

- Use `.spring()` for interactive feedback
- Use `.easeInOut()` for state transitions
- Wrap state changes in `withAnimation {}`

```swift
// Interactive spring animation
withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
    viewModel.zoomTo(node)
}

// Smooth hover transitions
withAnimation(.easeOut(duration: 0.15)) {
    hoveredNode = newHovered
}

// Content transitions for numeric values
Text(formatBytes(size))
    .contentTransition(.numericText())
```

## Code Organization

### File Structure

```
Sources/
├── main.swift           # CLI entry, argument parsing
├── FileNode.swift       # Data model (UI-bound)
├── Scanner.swift        # Background scanning logic
├── Watcher.swift        # FSEvents wrapper
├── FloatingPanel.swift  # NSPanel + AppDelegate
└── MainView.swift       # SwiftUI view + Canvas
```

### MARK Comments

Organize code with clear sections:

```swift
// MARK: - Properties
// MARK: - Initialization
// MARK: - Public Methods
// MARK: - Private Methods
// MARK: - Subviews (for SwiftUI)
```

### Documentation

- Use `///` doc comments for public APIs
- Document parameters with `- Parameter:` or `- Parameters:`
- Explain complex algorithms in the doc comment

## CLI Pattern

### Argument Parsing

- Implement manual parsing for simple CLIs (no external dependencies)
- Support both short (`-d`) and long (`--depth`) flags
- Resolve paths with tilde expansion and standardization

```swift
private func parseArguments() -> (path: String, depth: Int)? {
    let args = Array(CommandLine.arguments.dropFirst())
    // ... parsing logic
    
    // Path resolution
    let resolved = (path as NSString).expandingTildeInPath
    let absolute = URL(fileURLWithPath: resolved).standardized.path
    return (absolute, depth)
}
```

### Application Bootstrap

- Use `DispatchQueue.main.async` to avoid race conditions with `NSApplication.run()`

```swift
let app = NSApplication.shared
let delegate = AppDelegate()
delegate.watchPath = path
app.delegate = delegate

DispatchQueue.main.async {
    delegate.applicationDidFinishLaunching(
        Notification(name: NSApplication.didFinishLaunchingNotification)
    )
}

app.run()
```

## Error Handling

- Use `guard` for early returns with invalid state
- Handle file system errors gracefully (permissions, missing files)
- Provide clear error messages to CLI users

```swift
guard FileManager.default.fileExists(atPath: path, isDirectory: &isDir),
      isDir.boolValue else {
    print("Error: '\(path)' is not a valid directory")
    return nil
}
```

## Performance Tips

1. **Avoid Progress objects** during file scans - use throttled callbacks if needed
2. **Keep @MainActor scope minimal** - only for UI updates
3. **Use Sendable structs** for data transfer between threads
4. **Batch FSEvents** with latency parameter to reduce callback frequency
5. **Sort data once** after scanning, not during tree traversal
