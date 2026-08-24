export type InputKind = "bv" | "ep" | "xml";
export type ConflictPolicy = "overwrite" | "skip" | "error";
export type OutputMode = "directory" | "download";

export type BatchItemStatus =
  | "succeeded"
  | "failed"
  | "skipped"
  | "unmatched_local"
  | "unmatched_episode"
  | "ambiguous"
  | "fallback"
  | "pending"
  | "running";

export interface VideoPage {
  page: number;
  part: string;
  cid: number;
  duration_s: number;
}

export interface Video {
  bvid: string;
  title: string;
  pages: VideoPage[];
}

export interface Episode {
  episode_id: number;
  aid: number;
  bvid: string;
  cid: number;
  title: string | null;
  long_title: string | null;
  duration_s: number;
  metadata: Record<string, unknown>;
  display_number: number | null;
}

export interface Season {
  season_id: number;
  title: string;
  episodes: Episode[];
  metadata: Record<string, unknown>;
}

export type ResolveResponse =
  | { kind: "bv"; video: Video }
  | { kind: "ep"; season: Season; episode: Episode }
  | { kind: "ss"; season: Season; episodes: Episode[] };

export interface OutputArtifact {
  artifact_id: string;
  filename: string;
  media_type: string;
  path: string | null;
  relative_path: string | null;
  metadata: Record<string, unknown>;
  skipped: boolean;
}

export interface ExportResult {
  success: boolean;
  output_path: string | null;
  danmaku_count: number;
  skipped: boolean;
  metadata: Record<string, unknown>;
  artifact: OutputArtifact | null;
}

export interface BatchItemResult {
  episode_id: number | null;
  display_number: number | null;
  episode_title: string | null;
  local_video_path: string | null;
  output_path: string | null;
  status: BatchItemStatus;
  reason: string | null;
  error: string | null;
  fallback: boolean;
  artifact: OutputArtifact | null;
}

export interface BatchExportResult {
  total: number;
  matched: number;
  selected: number;
  succeeded: number;
  failed: number;
  skipped: number;
  unmatched_local: number;
  unmatched_episode: number;
  ambiguous: number;
  pending: number;
  running: number;
  fallback: number;
  items: BatchItemResult[];
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
  mediaType: string;
  partial: boolean;
  failedCount: number;
}
