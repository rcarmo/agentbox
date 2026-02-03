# SKILL: Building Native macOS CLI Apps with SwiftUI Visualization

This document captures design patterns, architectural decisions, and lessons learned for building lightweight native macOS CLI tools with rich visual interfaces—without the overhead of Electron or web technologies.

## When to Use This Pattern

This approach is ideal when you need:

- **CLI-first tools** with optional/auxiliary GUI
- **Floating utility windows** (inspectors, monitors, dashboards)
- **Real-time data visualization** with live updates
- **Minimal footprint** (~200KB binary, ~15MB RAM)
- **Native macOS feel** (animations, system integration)

### Example Use Cases

| Type | Examples |
|------|----------|
| **File system tools** | Disk usage, file watchers, backup monitors |
| **Developer tools** | Log viewers, profilers, build monitors |
| **System monitors** | CPU/memory graphs, network traffic, process lists |
| **Data dashboards** | Metrics, time series, real-time feeds |
| **Quick-look tools** | JSON viewers, image inspectors, diff tools |

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│  main.swift                                                 │
│  └── CLI parsing, app bootstrap                             │
├─────────────────────────────────────────────────────────────┤
│  AppDelegate + FloatingPanel                                │
│  └── @MainActor: Window management, coordination            │
├─────────────────────────────────────────────────────────────┤
│  MainView (SwiftUI)                                         │
│  └── @MainActor: Canvas rendering, user interactions        │
├─────────────────────────────────────────────────────────────┤
│  DataProcessor / Scanner / Fetcher                          │
│  └── Sendable: Background data acquisition                  │
├─────────────────────────────────────────────────────────────┤
│  Watcher / Listener (optional)                              │
│  └── Event source: File system, network, timer              │
├─────────────────────────────────────────────────────────────┤
│  DataModel                                                  │
│  └── @MainActor: UI-bound observable state                  │
└─────────────────────────────────────────────────────────────┘
```

### Why Native Over Electron?

| Metric | Native Swift | Electron |
|--------|--------------|----------|
| Binary size | ~200 KB | 150+ MB |
| Memory (idle) | ~15 MB | 100+ MB |
| Startup time | < 100ms | 1-3s |
| CPU (idle) | Near zero | Background JS |
| System integration | Full | Limited |

## Key Patterns

### Pattern 1: Immutable Sendable Data Model (Batch Updates)

**Use when**: You process all data first, then display the result.

**Solution**: Create **one immutable Sendable struct** for data. The ViewModel holds it via `@Published`—no type conversion needed.

```swift
// Immutable, Sendable data structure - works everywhere
struct DataNode: Sendable, Identifiable {
    let id: String
    let value: Double
    let children: [DataNode]
}

// ViewModel holds the data on MainActor
@MainActor
final class ViewModel: ObservableObject {
    @Published var root: DataNode?
    @Published var isLoading = false
}
```

**Workflow**:

1. Process data on background thread, producing immutable `Sendable` tree
2. Pass the tree to ViewModel on MainActor (no conversion, just assignment)

```swift
Task.detached(priority: .userInitiated) {
    let tree = await buildTree()  // Background work
    await MainActor.run {
        viewModel.root = tree  // Simple assignment
    }
}
```

**Why immutable structs?**

- `Sendable` by default (no mutable state to race on)
- No conversion overhead—same type everywhere
- SwiftUI efficiently diffs struct changes
- Simpler mental model: data flows one way

### Pattern 1b: Mutable Data Model (Progressive Updates)

**Use when**: You want the UI to update live as data comes in.

If you need to update the graph progressively during processing, the structures must be mutable and you must handle concurrency explicitly.

**Option A: Actor-isolated mutable state**

```swift
// Actor protects mutable state
actor DataBuilder {
    private var root: MutableNode?
    
    func addItem(_ item: Item) {
        // Safe mutation inside actor
        root?.insert(item)
    }
    
    func snapshot() -> DataNode {
        // Return immutable copy for UI
        root?.toImmutable() ?? DataNode.empty
    }
}

// Periodic UI updates
Task.detached {
    for await batch in stream {
        await builder.addItem(batch)
        
        // Throttled UI update
        if shouldUpdate {
            let snapshot = await builder.snapshot()
            await MainActor.run {
                viewModel.root = snapshot
            }
        }
    }
}
```

**Option B: AsyncStream with throttled updates**

```swift
// Stream intermediate results
func buildTreeWithProgress() -> AsyncStream<DataNode> {
    AsyncStream { continuation in
        Task.detached {
            var tree = MutableTree()
            var count = 0
            
            for item in items {
                tree.insert(item)
                count += 1
                
                // Emit snapshot every N items
                if count % 100 == 0 {
                    continuation.yield(tree.toImmutable())
                }
            }
            
            continuation.yield(tree.toImmutable())
            continuation.finish()
        }
    }
}

// Consume on MainActor
Task { @MainActor in
    for await snapshot in buildTreeWithProgress() {
        viewModel.root = snapshot
    }
}
```

**Trade-offs**:

| Approach | Pros | Cons |
| -------- | ---- | ---- |
| Immutable (batch) | Simple, no races, efficient | No live updates |
| Actor + snapshots | Live updates, safe | Snapshot overhead |
| AsyncStream | Reactive, composable | More complex setup |

**Rule of thumb**: Start with immutable. Add progressive updates only if UX requires it.

### Pattern 2: Floating Utility Window

```swift
final class FloatingPanel: NSPanel {
    init(contentRect: NSRect, rootView: some View) {
        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable,
                        .utilityWindow, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        
        // Floating behavior
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isFloatingPanel = true
        hidesOnDeactivate = false
        
        // Appearance
        titlebarAppearsTransparent = true
        titleVisibility = .hidden
        isMovableByWindowBackground = true
        
        // Content
        contentView = NSHostingView(rootView: rootView)
    }
}

