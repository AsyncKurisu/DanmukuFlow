# DanmukuFlow

DanmukuFlow converts Bilibili XML, BV video, and episode danmaku to ASS
subtitles. All sources use the same internal danmaku model and ASS renderer.

## CLI

```bash
danmukuflow convert input.xml
danmukuflow convert input.xml --output ./output/result.ass
danmukuflow convert BV1z44y1E7m6 --page 2 --output ./output/result.ass
danmukuflow convert ep473502 --output ./output/result.ass
danmukuflow convert ss28296
danmukuflow batch ss28296 --video-dir ./videos
danmukuflow batch ss28296 --video-dir ./videos --episodes 1-12
danmukuflow batch ss28296 --video-dir ./videos --concurrency 3 --overwrite
```

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

`BV` and `ep` inputs fetch details and segmented danmaku data from Bilibili
before rendering. `ss` remains unsupported by the single-item `convert`
command, but can be used with `batch` and a local video directory.

For the CLI, `batch --video-dir` is optional. When omitted, the current
working directory is used. An explicitly supplied directory that does not
exist is still reported as an error instead of silently falling back to a
different directory.

Batch export scans only the immediate directory for supported video files
(`.mkv`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.m4v`, and `.ts`). It compares the
numeric fields across the directory and uses the field that changes and agrees
with the real Season episode numbers. This supports both bracketed names and
names such as `S01E01`, for example:

```text
[Judas] Durarara - S01E01.mkv
[Judas] Durarara - S01E02.mkv
```

When the changing field can be identified, the generated ASS file is written
beside the video with exactly the same stem:

```text
[VCB-Studio] One-Punch Man [09][Ma10p_1080p][x265_flac].ass
```

If a directory contains only one video, has no changing numeric field, or the
file names cannot be matched reliably, the service does not guess from a
single file. Without `--episodes`, it downloads the first real Season episode
and writes a fallback file such as `Demo Season-ep1.ass`. With an explicit
selection, fallback files use the selected numbers, for example
`日常-ep2.ass`. Fallback exports are successful results with a separate
`fallback` status; they do not change the failure exit code.

Existing ASS files are skipped by default. Use `--overwrite` to download and
render them again. Batch processing does not recurse into subdirectories,
does not guess special episodes such as `SP01` or `OVA`, and continues other
episodes when one episode fails. Web UI integration remains outside this
release.
