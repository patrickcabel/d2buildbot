import { useEffect, useMemo, useState } from "react";
import { api, Item, Profile } from "../api";

const TIER_BORDER: Record<string, string> = {
  exotic: "border-exotic",
  legendary: "border-purple-500/60",
  rare: "border-blue-400/50",
};

function ItemCard({ item }: { item: Item }) {
  return (
    <div
      className={`flex items-center gap-2 p-2 rounded bg-white/5 border ${
        TIER_BORDER[item.tier] || "border-white/10"
      }`}
      title={`${item.name} (${item.location})`}
    >
      {item.icon ? (
        <img src={item.icon} alt="" className="w-10 h-10 rounded" />
      ) : (
        <div className="w-10 h-10 rounded bg-white/10" />
      )}
      <div className="min-w-0">
        <div className="text-sm truncate">{item.name}</div>
        <div className="text-xs text-white/50 flex gap-2">
          {item.power ? <span>{item.power}</span> : null}
          {item.slot && <span>{item.slot}</span>}
          {item.ammoType !== "none" && <span>{item.ammoType}</span>}
        </div>
      </div>
    </div>
  );
}

export default function Inventory({ authed }: { authed: boolean }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<string>("all");
  const [location, setLocation] = useState<string>("all");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setProfile(await api.profile());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (authed) load();
  }, [authed]);

  const filtered = useMemo(() => {
    if (!profile) return [];
    return profile.items.filter((i) => {
      if (kind !== "all" && i.kind !== kind) return false;
      if (location !== "all" && i.location !== location) return false;
      if (search && !i.name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [profile, kind, location, search]);

  if (!authed) return <p className="text-white/60">Log in to view your inventory.</p>;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button onClick={load} className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-sm">
          {loading ? "Loading…" : "Reload"}
        </button>
        <input
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 rounded bg-white/5 border border-white/10 text-sm"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="px-2 py-1.5 rounded bg-white/5 border border-white/10 text-sm"
        >
          <option value="all">All types</option>
          <option value="weapon">Weapons</option>
          <option value="armor">Armor</option>
        </select>
        <select
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          className="px-2 py-1.5 rounded bg-white/5 border border-white/10 text-sm"
        >
          <option value="all">All locations</option>
          <option value="equipped">Equipped</option>
          <option value="character">On character</option>
          <option value="vault">Vault</option>
        </select>
        <span className="text-sm text-white/50 ml-auto">{filtered.length} items</span>
      </div>

      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      {profile && (
        <div className="flex gap-3 mb-4 flex-wrap">
          {profile.characters.map((c) => (
            <div
              key={c.characterId}
              className="px-3 py-2 rounded bg-white/5 border border-white/10 text-sm capitalize"
            >
              {c.classType} · {c.light} light
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {filtered.map((i) => (
          <ItemCard key={(i.itemInstanceId || i.itemHash) + i.location} item={i} />
        ))}
      </div>
    </div>
  );
}
