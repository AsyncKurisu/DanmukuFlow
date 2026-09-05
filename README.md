# DanmukuFlow

**项目仍处于开发过程中...**

DanmukuFlow 用于将 Bilibili XML、BV 视频和番剧弹幕转换为 ASS 字幕，并提供 CLI 和本地 FastAPI Web 服务。

## 安装

```powershell
python -m pip install -e .
```

项目要求 Python 3.8 或更高版本。

## Bilibili Cookie 配置

如果匿名请求遇到 Bilibili `-352` 风控错误，可以配置完整登录态 Cookie。CLI 和 Web 使用同一个 `.env` 文件。

### CLI

1. 复制项目根目录的 `.env.example` 为 `.env`：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 从已登录的 `bilibili.com` 浏览器请求中复制完整 Cookie，并粘贴到 `.env`：

   ```dotenv
   BILIBILI_COOKIE="SESSDATA=...; bili_jct=...; buvid3=..."
   ```

3. 重新启动 CLI 使配置生效。

### Web

打开页面右上角的“设置”，粘贴同一份完整 Cookie 并点击“保存并应用”。服务会将 Cookie 写入同一个 `.env`，并立即刷新当前登录态，无需重启 FastAPI。

程序启动时读取 `.env`。同名操作系统环境变量优先于 `.env`，也可以使用 `DANMUKUFLOW_ENV_FILE` 指定其他配置文件：

```powershell
$env:DANMUKUFLOW_ENV_FILE = "C:\path\to\danmukuflow.env"
```

`.env` 包含登录凭据，已被 `.gitignore` 忽略，不要提交或公开分享。程序不会通过 Web API 返回 Cookie，也不会将 Cookie 写入日志。

未配置 Cookie 时仍可以进行匿名请求。Cookie、请求限速和退避重试不能保证永久绕过 Bilibili 风控。Cookie 过期后，CLI 重新编辑 `.env`，Web 重新粘贴保存。

## CLI

```powershell
danmukuflow convert input.xml
danmukuflow convert input.xml --output .\output\result.ass
danmukuflow convert BV1z44y1E7m6 --page 2 --output .\output\result.ass
danmukuflow convert ep473502 --output .\output\result.ass
danmukuflow batch ss28296 --video-dir .\videos
danmukuflow batch ss28296 --video-dir .\videos --episodes 1-12
danmukuflow batch ss28296 --video-dir .\videos --concurrency 1 --overwrite
```

`--page` 仅适用于 BV 视频。批量任务默认并发为 1，以降低连续请求触发风控的概率；可以通过 `--concurrency` 调整。

批量任务支持 `all`、`1-12`、`1,3,5` 和 `1,3-5,8` 等选集表达式。已有 ASS 文件默认跳过，`--overwrite` 可覆盖，`--skip-existing` 保留为兼容参数。

## Python API

```python
from pathlib import Path

from danmukuflow import ExportRequest, ExportService, XMLSource

result = ExportService().export(
    ExportRequest(
        source=XMLSource(Path("input.xml")),
        output_path=Path("output.ass"),
    )
)

print(result.output_path)
```

## Web 服务

启动本地 FastAPI 服务：

```powershell
uvicorn danmukuflow.web:app --host 127.0.0.1 --port 8000
```

建议绑定 `127.0.0.1`，不要将包含本地文件目录选择和 Bilibili 登录态能力的服务暴露到公网。

主要接口：

```text
POST /api/resolve
POST /api/seasons/resolve
POST /api/directories/select
POST /api/exports
POST /api/batch-exports
GET  /api/files/{artifact_id}
```

未提供 `output_dir` 时，单条导出返回 ASS 下载附件；批量导出在全部成功且只有一个文件时直接返回 ASS，多个文件返回 ZIP。部分成功时，成功的 ASS 会打包为 ZIP，并附带 `batch-result.json` 保存失败原因。浏览器下载目录由浏览器自行决定，服务端不会读取或控制该目录。提供 `output_dir` 时，服务端负责目录创建、命名和文件写入。

批量请求可以使用两种互斥模式：

- `output_dir`：普通批量输出目录；
- `video_dir`：扫描本地视频、匹配真实剧集，并将 ASS 写入对应视频目录。

普通批量输出未指定自定义模板时，ASS 直接写入 `output_dir`，默认命名为 `{season_title}-{episode_no}.ass`，不会创建番剧子目录，也不会加入 `episode_id`。自定义模板仍可使用子目录和 `episode_id`。`video_dir` 模式继续使用对应本地视频的文件名 stem。

视频扫描、剧集匹配、ASS 文件命名和弹幕导出均由后端完成，前端只展示服务端返回的状态、原因和路径。

## Web 前端

前端位于与 `src` 同级的 `web` 目录，使用 React、Vite 和 TypeScript。

安装依赖：

```powershell
cd web
npm install
```

开发模式需要分别启动 FastAPI 和 Vite：

```powershell
# 终端 1，在项目根目录执行
uvicorn danmukuflow.web:app --host 127.0.0.1 --port 8000

# 终端 2，在 web 目录执行
npm run dev
```

Vite 会将 `/api` 请求代理到 `http://127.0.0.1:8000`。生产构建：

```powershell
cd web
npm run build
```

构建后的 `web/dist` 存在时，FastAPI 会自动托管前端页面：

```powershell
uvicorn danmukuflow.web:app --host 127.0.0.1 --port 8000
```

目录按钮会让运行 FastAPI 的 Windows 本机打开原生文件夹选择器。浏览器必须访问同一台电脑上的服务，否则选择器会在服务器所在电脑上打开。

## Bilibili 请求与 `-352`

Bilibili 客户端会使用基础浏览器请求头、可选 Cookie、HTTPS 弹幕接口和线程安全的请求间隔。

- 默认批量并发为 1；
- `-352` 会进行有限的退避重试；
- 网络错误和临时 HTTP 错误保留原有重试；
- `404`、资源不存在和数据结构错误不会重试；
- 重试失败后，批量结果仍保留部分成功和每集失败原因。

GitHub issue 中针对动态接口附加 `DedeUserID` 的做法不直接适用于 DanmukuFlow，因为本项目请求的是弹幕分段接口，不是用户动态接口。

## 测试

```powershell
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

前端测试和构建：

```powershell
cd web
npm test
npm run build
```
