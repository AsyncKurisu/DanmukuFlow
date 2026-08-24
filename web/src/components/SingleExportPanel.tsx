import { useState } from "react";
import {
  ApiError,
  exportSingle,
  isDownloadResult,
  resolveInput,
  saveDownload,
} from "../api/client";
import type { ExportResult, InputKind, ResolveResponse } from "../types";
import { DirectoryPickerField } from "./DirectoryPickerField";
import { SingleResultPanel } from "./ExportResultPanel";

export function SingleExportPanel() {
  const [kind, setKind] = useState<InputKind>("bv");
  const [input, setInput] = useState("");
  const [page, setPage] = useState("");
  const [xmlFile, setXmlFile] = useState<File | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [template, setTemplate] = useState("");
  const [conflictPolicy, setConflictPolicy] = useState<
    "overwrite" | "skip" | "error"
  >("overwrite");
  const [resolved, setResolved] = useState<ResolveResponse | null>(null);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"resolve" | "export" | null>(null);

  function apiMessage(error: unknown): string {
    return error instanceof ApiError ? error.reason ?? error.detail : String(error);
  }

  async function handleResolve() {
    if (!input.trim()) {
      setMessage("请输入 BV 或 ep。");
      return;
    }
    setMessage("");
    setBusy("resolve");
    try {
      setResolved(await resolveInput(input.trim(), page ? Number(page) : undefined));
    } catch (error) {
      setResolved(null);
      setMessage(apiMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function handleExport() {
    if (kind === "xml" && !xmlFile) {
      setMessage("请选择 XML 文件。");
      return;
    }
    if (kind !== "xml" && !input.trim()) {
      setMessage("请输入 BV 或 ep。");
      return;
    }

    setMessage("");
    setResult(null);
    setBusy("export");
    try {
      const response = await exportSingle({
        input: kind === "xml" ? undefined : input.trim(),
        page: kind === "bv" && page ? Number(page) : undefined,
        xmlFile: kind === "xml" ? xmlFile : null,
        outputDir: outputDir.trim() || undefined,
        namingTemplate: template.trim() || undefined,
        conflictPolicy,
      });
      if (isDownloadResult(response)) {
        saveDownload(response);
        setMessage(`已开始下载 ${response.filename}`);
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
          <h2>单条导出</h2>
          <p className="muted">BV、ep 和 XML 共用同一套后端导出流程。</p>
        </div>
      </div>

      <div className="panel form-panel">
        <div className="field-group">
          <span className="field-label">输入类型</span>
          <div className="segmented">
            {(["bv", "ep", "xml"] as InputKind[]).map((item) => (
              <button
                type="button"
                key={item}
                className={kind === item ? "active" : ""}
                onClick={() => {
                  setKind(item);
                  setResolved(null);
                  setMessage("");
                }}
              >
                {item.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {kind === "xml" ? (
          <label className="field">
            <span>XML 文件</span>
            <input
              type="file"
              accept=".xml,text/xml,application/xml"
              onChange={(event) => setXmlFile(event.target.files?.[0] ?? null)}
            />
            <small className="muted">
              {xmlFile?.name ?? "只上传本地文件，不提交服务器路径"}
            </small>
          </label>
        ) : (
          <label className="field">
            <span>{kind === "bv" ? "BV 或 Bilibili URL" : "ep 或 Bilibili URL"}</span>
            <input
              value={input}
              placeholder={kind === "bv" ? "例如 BV1..." : "例如 ep123..."}
              onChange={(event) => setInput(event.target.value)}
            />
          </label>
        )}

        {kind === "bv" && (
          <label className="field narrow-field">
            <span>Page</span>
            <input
              type="number"
              min="1"
              value={page}
              placeholder="默认 1"
              onChange={(event) => setPage(event.target.value)}
            />
          </label>
        )}

        <div className="button-row">
          {kind !== "xml" && (
            <button
              type="button"
              className="button secondary"
              disabled={busy !== null}
              onClick={handleResolve}
            >
              {busy === "resolve" ? "解析中..." : "解析详情"}
            </button>
          )}
          <button
            type="button"
            className="button primary"
            disabled={busy !== null}
            onClick={handleExport}
          >
            {busy === "export" ? "导出中..." : "开始导出"}
          </button>
        </div>
      </div>

      {resolved && (
        <section className="panel info-panel">
          {resolved.kind === "bv" && (
            <>
              <strong>{resolved.video.title}</strong>
              <span className="muted">
                {resolved.video.bvid} · {resolved.video.pages.length} 个 Page
              </span>
            </>
          )}
          {resolved.kind === "ep" && (
            <>
              <strong>{resolved.episode.title || resolved.episode.long_title}</strong>
              <span className="muted">
                {resolved.season.title} · Episode ID {resolved.episode.episode_id}
              </span>
            </>
          )}
        </section>
      )}

      <section className="panel form-panel output-options">
        <div className="panel-heading">
          <div>
            <h3>输出设置</h3>
            <span className="muted">
              不填写输出目录时由浏览器负责保存下载文件。
            </span>
          </div>
        </div>

        <div className="field">
          <span>输出目录（可选）</span>
          <DirectoryPickerField
            label="输出目录"
            value={outputDir}
            placeholder="留空则下载 ASS"
            kind="output"
            onChange={setOutputDir}
            onError={setMessage}
          />
        </div>

        <label className="field">
          <span>命名模板（可选）</span>
          <input
            value={template}
            placeholder="例如 {video_title}.ass"
            onChange={(event) => setTemplate(event.target.value)}
          />
        </label>

        <label className="field narrow-field">
          <span>冲突策略</span>
          <select
            value={conflictPolicy}
            onChange={(event) =>
              setConflictPolicy(event.target.value as typeof conflictPolicy)
            }
          >
            <option value="overwrite">overwrite</option>
            <option value="skip">skip</option>
            <option value="error">error</option>
          </select>
        </label>
      </section>

      {message && <p className="message error-message">{message}</p>}
      {result && <SingleResultPanel result={result} />}
    </section>
  );
}
