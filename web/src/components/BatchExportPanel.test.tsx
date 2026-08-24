import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BatchExportResult, ResolveResponse } from "../types";

const mocks = vi.hoisted(() => ({
  resolveInput: vi.fn(),
  exportBatch: vi.fn(),
  isDownloadResult: vi.fn(() => false),
  saveDownload: vi.fn(),
}));

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {},
  resolveInput: mocks.resolveInput,
  exportBatch: mocks.exportBatch,
  isDownloadResult: mocks.isDownloadResult,
  saveDownload: mocks.saveDownload,
}));

import { BatchExportPanel } from "./BatchExportPanel";

const episodes = [
  {
    episode_id: 101,
    aid: 1,
    bvid: "BV1",
    cid: 11,
    title: "第一集",
    long_title: "Long 1",
    duration_s: 1,
    metadata: {},
    display_number: 1,
  },
  {
    episode_id: 9007,
    aid: 2,
    bvid: "BV2",
    cid: 22,
    title: "SP",
    long_title: "Special",
    duration_s: 1,
    metadata: {},
    display_number: null,
  },
];

const resolvedSeason: ResolveResponse = {
  kind: "ss",
  season: {
    season_id: 7,
    title: "Demo Season",
    metadata: {},
    episodes,
  },
  episodes,
};

const batchResult: BatchExportResult = {
  total: 1,
  matched: 1,
  selected: 1,
  succeeded: 1,
  failed: 0,
  skipped: 0,
  unmatched_local: 0,
  unmatched_episode: 0,
  ambiguous: 0,
  pending: 0,
  running: 0,
  fallback: 0,
  items: [],
};

describe("BatchExportPanel", () => {
  it("renders backend episodes and submits their real ids", async () => {
    mocks.resolveInput.mockResolvedValue(resolvedSeason);
    mocks.exportBatch.mockResolvedValue(batchResult);
    render(<BatchExportPanel />);

    fireEvent.change(
      screen.getByPlaceholderText("例如 ss123 或 Bilibili Season URL"),
      { target: { value: "ss7" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "查询 Season" }));

    expect(await screen.findByText("Demo Season")).toBeInTheDocument();
    expect(screen.getByText("id 9007")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "取消全选" }));
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: "导出已选 1 集" }));

    await waitFor(() => {
      expect(mocks.exportBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          seasonId: 7,
          selectedEpisodeIds: [9007],
          concurrency: 1,
        }),
      );
    });
  });

  it("reports partial ZIP downloads", async () => {
    mocks.resolveInput.mockResolvedValue(resolvedSeason);
    mocks.exportBatch.mockResolvedValue({
      filename: "season-7.zip",
      partial: true,
      failedCount: 1,
      blob: new Blob(["zip"]),
    });
    mocks.isDownloadResult.mockReturnValue(true);
    render(<BatchExportPanel />);

    fireEvent.change(
      screen.getByPlaceholderText("例如 ss123 或 Bilibili Season URL"),
      { target: { value: "ss7" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "查询 Season" }));
    await screen.findByText("Demo Season");
    fireEvent.click(screen.getByRole("button", { name: "导出已选 2 集" }));

    await waitFor(() => {
      expect(mocks.saveDownload).toHaveBeenCalled();
    });
    expect(screen.getByText(/batch-result\.json/)).toBeInTheDocument();
  });
});
