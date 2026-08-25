# 变更日志

## 0.0.1 (2026-08-24  开发中)

使用 Codex 完成前后端搭建，后续实现代码轻量化工作并完善使用手册，预期目标除了 CLI 以外，将web端能打包为可执行文件，真正开箱即用。

### Feature

- 新增独立 React/Vite/TypeScript 前端，前端仅负责用户交互、API 调用、选集操作、下载处理和结果展示。([#6](https://github.com/AsyncKurisu/DanmukuFlow/pull/6))
- 统一输出规则与 Web API 服务层，使 CLI 和 Web API 共用相同的输入解析、Episode 选择、导出服务、ASS 渲染和输出逻辑。([#5](https://github.com/AsyncKurisu/DanmukuFlow/pull/5))
- 在 PR3 的单条 B 站导出能力基础上，实现番剧批量导出。([#4](https://github.com/AsyncKurisu/DanmukuFlow/pull/4))
- 在现有统一单条导出任务基础上，实现 B 站输入的数据获取链路。([#3](https://github.com/AsyncKurisu/DanmukuFlow/pull/3))
- 定义后续 CLI 和 Web 共用的任务输入、任务配置、执行结果和错误模型，并实现 CLI 对本地 XML 转 ASS 的正式支持。([#2](https://github.com/AsyncKurisu/DanmukuFlow/pull/2))
- 初始化 Python 模块，完成 XML 文件解析为内部弹幕模型的工作并执行 ASS 渲染得到 ASS 文件。([#1](https://github.com/AsyncKurisu/DanmukuFlow/pull/1))
