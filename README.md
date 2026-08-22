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
before rendering. `ss` inputs currently resolve season data only and return a
clear unsupported-export error; batch downloading and Web UI integration are
outside this release.
