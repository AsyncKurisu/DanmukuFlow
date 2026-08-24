import { useState } from "react";
import { BatchExportPanel } from "./components/BatchExportPanel";
import { SingleExportPanel } from "./components/SingleExportPanel";

type View = "single" | "batch";

export default function App() {
  const [view, setView] = useState<View>("single");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">DF</span>
          <div>
            <h1>DanmukuFlow</h1>
            <p>弹幕 ASS 导出工具</p>
          </div>
        </div>
        <div className="header-note">本地 Web 服务 · FastAPI</div>
      </header>

      <main className="app-main">
        <nav className="top-tabs" aria-label="导出模式">
          <button
            type="button"
            className={view === "single" ? "active" : ""}
            onClick={() => setView("single")}
          >
            单条导出
          </button>
          <button
            type="button"
            className={view === "batch" ? "active" : ""}
            onClick={() => setView("batch")}
          >
            Season 批量
          </button>
        </nav>
        {view === "single" ? <SingleExportPanel /> : <BatchExportPanel />}
      </main>

      <footer className="app-footer">
        文件解析、弹幕下载、匹配、命名和渲染均由服务端统一处理。
      </footer>
    </div>
  );
}
