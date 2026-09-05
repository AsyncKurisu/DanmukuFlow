import type {
  BatchExportResult,
  ConflictPolicy,
  DownloadResult,
  ExportResult,
  ResolveResponse,
} from "../types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type DirectoryKind = "output" | "video";

export interface BilibiliSettings {
  configured: boolean;
  cookie_count: number;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  reason: string | null;

  constructor(status: number, detail: string, reason: string | null = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.reason = reason;
  }
}

function url(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function getBilibiliSettings(): Promise<BilibiliSettings> {
  const response = await fetch(url("/api/settings/bilibili"));
  return (await parseResponse<BilibiliSettings>(response)) as BilibiliSettings;
}

export async function saveBilibiliCookie(cookie: string): Promise<BilibiliSettings> {
  const response = await fetch(url("/api/settings/bilibili"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cookie }),
  });
  return (await parseResponse<BilibiliSettings>(response)) as BilibiliSettings;
}

function contentDispositionFilename(value: string | null): string {
  if (!value) {
    return "danmukuflow-download.ass";
  }

  const utf8 = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].replace(/^["']|["']$/g, ""));
    } catch {
      // Use the ASCII fallback when the server sends malformed quoting.
    }
  }

  const plain = value.match(/filename="?([^";]+)"?/i);
  return plain?.[1] ?? "danmukuflow-download.ass";
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let detail = `请求失败（HTTP ${response.status}）`;
  let reason: string | null = null;

  try {
    const payload = (await response.json()) as {
      detail?: unknown;
      reason?: unknown;
    };
    if (Array.isArray(payload.detail)) {
      detail = payload.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String(item.msg);
          }
          return JSON.stringify(item);
        })
        .join("; ");
    } else if (payload.detail != null) {
      detail = String(payload.detail);
    }
    if (payload.reason != null) {
      reason = String(payload.reason);
    }
  } catch {
    const text = await response.text().catch(() => "");
    if (text) detail = text;
  }

  return new ApiError(response.status, detail, reason);
}

async function parseResponse<T>(response: Response): Promise<T | DownloadResult> {
  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return {
    blob: await response.blob(),
    filename: contentDispositionFilename(response.headers.get("content-disposition")),
    mediaType: contentType,
    partial: response.headers.get("x-danmukuflow-partial") === "true",
    failedCount: Number(response.headers.get("x-danmukuflow-failed-count") ?? 0),
  };
}

export function isDownloadResult(
  value: ExportResult | BatchExportResult | DownloadResult,
): value is DownloadResult {
  return "blob" in value && value.blob instanceof Blob;
}

export async function resolveInput(
  input: string,
  page?: number,
): Promise<ResolveResponse> {
  const response = await fetch(url("/api/resolve"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, ...(page ? { page } : {}) }),
  });
  return (await parseResponse<ResolveResponse>(response)) as ResolveResponse;
}

export async function selectDirectory(kind: DirectoryKind): Promise<string | null> {
  const response = await fetch(url("/api/directories/select"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind }),
  });
  if (response.status === 204) {
    return null;
  }
  const payload = (await parseResponse<{ path: string }>(response)) as {
    path: string;
  };
  return payload.path;
}

export interface SingleExportOptions {
  input?: string;
  page?: number;
  xmlFile?: File | null;
  outputDir?: string;
  namingTemplate?: string;
  conflictPolicy: ConflictPolicy;
}

export async function exportSingle(
  options: SingleExportOptions,
): Promise<ExportResult | DownloadResult> {
  let response: Response;

  if (options.xmlFile) {
    const form = new FormData();
    form.append("xml_file", options.xmlFile);
    if (options.outputDir) form.append("output_dir", options.outputDir);
    if (options.namingTemplate) form.append("naming_template", options.namingTemplate);
    form.append("conflict_policy", options.conflictPolicy);
    form.append("render_config", JSON.stringify({}));
    response = await fetch(url("/api/exports"), {
      method: "POST",
      body: form,
    });
  } else {
    response = await fetch(url("/api/exports"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input: options.input,
        ...(options.page ? { page: options.page } : {}),
        ...(options.outputDir ? { output_dir: options.outputDir } : {}),
        ...(options.namingTemplate ? { naming_template: options.namingTemplate } : {}),
        conflict_policy: options.conflictPolicy,
        render_config: {},
      }),
    });
  }

  return parseResponse<ExportResult>(response) as Promise<
    ExportResult | DownloadResult
  >;
}

export interface BatchExportOptions {
  seasonId: number;
  selectedEpisodeIds: number[];
  videoDir?: string;
  outputDir?: string;
  namingTemplate?: string;
  conflictPolicy: ConflictPolicy;
  concurrency: number;
}

export async function exportBatch(
  options: BatchExportOptions,
): Promise<BatchExportResult | DownloadResult> {
  const body = {
    season_id: options.seasonId,
    selected_episode_ids: options.selectedEpisodeIds,
    ...(options.videoDir ? { video_dir: options.videoDir } : {}),
    ...(options.outputDir ? { output_dir: options.outputDir } : {}),
    ...(options.namingTemplate ? { naming_template: options.namingTemplate } : {}),
    conflict_policy: options.conflictPolicy,
    concurrency: options.concurrency,
    render_config: {},
  };
  const response = await fetch(url("/api/batch-exports"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse<BatchExportResult>(response) as Promise<
    BatchExportResult | DownloadResult
  >;
}

export function saveDownload(download: DownloadResult): void {
  const href = URL.createObjectURL(download.blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = download.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  // Keep the URL alive until the browser has taken ownership of the download.
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}
