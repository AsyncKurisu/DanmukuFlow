import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BatchExportResult } from "../types";
import { BatchResultPanel } from "./ExportResultPanel";

describe("BatchResultPanel", () => {
  it("shows detailed matching statuses and summary counts", () => {
    const result: BatchExportResult = {
      total: 4,
      matched: 1,
      selected: 2,
      succeeded: 1,
      failed: 0,
      skipped: 0,
      unmatched_local: 1,
      unmatched_episode: 1,
      ambiguous: 1,
      pending: 0,
      running: 0,
      fallback: 1,
      items: [
        {
          episode_id: 101,
          display_number: 1,
          episode_title: "Episode 1",
          local_video_path: null,
          output_path: null,
          status: "fallback",
          reason: "fallback filename",
          error: null,
          fallback: true,
          artifact: null,
        },
        {
          episode_id: null,
          display_number: 9,
          episode_title: null,
          local_video_path: "video-09.mkv",
          output_path: null,
          status: "unmatched_local",
          reason: "no matching episode",
          error: null,
          fallback: false,
          artifact: null,
        },
      ],
    };

    render(<BatchResultPanel result={result} />);

    expect(screen.getAllByText("未匹配本地视频")).toHaveLength(2);
    expect(screen.getByText("回退匹配")).toBeInTheDocument();
    expect(screen.getByText("fallback filename")).toBeInTheDocument();
    expect(screen.getByText("video-09.mkv")).toBeInTheDocument();
  });
});
