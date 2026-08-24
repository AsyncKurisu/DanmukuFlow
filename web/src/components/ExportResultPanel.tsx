import type { BatchExportResult, ExportResult } from "../types";

const STATUS_LABELS: Record<string, string> = {
  succeeded: "成功",
  failed: "失败",
  skipped: "已跳过",
  unmatched_local: "未匹配本地视频",
  unmatched_episode: "未匹配剧集",
  ambiguous: "存在歧义",
  fallback: "回退匹配",
  pending: "待处理",
  running: "处理中",
};

interface SingleResultProps {
  result: ExportResult;
}

export function SingleResultPanel({ result }: SingleResultProps) {
  const title = String(result.metadata.title ?? result.artifact?.filename ?? "ASS 文件");
  return (
    <section className={`result-card ${result.skipped ? "warning" : "success"}`}>
      <div className="result-title">
        <span className="status-dot" />
        <strong>{result.skipped ? "已跳过现有文件" : "导出完成"}</strong>
      </div>
      <dl className="result-list">
        <div>
          <dt>标题</dt>
          <dd>{title}</dd>
        </div>
        <div>
          <dt>弹幕数量</dt>
          <dd>{result.danmaku_count}</dd>
        </div>
        <div>
          <dt>输出</dt>
          <dd>{result.output_path ?? result.artifact?.filename ?? "浏览器下载"}</dd>
        </div>
      </dl>
    </section>
  );
}

interface BatchResultProps {
  result: BatchExportResult;
}

export function BatchResultPanel({ result }: BatchResultProps) {
  const stats = [
    ["total", "总数", result.total],
    ["matched", "已匹配", result.matched],
    ["selected", "已选择", result.selected],
    ["succeeded", "成功", result.succeeded],
    ["failed", "失败", result.failed],
    ["skipped", "跳过", result.skipped],
    ["unmatched_local", "未匹配本地视频", result.unmatched_local],
    ["unmatched_episode", "未匹配剧集", result.unmatched_episode],
    ["ambiguous", "歧义", result.ambiguous],
    ["fallback", "回退", result.fallback],
    ["pending", "待处理", result.pending],
    ["running", "处理中", result.running],
  ];

  return (
    <section className="panel result-panel">
      <div className="panel-heading">
        <div>
          <h3>批量结果</h3>
          <span className="muted">
            {result.pending > 0 || result.running > 0
              ? `待处理 ${result.pending}，处理中 ${result.running}`
              : "任务已完成"}
          </span>
        </div>
      </div>

      <div className="stat-grid">
        {stats.map(([key, label, value]) => (
          <div className={`stat-cell stat-${key}`} key={key}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="result-table-wrap">
        <table className="result-table">
          <thead>
            <tr>
              <th>剧集</th>
              <th>状态</th>
              <th>本地视频</th>
              <th>ASS 输出</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            {result.items.map((item, index) => (
              <tr key={`${item.episode_id ?? "local"}-${index}`}>
                <td>
                  {item.display_number ?? "-"}{" "}
                  {item.episode_title ? `· ${item.episode_title}` : ""}
                </td>
                <td>
                  <span className={`status-badge status-${item.status}`}>
                    {STATUS_LABELS[item.status] ?? item.status}
                  </span>
                </td>
                <td className="path-cell">{item.local_video_path ?? "-"}</td>
                <td className="path-cell">
                  {item.output_path ?? item.artifact?.filename ?? "-"}
                </td>
                <td>
                  {item.reason ??
                    item.error ??
                    (item.fallback ? "使用回退策略" : "-")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
