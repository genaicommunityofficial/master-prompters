import jsQR from 'jsqr'

async function decodeWithBarcodeDetector(file: File): Promise<string | null> {
  const Detector = (window as unknown as { BarcodeDetector?: new (opts: { formats: string[] }) => { detect: (src: ImageBitmap) => Promise<Array<{ rawValue?: string }>> } }).BarcodeDetector
  if (!Detector) return null
  try {
    const detector = new Detector({ formats: ['qr_code'] })
    const bitmap = await createImageBitmap(file)
    const codes = await detector.detect(bitmap)
    bitmap.close()
    const value = codes[0]?.rawValue?.trim()
    return value || null
  } catch {
    return null
  }
}

function drawToCanvas(bitmap: ImageBitmap, maxEdge = 1600): ImageData {
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const width = Math.max(1, Math.round(bitmap.width * scale))
  const height = Math.max(1, Math.round(bitmap.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not read that image.')
  ctx.drawImage(bitmap, 0, 0, width, height)
  return ctx.getImageData(0, 0, width, height)
}

export async function decodeQrFromFile(file: File): Promise<string> {
  const native = await decodeWithBarcodeDetector(file)
  if (native) return native

  const bitmap = await createImageBitmap(file)
  try {
    const imageData = drawToCanvas(bitmap)
    const result = jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: 'attemptBoth',
    })
    const value = result?.data?.trim()
    if (!value) {
      throw new Error('Could not read a QR code from that image. Try a clearer photo, or paste the QR message.')
    }
    return value
  } finally {
    bitmap.close()
  }
}
