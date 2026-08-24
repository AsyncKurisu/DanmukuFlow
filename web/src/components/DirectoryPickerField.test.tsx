import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DirectoryPickerField } from "./DirectoryPickerField";

const mocks = vi.hoisted(() => ({
  selectDirectory: vi.fn(),
}));

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {},
  selectDirectory: mocks.selectDirectory,
}));

describe("DirectoryPickerField", () => {
  it("writes the selected output directory", async () => {
    mocks.selectDirectory.mockResolvedValue("C:\\Users\\Kurisu\\Desktop\\test_ss");
    const onChange = vi.fn();

    render(
      <DirectoryPickerField
        label="普通输出目录"
        value=""
        placeholder="留空则下载"
        kind="output"
        onChange={onChange}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "浏览普通输出目录" }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        "C:\\Users\\Kurisu\\Desktop\\test_ss",
      );
    });
  });

  it("does not change the value when selection is cancelled", async () => {
    mocks.selectDirectory.mockResolvedValue(null);
    const onChange = vi.fn();

    render(
      <DirectoryPickerField
        label="本地视频目录"
        value="C:\\Videos"
        placeholder=""
        kind="video"
        onChange={onChange}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "浏览本地视频目录" }));

    await waitFor(() => {
      expect(mocks.selectDirectory).toHaveBeenCalledWith("video");
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});
