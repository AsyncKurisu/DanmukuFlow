import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Episode } from "../types";
import { EpisodeSelector } from "./EpisodeSelector";

const episodes: Episode[] = [
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

describe("EpisodeSelector", () => {
  it("uses real episode ids for single and bulk selection", () => {
    let selected = new Set<number>();
    const { rerender } = render(
      <EpisodeSelector
        episodes={episodes}
        selectedIds={selected}
        onChange={(ids) => {
          selected = ids;
        }}
      />,
    );

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(selected).toEqual(new Set([101]));

    rerender(
      <EpisodeSelector
        episodes={episodes}
        selectedIds={selected}
        onChange={(ids) => {
          selected = ids;
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "全选" }));
    expect(selected).toEqual(new Set([101, 9007]));

    fireEvent.click(screen.getByRole("button", { name: "取消全选" }));
    expect(selected).toEqual(new Set());
  });
});
