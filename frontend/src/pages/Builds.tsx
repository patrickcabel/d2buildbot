import { useEffect, useState } from "react";
import { api, Build, BuildItem, NamedRec } from "../api";

function OwnedBadge({ owned }: { owned: boolean | null | undefined }) {
  if (owned === null || owned === undefined) return null;
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded ${
        owned ? "bg-green-500/20 text-green-300" : "bg-red-500/20 text-red-300"
      }`}
    >
      {owned ? "owned" : "missing"}
    </span>
  );
}

function SlotRow({ label, item }: { label: string; item: BuildItem | null }) {
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-white/5">
      <span className="w-20 text-xs uppercase text-white/40">{label}</span>
      {item ? (
        <>
          {item.icon && <img src={item.icon} alt="" className="w-8 h-8 rounded" />}
          <div className="min-w-0">
            <div className={`text-sm truncate ${item.isExotic ? "text-exotic" : ""}`}>
              {item.name}
            </div>
            <div className="text-xs text-white/50">
              {item.reason}
              {item.wishlist?.is_wishlisted && " · god roll"}
            </div>
          </div>
        </>
      ) : (
        <span className="text-sm text-white/40">Nothing suitable in inventory</span>
      )}
    </div>
  );
}

function RecList({ title, items }: { title: string; items: NamedRec[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="text-xs uppercase text-white/40 mb-1">{title}</h4>
      <div className="flex flex-wrap gap-1.5">
        {items.map((r, i) => (
          <span
            key={i}
            className="text-xs px-2 py-1 rounded bg-white/5 border border-white/10 flex items-center gap-1.5"
            title={r.from === "references" ? `${r.sources} source(s)` : "curated"}
          >
            {r.name}
            <OwnedBadge owned={r.owned} />
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Builds({ authed }: { authed: boolean }) {
  const [query, setQuery] = useState("");
  const [build, setBuild] = useState<Build | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [wishlist, setWishlist] = useState<{ items: number; rolls: number } | null>(null);
  const [wlBusy, setWlBusy] = useState(false);

  async function loadWishlist() {
    try {
      setWishlist(await api.wishlistStatus());
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadWishlist();
  }, []);

  async function downloadVoltron() {
    setWlBusy(true);
    try {
      const res = await api.downloadVoltron();
      setWishlist({ items: res.items, rolls: res.rolls });
    } catch (e) {
      alert("Download failed: " + (e as Error).message);
    } finally {
      setWlBusy(false);
    }
  }

  function copySearch() {
    if (!build?.dim) return;
    navigator.clipboard.writeText(build.dim.search);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function submit() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setBuild(await api.createBuild(query));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 text-xs text-white/50">
        <span>
          Wishlist:{" "}
          {wishlist && wishlist.rolls > 0
            ? `${wishlist.rolls} rolls across ${wishlist.items} items`
            : "none loaded"}
        </span>
        {(!wishlist || wishlist.rolls === 0) && (
          <button
            onClick={downloadVoltron}
            disabled={wlBusy}
            className="px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 disabled:opacity-50"
          >
            {wlBusy ? "Downloading…" : "Download voltron.txt god rolls"}
          </button>
        )}
      </div>
      <div className="flex gap-2 mb-6">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder='e.g. "I want a Telesto build"'
          className="flex-1 px-4 py-2.5 rounded bg-white/5 border border-white/10"
        />
        <button
          onClick={submit}
          disabled={loading || !authed}
          className="px-5 py-2.5 rounded bg-exotic text-black font-medium disabled:opacity-50"
        >
          {loading ? "Building…" : "Generate"}
        </button>
      </div>

      {!authed && <p className="text-white/60">Log in with Bungie to generate builds from your inventory.</p>}
      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      {build && (
        <div className="space-y-5">
          <div className="p-4 rounded bg-white/5 border border-white/10">
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-xl font-bold text-exotic">
                {build.exotic ? build.exotic.name : "No exotic matched"}
              </h2>
              {build.exotic && <OwnedBadge owned={build.exotic.owned} />}
              <span className="text-sm text-white/50 capitalize ml-auto">
                {build.classType} · {build.subclass || "any"} subclass
              </span>
            </div>
            <p className="text-sm text-white/70">{build.rationale}</p>
            {build.notes && <p className="text-sm text-white/50 mt-2 italic">{build.notes}</p>}
            {build.statPriority.length > 0 && (
              <p className="text-xs text-white/50 mt-2">
                Stat priority: {build.statPriority.join(" › ")}
              </p>
            )}
            {build.dim && (
              <div className="mt-3 flex items-center gap-2">
                <a
                  href={build.dim.url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded bg-blue-500/20 hover:bg-blue-500/30 text-blue-200 text-sm"
                >
                  Open in DIM
                </a>
                <button
                  onClick={copySearch}
                  className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-sm"
                  title={build.dim.search}
                >
                  {copied ? "Copied!" : "Copy DIM search"}
                </button>
              </div>
            )}
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <div className="p-4 rounded bg-white/5 border border-white/10">
              <h3 className="font-semibold mb-2">Weapons</h3>
              {["kinetic", "energy", "power"].map((s) => (
                <SlotRow key={s} label={s} item={build.weapons[s]} />
              ))}
            </div>
            <div className="p-4 rounded bg-white/5 border border-white/10">
              <h3 className="font-semibold mb-2">Armor</h3>
              {["helmet", "gauntlets", "chest", "legs", "class"].map((s) => (
                <SlotRow key={s} label={s} item={build.armor[s]} />
              ))}
            </div>
          </div>

          <div className="p-4 rounded bg-white/5 border border-white/10 space-y-4">
            <RecList title="Aspects" items={build.aspects} />
            <RecList title="Fragments" items={build.fragments} />
            <RecList title="Mods" items={build.mods} />
          </div>

          {build.references.length > 0 && (
            <div className="p-4 rounded bg-white/5 border border-white/10">
              <h3 className="font-semibold mb-2">Sources referenced</h3>
              <ul className="text-sm space-y-1">
                {build.references.map((r, i) => (
                  <li key={i}>
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-300 hover:underline"
                    >
                      [{r.type}] {r.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
