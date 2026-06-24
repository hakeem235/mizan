// Client-side OCR via Tesseract (Arabic + English). Loaded dynamically so the
// ~heavy wasm bundle stays out of the initial page load and off the server.
export async function runOcr(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  const { default: Tesseract } = await import("tesseract.js");
  const result = await Tesseract.recognize(file, "ara+eng", {
    logger: (m: { status: string; progress: number }) => {
      if (m.status === "recognizing text" && onProgress) {
        onProgress(Math.round(m.progress * 100));
      }
    },
  });
  return result.data.text;
}
