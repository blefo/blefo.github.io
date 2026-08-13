import Foundation
import AppKit
import Vision
import ImageIO
import CoreGraphics

guard CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: swift make_face.swift <photo> <outdir>\n".utf8))
    exit(1)
}

let inputPath = CommandLine.arguments[1]
let outputDir = CommandLine.arguments[2]
try? FileManager.default.createDirectory(atPath: outputDir, withIntermediateDirectories: true)

guard
    let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: inputPath) as CFURL, nil),
    let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    FileHandle.standardError.write(Data("failed to load image\n".utf8))
    exit(1)
}

let width = cgImage.width
let height = cgImage.height

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let segmentation = VNGeneratePersonSegmentationRequest()
segmentation.qualityLevel = .accurate
let faceRequest = VNDetectFaceLandmarksRequest()

do {
    try handler.perform([segmentation, faceRequest])
} catch {
    FileHandle.standardError.write(Data("vision failed: \(error)\n".utf8))
    exit(1)
}

guard let maskBuffer = segmentation.results?.first?.pixelBuffer else {
    FileHandle.standardError.write(Data("person segmentation produced no mask\n".utf8))
    exit(1)
}

guard let face = faceRequest.results?.first else {
    FileHandle.standardError.write(Data("no face detected\n".utf8))
    exit(1)
}

CVPixelBufferLockBaseAddress(maskBuffer, .readOnly)
defer { CVPixelBufferUnlockBaseAddress(maskBuffer, .readOnly) }

let maskWidth = CVPixelBufferGetWidth(maskBuffer)
let maskHeight = CVPixelBufferGetHeight(maskBuffer)
let maskBytesPerRow = CVPixelBufferGetBytesPerRow(maskBuffer)
let maskFormat = CVPixelBufferGetPixelFormatType(maskBuffer)

guard let maskBase = CVPixelBufferGetBaseAddress(maskBuffer) else {
    FileHandle.standardError.write(Data("mask has no base address\n".utf8))
    exit(1)
}

var mask = [UInt8](repeating: 0, count: maskWidth * maskHeight)
switch maskFormat {
case kCVPixelFormatType_OneComponent8:
    for y in 0..<maskHeight {
        memcpy(&mask[y * maskWidth], maskBase.advanced(by: y * maskBytesPerRow), maskWidth)
    }
default:
    for y in 0..<maskHeight {
        for x in 0..<maskWidth {
            mask[y * maskWidth + x] = maskBase.advanced(by: y * maskBytesPerRow + x * 4).load(as: UInt8.self)
        }
    }
}

var sourcePixels = [UInt8](repeating: 0, count: width * height * 4)
let sourceReady: Bool = sourcePixels.withUnsafeMutableBytes { bytes in
    guard
        let context = CGContext(
            data: bytes.baseAddress,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    else {
        return false
    }
    context.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
    return true
}

guard sourceReady else {
    FileHandle.standardError.write(Data("failed to draw source pixels\n".utf8))
    exit(1)
}

let box = face.boundingBox
let faceX = box.origin.x * CGFloat(width)
let faceY = (1 - box.origin.y - box.height) * CGFloat(height)
let faceW = box.width * CGFloat(width)
let faceH = box.height * CGFloat(height)

let expandLeft = faceW * 0.16
let expandRight = faceW * 0.16
let expandTop = faceH * 0.44
let expandBottom = faceH * 0.08

let cropX0 = max(0, Int((faceX - expandLeft).rounded(.down)))
let cropY0 = max(0, Int((faceY - expandTop).rounded(.down)))
let cropX1 = min(width, Int((faceX + faceW + expandRight).rounded(.up)))
let cropY1 = min(height, Int((faceY + faceH + expandBottom).rounded(.up)))
let cropW = cropX1 - cropX0
let cropH = cropY1 - cropY0

func normalizedEyePoint(_ region: VNFaceLandmarkRegion2D?) -> CGPoint? {
    region?.normalizedPoints.first
}

func imagePoint(_ normalized: CGPoint) -> CGPoint {
    let x = faceX + normalized.x * faceW
    let yTop = (1 - (box.origin.y + normalized.y * box.height)) * CGFloat(height)
    return CGPoint(x: x - CGFloat(cropX0), y: yTop - CGFloat(cropY0))
}

let leftEye = imagePoint(normalizedEyePoint(face.landmarks?.leftEye) ?? CGPoint(x: 0.35, y: 0.42))
let rightEye = imagePoint(normalizedEyePoint(face.landmarks?.rightEye) ?? CGPoint(x: 0.65, y: 0.42))

var output = [UInt8](repeating: 0, count: cropW * cropH * 4)
for dy in 0..<cropH {
    let sourceY = cropY0 + dy
    let maskY = min(maskHeight - 1, sourceY * maskHeight / height)
    for dx in 0..<cropW {
        let sourceX = cropX0 + dx
        let maskX = min(maskWidth - 1, sourceX * maskWidth / width)
        guard mask[maskY * maskWidth + maskX] > 88 else { continue }

        let sourceIndex = (sourceY * width + sourceX) * 4
        let outputIndex = (dy * cropW + dx) * 4
        output[outputIndex] = sourcePixels[sourceIndex]
        output[outputIndex + 1] = sourcePixels[sourceIndex + 1]
        output[outputIndex + 2] = sourcePixels[sourceIndex + 2]
        output[outputIndex + 3] = 255
    }
}

let outputURL = URL(fileURLWithPath: outputDir).appendingPathComponent("face-crop.png")
let pngContext = CGContext(
    data: &output,
    width: cropW,
    height: cropH,
    bitsPerComponent: 8,
    bytesPerRow: cropW * 4,
    space: CGColorSpaceCreateDeviceRGB(),
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
)!
let pngImage = pngContext.makeImage()!
if let destination = CGImageDestinationCreateWithURL(outputURL as CFURL, "public.png" as CFString, 1, nil) {
    CGImageDestinationAddImage(destination, pngImage, nil)
    CGImageDestinationFinalize(destination)
}

let metadata: [String: Any] = [
    "image": ["width": cropW, "height": cropH],
    "eyes": [
        ["name": "left", "x": leftEye.x, "y": leftEye.y],
        ["name": "right", "x": rightEye.x, "y": rightEye.y]
    ]
]

let jsonURL = URL(fileURLWithPath: outputDir).appendingPathComponent("face-meta.json")
let jsonData = try JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys])
try jsonData.write(to: jsonURL)

print("crop=\(cropW)x\(cropH) mask=\(maskWidth)x\(maskHeight)")
