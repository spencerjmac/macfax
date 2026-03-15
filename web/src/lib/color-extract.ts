/**
 * Extracts the dominant brand color from a team logo image using the Canvas API.
 *
 * Filters out near-white (lightness > 0.88) and near-grey (saturation < 0.12)
 * pixels before quantising the remaining colours into buckets. Returns the
 * average RGB value of the most populated bucket, or null on failure
 * (CORS block, load error, no saturated pixels found).
 */
export async function extractDominantColor(src: string): Promise<string | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = () => {
      try {
        const SIZE = 64;
        const canvas = document.createElement('canvas');
        canvas.width = SIZE;
        canvas.height = SIZE;
        const ctx = canvas.getContext('2d');
        if (!ctx) { resolve(null); return; }

        ctx.drawImage(img, 0, 0, SIZE, SIZE);

        let pixels: Uint8ClampedArray;
        try {
          pixels = ctx.getImageData(0, 0, SIZE, SIZE).data;
        } catch {
          // Canvas tainted by cross-origin image without CORS headers
          resolve(null);
          return;
        }

        interface Bucket { rSum: number; gSum: number; bSum: number; count: number }
        const buckets = new Map<string, Bucket>();

        for (let i = 0; i < pixels.length; i += 4) {
          const r = pixels[i], g = pixels[i + 1], b = pixels[i + 2], a = pixels[i + 3];
          if (a < 100) continue;  // transparent

          // Inline HSL lightness + saturation check
          const rN = r / 255, gN = g / 255, bN = b / 255;
          const cMax = Math.max(rN, gN, bN);
          const cMin = Math.min(rN, gN, bN);
          const l = (cMax + cMin) / 2;
          const d = cMax - cMin;
          const s = d === 0 ? 0 : (l > 0.5 ? d / (2 - cMax - cMin) : d / (cMax + cMin));

          if (l > 0.88) continue;  // near-white
          if (s < 0.12) continue;  // achromatic / grey

          // Quantise to ~8 buckets per channel (step of 32)
          const key = `${Math.round(r / 32) * 32},${Math.round(g / 32) * 32},${Math.round(b / 32) * 32}`;
          const entry = buckets.get(key);
          if (entry) {
            entry.rSum += r; entry.gSum += g; entry.bSum += b; entry.count++;
          } else {
            buckets.set(key, { rSum: r, gSum: g, bSum: b, count: 1 });
          }
        }

        if (buckets.size === 0) { resolve(null); return; }

        let best: Bucket | null = null;
        for (const entry of buckets.values()) {
          if (!best || entry.count > best.count) best = entry;
        }

        if (!best) { resolve(null); return; }

        const avgR = Math.round(best.rSum / best.count);
        const avgG = Math.round(best.gSum / best.count);
        const avgB = Math.round(best.bSum / best.count);
        resolve(`rgb(${avgR}, ${avgG}, ${avgB})`);
      } catch {
        resolve(null);
      }
    };

    img.onerror = () => resolve(null);
    img.src = src;
  });
}
