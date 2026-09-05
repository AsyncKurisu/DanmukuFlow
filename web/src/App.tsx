import { useEffect, useState } from "react";
import {
  ApiError,
  getBilibiliSettings,
  saveBilibiliCookie,
} from "./api/client";
import { BatchExportPanel } from "./components/BatchExportPanel";
import { SingleExportPanel } from "./components/SingleExportPanel";

type View = "single" | "batch";

export default function App() {
  const [view, setView] = useState<View>("single");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [cookie, setCookie] = useState("");
  const [settings, setSettings] = useState<{ configured: boolean; cookie_count: number } | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  useEffect(() => {
    if (!settingsOpen) return;
    setSettingsMessage(null);
    setSettingsError(null);
    getBilibiliSettings()
      .then(setSettings)
      .catch((error: unknown) => {
        setSettingsError(error instanceof ApiError ? error.detail : "读取设置失败");
      });
  }, [settingsOpen]);

  async function handleSaveCookie() {
    setSettingsBusy(true);
    setSettingsMessage(null);
    setSettingsError(null);
    try {
      const result = await saveBilibiliCookie(cookie);
      setSettings(result);
      setCookie("");
      setSettingsMessage("Cookie 已写入 .env 并立即生效");
    } catch (error: unknown) {
      setSettingsError(error instanceof ApiError ? error.detail : "保存 Cookie 失败");
    } finally {
      setSettingsBusy(false);
    }
  }

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
        <div className="header-actions">
          <button
            type="button"
            className="button secondary settings-button"
            onClick={() => setSettingsOpen((open) => !open)}
            aria-expanded={settingsOpen}
          >
            设置
          </button>
          <div className="header-note">本地 Web 服务 · FastAPI</div>
        </div>
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

      {settingsOpen && (
        <div className="settings-backdrop" role="presentation" onClick={() => setSettingsOpen(false)}>
          <section
            className="settings-panel panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <div>
                <h3 id="settings-title">Bilibili 登录设置</h3>
                <span className="muted">完整 Cookie 会保存到服务端 .env，不会保存在浏览器。</span>
              </div>
              <button type="button" className="button secondary" onClick={() => setSettingsOpen(false)}>
                关闭
              </button>
            </div>
            <p className="settings-status">
              当前状态：{settings?.configured ? `已配置（${settings.cookie_count} 项）` : "未配置"}
            </p>
            <label className="field">
              <span>浏览器 Cookie</span>
              <textarea
                value={cookie}
                onChange={(event) => setCookie(event.target.value)}
                placeholder="粘贴从 bilibili.com 复制的完整 Cookie"
                autoComplete="off"
                spellCheck={false}
                rows={6}
              />
            </label>
            {settingsError && <p className="message error-message">{settingsError}</p>}
            {settingsMessage && <p className="message success-message">{settingsMessage}</p>}
            <div className="button-row">
              <button
                type="button"
                className="button primary"
                disabled={settingsBusy || !cookie.trim()}
                onClick={handleSaveCookie}
              >
                {settingsBusy ? "保存中..." : "保存并应用"}
              </button>
            </div>
          </section>
        </div>
      )}

      <footer className="app-footer">
        文件解析、弹幕下载、匹配、命名和渲染均由服务端统一处理。
      </footer>
    </div>
  );
}
