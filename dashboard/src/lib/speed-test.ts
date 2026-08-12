/** Browser-side Cloudflare download/upload probes with live Mbps callbacks. */

export type SpeedProgress = {
  phase: "download" | "upload";
  mbps: number;
  loadedBytes: number;
  totalBytes: number;
};

const DOWN_URL = "https://speed.cloudflare.com/__down";
const UP_URL = "https://speed.cloudflare.com/__up";

/** ~25 MiB download for a fuller live test. */
export const LIVE_DOWNLOAD_BYTES = 25_000_000;
/** ~10 MiB upload. */
export const LIVE_UPLOAD_BYTES = 10_000_000;

function mbpsFrom(bytes: number, elapsedMs: number): number {
  const elapsed = elapsedMs / 1000;
  if (elapsed <= 0 || bytes <= 0) return 0;
  return (bytes * 8) / (elapsed * 1_000_000);
}

export async function measureLiveDownload(
  totalBytes: number,
  onProgress: (p: SpeedProgress) => void,
  signal?: AbortSignal,
): Promise<number> {
  const url = `${DOWN_URL}?bytes=${totalBytes}&measId=${Date.now()}`;
  const start = performance.now();
  const res = await fetch(url, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  if (!res.body) throw new Error("Download stream unavailable");

  const reader = res.body.getReader();
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    loaded += value.byteLength;
    onProgress({
      phase: "download",
      mbps: mbpsFrom(loaded, performance.now() - start),
      loadedBytes: loaded,
      totalBytes,
    });
  }
  return mbpsFrom(loaded, performance.now() - start);
}

function buildUploadBody(totalBytes: number): Blob {
  const chunk = new Uint8Array(64 * 1024);
  crypto.getRandomValues(chunk);
  const parts: BlobPart[] = [];
  let remaining = totalBytes;
  while (remaining > 0) {
    const size = Math.min(remaining, chunk.byteLength);
    parts.push(chunk.subarray(0, size));
    remaining -= size;
  }
  return new Blob(parts);
}

export async function measureLiveUpload(
  totalBytes: number,
  onProgress: (p: SpeedProgress) => void,
  signal?: AbortSignal,
): Promise<number> {
  const url = `${UP_URL}?measId=${Date.now()}`;
  const body = buildUploadBody(totalBytes);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const start = performance.now();

    const onAbort = () => {
      xhr.abort();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    xhr.open("POST", url);
    xhr.upload.onprogress = (event) => {
      const loaded = event.loaded;
      onProgress({
        phase: "upload",
        mbps: mbpsFrom(loaded, performance.now() - start),
        loadedBytes: loaded,
        totalBytes,
      });
    };
    xhr.onload = () => {
      signal?.removeEventListener("abort", onAbort);
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(mbpsFrom(totalBytes, performance.now() - start));
      } else {
        reject(new Error(`Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new Error("Upload failed"));
    };
    xhr.onabort = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    xhr.send(body);
  });
}

export async function runLiveSpeedTest(
  onProgress: (p: SpeedProgress) => void,
  signal?: AbortSignal,
): Promise<{ downloadMbps: number; uploadMbps: number }> {
  const downloadMbps = await measureLiveDownload(
    LIVE_DOWNLOAD_BYTES,
    onProgress,
    signal,
  );
  const uploadMbps = await measureLiveUpload(
    LIVE_UPLOAD_BYTES,
    onProgress,
    signal,
  );
  return { downloadMbps, uploadMbps };
}