// Hide dock icon (accessory app)
NSApp.setActivationPolicy(.accessory)
```

### Pattern 3: Canvas-Based Visualization

For data-heavy visualizations (charts, graphs, diagrams), use `Canvas`:

```swift
struct DataVisualization: View {
    @ObservedObject var viewModel: ViewModel
    @State private var hoveredItem: Item?
    
    var body: some View {
        Canvas { context, size in
            // GPU-accelerated immediate-mode drawing
            for item in viewModel.items {
                drawItem(context: context, item: item, size: size)
            }
        }
        .onContinuousHover { phase in
            // Manual hit-testing
            hoveredItem = hitTest(phase, viewModel.items)
        }
        .onTapGesture { location in
            // Handle clicks with geometry
        }
    }
}
```

**Why Canvas over Views?**
- O(1) view count regardless of data size
- No view diffing overhead
- Direct control over z-order and clipping
- Better for 1000+ items

### Pattern 4: Background Task Management

```swift
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var processor: DataProcessor?
    
    func startProcessing() {
        viewModel.setLoading()
        
        let config = currentConfig  // Capture for closure
        
        Task.detached(priority: .userInitiated) { [processor] in
            guard let result = await processor?.process(config) else { return }
            
            await MainActor.run { [weak self] in
                self?.viewModel.update(result)
            }
        }
    }
}
```

### Pattern 5: Event Source with Debouncing

For file system, network, or other event sources:

```swift
final class EventWatcher {
    private var pendingWork: DispatchWorkItem?
    private let debounceInterval: TimeInterval
    private let callback: @Sendable () -> Void
    
    func handleEvent() {
        pendingWork?.cancel()
        pendingWork = DispatchWorkItem { [weak self] in
            self?.callback()
        }
        DispatchQueue.main.asyncAfter(
            deadline: .now() + debounceInterval,
            execute: pendingWork!
        )
    }
}
```

### Pattern 6: CLI Bootstrap with GUI

```swift
// main.swift
import AppKit

func main() {
    // 1. Parse CLI arguments
    guard let config = parseArguments() else {
        exit(1)
    }
    
    // 2. Set up app
    let app = NSApplication.shared
    let delegate = AppDelegate()
    delegate.config = config
    app.delegate = delegate
    
    // 3. Bootstrap window AFTER run loop starts
    DispatchQueue.main.async {
        delegate.applicationDidFinishLaunching(
            Notification(name: NSApplication.didFinishLaunchingNotification)
        )
    }
    
    // 4. Run app
    app.run()
}

main()
```

## Lessons Learned

### 1. Avoid Progress Objects in Hot Paths

```swift
// SLOW: Progress KVO fires on every update
let progress = Progress(totalUnitCount: 10000)
for item in items {
    progress.completedUnitCount += 1  // Expensive!
}

// FAST: Throttle or skip entirely
var count = 0
for item in items {
    count += 1
    if count % 100 == 0 {
        await reportProgress(count)
    }
}
```

### 2. Minimize @MainActor Scope

```swift
// WRONG: Entire processor blocks UI
@MainActor
final class DataProcessor { ... }

// CORRECT: Only conversion is on MainActor
final class DataProcessor: Sendable {
    func process() async -> DisplayData {
        let raw = heavyWork()  // Background
        return await MainActor.run { convert(raw) }  // UI
    }
}
```

### 3. Resolve Paths to Absolute

File system APIs often require absolute paths:

```swift
func resolvePath(_ input: String) -> String {
    let expanded = (input as NSString).expandingTildeInPath
    return URL(fileURLWithPath: expanded).standardized.path
}
```

### 4. Color Space Conversion

Web colors (HSL) vs. Swift colors (HSB):

```swift
// HSL to HSB approximation for vibrant colors
// HSL: s=70%, l=60% → HSB: s=50-80%, b=75-95%
Color(hue: h, saturation: 0.65, brightness: 0.85)
```

### 5. Spring Animations for Polish

```swift
// Interactive feedback
withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
    viewModel.selectItem(item)
}

// Smooth tracking
.animation(.interactiveSpring(response: 0.15), value: mouseLocation)

// Numeric transitions
Text(formattedValue)
    .contentTransition(.numericText())
```

## Project Structure

```
Sources/
├── main.swift              # CLI entry point
├── Config.swift            # Configuration types
├── FloatingPanel.swift     # Window + AppDelegate
├── MainView.swift          # SwiftUI view
├── ViewModel.swift         # Observable state
├── DataModel.swift         # Sendable data types
├── Processor.swift         # Background work
└── Watcher.swift           # Event source (optional)

Package.swift               # Swift Package Manager
```

## Performance Guidelines

| Goal | Approach |
|------|----------|
| Fast startup | Minimal imports, defer heavy init |
| Responsive UI | Background `Task.detached`, two-type pattern |
| Low memory | Stream data, avoid caching everything |
| Smooth animations | 60fps Canvas, spring physics |
| Small binary | No external dependencies |

## Checklist for New Projects

- [ ] Define CLI argument structure
- [ ] Create `Sendable` data model for background work
- [ ] Create `@MainActor` model for UI binding
- [ ] Implement `FloatingPanel` with desired style
- [ ] Use `Canvas` for complex visualizations
- [ ] Add debouncing for event sources
- [ ] Test with large datasets
- [ ] Profile with Instruments for bottlenecks

## Summary

The key insight: **SwiftUI Canvas + NSPanel + proper concurrency = powerful native tools with minimal code.**

This pattern delivers:
- Native performance and feel
- Tiny resource footprint
- CLI-first flexibility
- Rich visualization capabilities

All without the complexity and overhead of web-based alternatives.
