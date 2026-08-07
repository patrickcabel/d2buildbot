import { useEffect, useState } from "react";
import { api, ReferenceDetail, ReferenceSummary } from "../api";

const STATUS_COLOR: Record<string, string> = {
  ready: "text-green-300",
  error: "text-red-300",
  pending: "text-yellow-300",
};

export default function References({ manifestReady }: { manifestReady: boolean }) {
  const [refs, setRefs] = useState<ReferenceSummary[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReferenceDetail | null>(null);

  async function load() {
    try {
      setRefs((await api.listReferences()).references);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add() {
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await api.addReference(url.trim());
      setUrl("");
      setSelected(detail);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function refresh(id: number) {
    setBusy(true);
    try {
      const detail = await api.refreshReference(id);
      setSelected(detail);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await api.deleteReference(id);
    if (selected?.id === id) setSelected(null);
    await load();
  }

  async function open(id: number) {
    setSelected(await api.getReference(id));
  }

  return (
    <div>
      <p className="text-sm text-white/60 mb-3">
        Add YouTube videos (captions + comments), DIM loadout links, or build guide web pages. They
        are fetched once and saved locally, so build queries never need to search the internet.
      </p>
      {!manifestReady && (
        <p className="text-yellow-300 text-sm mb-3">Sync the manifest first to enable ingestion.</p>
      )}
      <div className="flex gap-2 mb-4">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="https://youtube.com/watch?v=… or https://dim.gg/… or a guide URL"
          className="flex-1 px-3 py-2 rounded bg-white/5 border border-white/10 text-sm"
        />
        <button
          onClick={add}
          disabled={busy || !manifestReady}
          className="px-4 py-2 rounded bg-exotic text-black font-medium disabled:opacity-50"
        >
          {busy ? "Ingesting…" : "Ingest"}
        </button>
      </div>

      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      <div className="grid md:grid-cols-2 gap-5">
        <div className="space-y-2">
          {refs.map((r) => (
            <div
              key={r.id}
              className="p-3 rounded bg-white/5 border border-white/10 cursor-pointer hover:bg-white/10"
              onClick={() => open(r.id)}
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-white/10">
                  {r.source_type}
                </span>
                <span className={`text-xs ${STATUS_COLOR[r.status] || ""}`}>{r.status}</span>
                <span className="text-xs text-white/40 ml-auto">{r.fact_count} facts</span>
              </div>
              <div className="text-sm mt-1 truncate">{r.title || r.url}</div>
              {r.error && <div className="text-xs text-red-300 mt-1">{r.error}</div>}
              <div className="flex gap-2 mt-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    refresh(r.id);
                  }}
                  className="text-xs px-2 py-0.5 rounded bg-white/10 hover:bg-white/20"
                >
                  Refresh
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(r.id);
                  }}
                  className="text-xs px-2 py-0.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-200"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
          {refs.length === 0 && <p className="text-white/40 text-sm">No references yet.</p>}
        </div>

        <div>
          {selected ? (
            <div className="p-4 rounded bg-white/5 border border-white/10">
              <a
                href={selected.url}
                target="_blank"
                rel="noreferrer"
                className="text-blue-300 hover:underline text-sm break-all"
              >
                {selected.title || selected.url}
              </a>
              <h4 className="text-xs uppercase text-white/40 mt-3 mb-2">
                Extracted items ({selected.facts.length})
              </h4>
              <div className="space-y-1 max-h-[60vh] overflow-auto">
                {selected.facts.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className="text-[10px] uppercase text-white/40 w-16">{f.entity_type}</span>
                    <span className="flex-1">{f.name}</span>
                    <span className="text-xs text-white/40">×{f.mention_count}</span>
                  </div>
                ))}
                {selected.facts.length === 0 && (
                  <p className="text-white/40 text-sm">No Destiny items detected in this source.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-white/40 text-sm">Select a reference to see what was extracted.</p>
          )}
        </div>
      </div>
    </div>
  );
}
