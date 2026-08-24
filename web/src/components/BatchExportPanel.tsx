import { useState } from "react";
import {
  ApiError,
  exportBatch,
  isDownloadResult,
  resolveInput,
  saveDownload,
} from "../api/client";
import type { BatchExportResult, ConflictPolicy, Season } from "../types";
import { DirectoryPickerField } from "./DirectoryPickerField";
import { EpisodeSelector } from "./EpisodeSelector";
import { BatchResultPanel } from "./ExportResultPanel";

export function BatchExportPanel() {
  const [input, setInput] = useState("");
  const [season, setSeason] = useState<Season | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [videoDir, setVideoDir] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [template, setTemplate] = useState("");
  const [conflictPolicy, setConflictPolicy] = useState<ConflictPolicy>("skip");
  const [concurrency, setConcurrency] = useState("1");
  const [result, setResult] = useState<BatchExportResult | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"resolve" | "export" | null>(null);

  function apiMessage(error: unknown): string {
    return error instanceof ApiError ? error.reason ?? error.detail : String(error);
  }

  async function handleResolve() {
    if (!input.trim()) {
      setMessage("请输入 ss 或 Bilibili Season URL。");
      return;
    }

    setMessage("");
    setResult(null);
    setBusy("resolve");
    try {
      const response = await resolveInput(input.trim());
      if (response.kind !== "ss") {
        throw new Error("批量导出只接受 ss 输入。");
      }
      setSeason(response.season);
      setSelectedIds(new Set(response.episodes.map((episode) => episode.episode_id)));
    } catch (error) {
      setSeason(null);
      setSelectedIds(new Set());
      setMessage(apiMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function handleExport() {
    if (!season) {
      setMessage("请先解析 Season。");
      return;
    }
    if (selectedIds.size === 0) {
      setMessage("请至少选择一集。");
      return;
    }
    if (videoDir.trim() && outputDir.trim()) {
      setMessage("本地视频匹配模式与普通输出目录不能同时使用。");
      return;
    }

    setMessage("");
    setResult(null);
    setBusy("export");
    try {
      const response = await exportBatch({
        seasonId: season.season_id,
        selectedEpisodeIds: Array.from(selectedIds),
        videoDir: videoDir.trim() || undefined,
        outputDir: outputDir.trim() || undefined,
        namingTemplate: template.trim() || undefined,
        conflictPolicy,
        concurrency: Math.max(1, Math.min(8, Number(concurrency) || 1)),
      });
      if (isDownloadResult(response)) {
        saveDownload(response);
        setMessage(
          response.partial
            ? `已开始下载 ${response.filename}，部分剧集失败，详情见 ZIP 内的 batch-result.json`
            : `已开始下载 ${response.filename}`,
        );
      } else {
        setResult(response);
      }
    } catch (error) {
      setMessage(apiMessage(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="workspace">
      <div className="workspace-header">
        <div>
          <h2>Season 批量导出</h2>
          <p className="muted">
            先查询真实剧集，再按 Episode ID 提交批量任务。
          </p>
        </div>
      </div>

      <div className="panel form-panel">
        <label className="field">
          <span>Season 输入</span>
          <input
            value={input}
            placeholder="例如 ss123 或 Bilibili Season URL"
            onChange={(event) => setInput(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="button primary"
          disabled={busy !== null}
          onClick={handleResolve}
        >
          {busy === "resolve" ? "查询中..." : "查询 Season"}
        </button>
      </div>

      {season && (
        <>
          <section className="panel season-summary">
            <div>
              <span className="eyebrow">Season {season.season_id}</span>
              <h3>{season.title}</h3>
            </div>
            <span className="muted">{season.episodes.length} 个真实剧集</span>
          </section>

          <EpisodeSelector
            episodes={season.episodes}
            selectedIds={selectedIds}
            onChange={setSelectedIds}
          />

          <section className="panel form-panel output-options">
            <div className="panel-heading">
              <div>
                <h3>批量输出设置</h3>
                <span className="muted">
                  video_dir 用于扫描和匹配本地视频；output_dir 仅用于普通批量输出。
                </span>
              </div>
            </div>

            <div className="field">
              <span>本地视频目录（可选）</span>
              <DirectoryPickerField
                label="本地视频目录"
                value={videoDir}
                placeholder="填入后由服务端扫描并匹配视频"
                kind="video"
                onChange={setVideoDir}
                onError={setMessage}
              />
            </div>

            <div className="field">
              <span>普通输出目录（可选）</span>
              <DirectoryPickerField
                label="普通输出目录"
                value={outputDir}
                placeholder="留空则下载 ASS 或 ZIP"
                kind="output"
                onChange={setOutputDir}
                onError={setMessage}
              />
            </div>

            <div className="form-grid">
              <label className="field">
                <span>命名模板</span>
                <input
                  value={template}
                  placeholder="默认 {season_title}-{episode_no}.ass"
                  onChange={(event) => setTemplate(event.target.value)}
                />
              </label>
              <label className="field">
                <span>并发数</span>
                <input
                  type="number"
                  min="1"
                  max="8"
                  value={concurrency}
                  onChange={(event) => setConcurrency(event.target.value)}
                />
              </label>
              <label className="field">
                <span>冲突策略</span>
                <select
                  value={conflictPolicy}
                  onChange={(event) =>
                    setConflictPolicy(event.target.value as ConflictPolicy)
                  }
                >
                  <option value="overwrite">overwrite</option>
                  <option value="skip">skip</option>
                  <option value="error">error</option>
                </select>
              </label>
            </div>

            <button
              type="button"
              className="button primary"
              disabled={busy !== null}
              onClick={handleExport}
            >
              {busy === "export" ? "导出中..." : `导出已选 ${selectedIds.size} 集`}
            </button>
          </section>
        </>
      )}

      {message && <p className="message error-message">{message}</p>}
      {result && <BatchResultPanel result={result} />}
    </section>
  );
}
