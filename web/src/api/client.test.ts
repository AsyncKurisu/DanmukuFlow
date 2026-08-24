import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  exportBatch,
  exportSingle,
  isDownloadResult,
  resolveInput,
  saveDownload,
  selectDirectory,
} from "./client";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("web API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submits BV page during resolve", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ kind: "bv", video: {} }));

    await resolveInput("BV123", 2);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ input: "BV123", page: 2 });
  });

  it("submits real selected episode ids for batch export", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ total: 2 }));

    await exportBatch({
      seasonId: 7,
      selectedEpisodeIds: [101, 9007],
      conflictPolicy: "skip",
      concurrency: 1,
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      season_id: 7,
      selected_episode_ids: [101, 9007],
      conflict_policy: "skip",
      concurrency: 1,
    });
  });

  it("requests a native directory and returns its path", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse({ path: "C:\\Users\\Kurisu\\Desktop\\test_ss" }),
      );

    await expect(selectDirectory("output")).resolves.toBe(
      "C:\\Users\\Kurisu\\Desktop\\test_ss",
    );

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ kind: "output" });
  });

  it("returns null when the native directory picker is cancelled", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
    } as Response);

    await expect(selectDirectory("video")).resolves.toBeNull();
  });

  it("uses multipart upload for XML and recognizes attachment responses", async () => {
    const response = {
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": "text/plain; charset=utf-8",
        "content-disposition": 'attachment; filename="input.ass"',
      }),
      blob: async () => new Blob(["ass"]),
    } as Response;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
    const file = new File(["<i />"], "input.xml", { type: "text/xml" });

    const result = await exportSingle({
      xmlFile: file,
      conflictPolicy: "overwrite",
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(isDownloadResult(result)).toBe(true);
    if (isDownloadResult(result)) {
      expect(result.filename).toBe("input.ass");
    }
  });

  it("reads partial batch download headers", async () => {
    const response = {
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": "application/zip",
        "content-disposition": 'attachment; filename="season-7.zip"',
        "x-danmukuflow-partial": "true",
        "x-danmukuflow-failed-count": "2",
      }),
      blob: async () => new Blob(["zip"]),
    } as Response;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    const result = await exportBatch({
      seasonId: 7,
      selectedEpisodeIds: [101, 9007],
      conflictPolicy: "skip",
      concurrency: 1,
    });

    expect(isDownloadResult(result)).toBe(true);
    if (isDownloadResult(result)) {
      expect(result.filename).toBe("season-7.zip");
      expect(result.partial).toBe(true);
      expect(result.failedCount).toBe(2);
    }
  });

  it("defers Blob URL revocation after starting a download", () => {
    vi.useFakeTimers();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:test");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL");

    saveDownload({
      blob: new Blob(["ass"]),
      filename: "season-7.zip",
      mediaType: "application/zip",
      partial: false,
      failedCount: 0,
    });

    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
    vi.useRealTimers();
  });

  it("decodes UTF-8 attachment filenames", async () => {
    const response = {
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": "text/plain; charset=utf-8",
        "content-disposition":
          "attachment; filename=\"download.ass\"; " +
          "filename*=UTF-8''%E4%B8%AD%E6%96%87%E8%A7%86%E9%A2%91.ass",
      }),
      blob: async () => new Blob(["ass"]),
    } as Response;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    const result = await exportSingle({
      input: "BV123",
      conflictPolicy: "overwrite",
    });

    expect(isDownloadResult(result)).toBe(true);
    if (isDownloadResult(result)) {
      expect(result.filename).toBe("中文视频.ass");
    }
  });

  it("preserves server error details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "selected episode is invalid" }, 400),
    );

    await expect(
      exportBatch({
        seasonId: 1,
        selectedEpisodeIds: [999],
        conflictPolicy: "skip",
        concurrency: 1,
      }),
    ).rejects.toThrow("selected episode is invalid");
  });
});
