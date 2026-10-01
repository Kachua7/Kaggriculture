// OCR every PNG given on argv with macOS Vision (VNRecognizeTextRequest).
// Usage: swift analysis/ocr_vision.swift a.png b.png ...
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("== \(path): UNREADABLE"); continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { print("== \(path): OCR error \(error)"); continue }
    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    print("== \(URL(fileURLWithPath: path).lastPathComponent)")
    print(lines.joined(separator: "\n"))
    print()
}
