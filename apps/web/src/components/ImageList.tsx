import { useMemo, useState } from "react";
import { ImagePlus, Images, Search, Trash2, X } from "lucide-react";
import type { EditorImage } from "../types";

interface Props {
  images: EditorImage[];
  currentId: string | null;
  resultCounts: Record<string, number>;
  onSelect(id: string): void;
  onRemove(id: string): void;
  onImport(): void;
}

type Filter = "all" | "done" | "todo";

export function ImageList({ images, currentId, resultCounts, onSelect, onRemove, onImport }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return images.filter((image) => {
      if (q && !image.name.toLowerCase().includes(q) && !image.path.toLowerCase().includes(q)) {
        return false;
      }
      const done = (resultCounts[image.id] ?? 0) > 0;
      if (filter === "done") return done;
      if (filter === "todo") return !done;
      return true;
    });
  }, [images, query, filter, resultCounts]);

  return (
    <>
      <div className="panel-head">
        <span className="panel-title">图片</span>
        <span className="panel-count">{images.length}</span>
        <span className="spacer" />
        <button className="icon-btn" onClick={onImport} title="导入图片">
          <ImagePlus size={15} />
        </button>
      </div>

      <div className="search-wrap">
        <div className="search-box">
          <Search size={13} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索文件名…"
            spellCheck={false}
          />
          {query && (
            <button
              className="mini-btn"
              style={{ border: 0, background: "transparent", color: "inherit", display: "grid" }}
              onClick={() => setQuery("")}
              title="清空"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="filter-row">
        <button className={`chip ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
          全部
        </button>
        <button className={`chip ${filter === "todo" ? "active" : ""}`} onClick={() => setFilter("todo")}>
          未分割
        </button>
        <button className={`chip ${filter === "done" ? "active" : ""}`} onClick={() => setFilter("done")}>
          已分割
        </button>
      </div>

      <div className="panel-scroll">
        {visible.length === 0 ? (
          <div className="empty-note">
            {images.length === 0 ? "还没有图片。\n导入一组图片开始。" : "没有匹配的图片。"}
          </div>
        ) : (
          <div className="image-list">
            {visible.map((image) => {
              const done = (resultCounts[image.id] ?? 0) > 0;
              const active = image.id === currentId;
              return (
                <div
                  key={image.id}
                  className={`image-item ${active ? "active" : ""}`}
                  onClick={() => onSelect(image.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(image.id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  title={image.path}
                >
                  <span className="image-thumb">
                    {image.url ? <img src={image.url} alt="" draggable={false} /> : <Images size={14} />}
                  </span>
                  <span className="image-meta">
                    <span className="image-name">{image.name}</span>
                    <span className="image-sub">
                      {image.width && image.height ? `${image.width}×${image.height}` : "加载中…"}
                      {done ? ` · ${resultCounts[image.id]} mask` : ""}
                    </span>
                  </span>
                  <span
                    className={`status-dot ${
                      image.status === "error" ? "error" : done ? "done" : ""
                    }`}
                  />
                  <button
                    type="button"
                    className="image-remove"
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemove(image.id);
                    }}
                    title="移除"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="sidebar-foot">
        <button className="btn btn-block" onClick={onImport}>
          <ImagePlus size={14} />
          导入图片
        </button>
      </div>
    </>
  );
}
