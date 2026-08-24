from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from danmukuflow.models import (
    Episode,
    OutputConfig,
    OutputMode,
    OutputOrganizationMode,
    RenderConfig,
    Season,
    Video,
    VideoPage,
)


class RenderConfigSchema(BaseModel):
    duration: float = 15.0
    width: int = 1280
    height: int = 720
    font: str = "\u9ed1\u4f53"
    font_size: int = 25
    width_ratio: float = 1.2
    horizontal_gap: float = 20.0
    lane_size: int = 32
    float_percentage: float = 0.5
    alpha: float = 0.7
    bold: bool = False
    outline: float = 0.8
    time_offset: float = 0.0
    denylist: List[str] = Field(default_factory=list)

    def to_model(self):
        return RenderConfig(
            duration=self.duration,
            width=self.width,
            height=self.height,
            font=self.font,
            font_size=self.font_size,
            width_ratio=self.width_ratio,
            horizontal_gap=self.horizontal_gap,
            lane_size=self.lane_size,
            float_percentage=self.float_percentage,
            alpha=self.alpha,
            bold=self.bold,
            outline=self.outline,
            time_offset=self.time_offset,
            denylist=tuple(self.denylist),
        )


class OutputConfigSchema(BaseModel):
    output_dir: Optional[str] = None
    naming_template: Optional[str] = None
    organization_mode: OutputOrganizationMode = OutputOrganizationMode.FLAT
    conflict_policy: str = "overwrite"
    mode: OutputMode = OutputMode.DIRECTORY
    allowed_output_roots: List[str] = Field(default_factory=list)

    def to_model(self):
        return OutputConfig(
            output_dir=Path(self.output_dir) if self.output_dir else None,
            naming_template=self.naming_template,
            organization_mode=self.organization_mode,
            conflict_policy=self.conflict_policy,
            mode=self.mode,
            allowed_output_roots=tuple(
                Path(item) for item in self.allowed_output_roots
            ),
        )


class ResolveRequestSchema(BaseModel):
    input: str
    page: Optional[int] = None


class SingleExportRequestSchema(BaseModel):
    input: Optional[str] = None
    page: Optional[int] = None
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    naming_template: Optional[str] = None
    organization_mode: OutputOrganizationMode = OutputOrganizationMode.FLAT
    conflict_policy: str = "overwrite"
    render_config: RenderConfigSchema = Field(default_factory=RenderConfigSchema)
    xml_content: Optional[str] = None
    xml_filename: Optional[str] = None


class BatchExportRequestSchema(BaseModel):
    season_id: int
    selected_episode_ids: List[int] = Field(default_factory=list)
    output_dir: Optional[str] = None
    naming_template: Optional[str] = None
    organization_mode: OutputOrganizationMode = OutputOrganizationMode.SEASON
    conflict_policy: str = "overwrite"
    concurrency: int = 3
    render_config: RenderConfigSchema = Field(default_factory=RenderConfigSchema)


def episode_to_dict(episode: Episode):
    return {
        "episode_id": episode.episode_id,
        "aid": episode.aid,
        "bvid": episode.bvid,
        "cid": episode.cid,
        "title": episode.title,
        "long_title": episode.long_title,
        "duration_s": episode.duration_s,
        "metadata": episode.metadata,
        "display_number": episode.display_number,
    }


def video_page_to_dict(page: VideoPage):
    return {
        "page": page.page,
        "part": page.part,
        "cid": page.cid,
        "duration_s": page.duration_s,
    }


def video_to_dict(video: Video):
    return {
        "bvid": video.bvid,
        "title": video.title,
        "pages": [video_page_to_dict(page) for page in video.pages],
    }


def season_to_dict(season: Season):
    return {
        "season_id": season.season_id,
        "title": season.title,
        "episodes": [episode_to_dict(episode) for episode in season.episodes],
        "metadata": season.metadata,
    }
