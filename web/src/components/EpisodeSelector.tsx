import type { Episode } from "../types";

interface EpisodeSelectorProps {
  episodes: Episode[];
  selectedIds: Set<number>;
  onChange: (ids: Set<number>) => void;
}

export function EpisodeSelector({
  episodes,
  selectedIds,
  onChange,
}: EpisodeSelectorProps) {
  const allSelected = episodes.length > 0 && selectedIds.size === episodes.length;

  function toggle(episodeId: number) {
    const next = new Set(selectedIds);
    if (next.has(episodeId)) {
      next.delete(episodeId);
    } else {
      next.add(episodeId);
    }
    onChange(next);
  }

  return (
    <section className="panel episode-panel">
      <div className="panel-heading">
        <div>
          <h3>选集</h3>
          <span className="muted">
            已选择 {selectedIds.size} / {episodes.length}
          </span>
        </div>
        <div className="button-row">
          <button
            type="button"
            className="button secondary"
            onClick={() =>
              onChange(new Set(episodes.map((episode) => episode.episode_id)))
            }
          >
            全选
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => onChange(new Set())}
          >
            取消全选
          </button>
        </div>
      </div>

      <div className="episode-grid">
        {episodes.map((episode) => {
          const label =
            episode.title || episode.long_title || `Episode ${episode.episode_id}`;
          return (
            <label
              className={`episode-option ${
                selectedIds.has(episode.episode_id) ? "selected" : ""
              }`}
              key={episode.episode_id}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(episode.episode_id)}
                onChange={() => toggle(episode.episode_id)}
              />
              <span className="episode-number">
                {episode.display_number ?? "SP"}
              </span>
              <span className="episode-copy">
                <strong>{label}</strong>
                <small>id {episode.episode_id}</small>
              </span>
            </label>
          );
        })}
      </div>

      {episodes.length > 0 && allSelected && (
        <p className="muted compact-note">
          当前已选择查询结果中的全部真实剧集。
        </p>
      )}
    </section>
  );
}
