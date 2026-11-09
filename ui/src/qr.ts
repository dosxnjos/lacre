// QR code as inline SVG, generated locally (no network).
import QRCode from "qrcode";

const cache = new Map<string, Promise<string>>();

export function qrSvg(text: string): Promise<string> {
  let p = cache.get(text);
  if (!p) {
    p = QRCode.toString(text, {
      type: "svg",
      errorCorrectionLevel: "M",
      margin: 1,
      color: { dark: "#000000", light: "#ffffff" },
    });
    cache.set(text, p);
  }
  return p;
}
