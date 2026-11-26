import AppKit
import Foundation

// Render the SVG source with macOS so every icon representation uses the same geometry.
let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    fputs("Usage: swift scripts/build_icon.swift source.svg output.iconset\n", stderr)
    exit(1)
}
let source = URL(fileURLWithPath: arguments[1])
let destination = URL(fileURLWithPath: arguments[2], isDirectory: true)
guard let image = NSImage(contentsOf: source) else {
    fputs("Cannot read SVG: \(source.path)\n", stderr)
    exit(1)
}
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
for points in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = points * scale
        guard let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
            isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0
        ), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
            fatalError("Cannot allocate \(pixels) px icon representation")
        }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        context.imageInterpolation = .high
        image.draw(
            in: NSRect(x: 0, y: 0, width: pixels, height: pixels),
            from: .zero, operation: .copy, fraction: 1
        )
        NSGraphicsContext.restoreGraphicsState()
        guard let data = bitmap.representation(using: .png, properties: [:]) else {
            fatalError("Cannot encode \(pixels) px icon representation")
        }
        let suffix = scale == 2 ? "@2x" : ""
        try data.write(to: destination.appendingPathComponent("icon_\(points)x\(points)\(suffix).png"))
    }
}
print("Rendered macOS icon set: \(destination.path)")
