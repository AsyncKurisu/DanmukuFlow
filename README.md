# DanmukuFlow

DanmukuFlow converts Bilibili XML danmaku files to ASS subtitles.

## CLI

```bash
danmu2ass convert input.xml
danmu2ass convert input.xml --output ./output/result.ass
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

This project currently supports local XML input only. BV, season, episode,
network fetching, batch downloading, and Web UI integration are intentionally
not implemented yet.
