import { useEffect, useMemo, useState } from "react";
import { api, Build, BuildItem, Character, NamedRec } from "../api";
import ArmorPicker from "./ArmorPicker";

const CLASSES = ["titan", "hunter", "warlock"] as const;

const CLASS_ICON_PATHS: Record<string, string> = {
  titan:
    "m14.839 15.979-13.178-7.609v15.218zm2.322 0 13.178 7.609v-15.218zm5.485-12.175-6.589-3.804-13.178 7.609 13.178 7.609 13.179-7.609zm0 16.784-6.589-3.805-13.178 7.609 13.178 7.608 13.179-7.608-6.59-3.805z",
  hunter:
    "m9.055 10.446 6.945-.023-6.948 10.451 6.948-.024-7.412 11.15h-7.045l7.036-10.428h-7.036l7.032-10.422h-7.032l7.507-11.126 6.95-.024zm13.89 0-6.945-10.446 6.95.024 7.507 11.126h-7.032l7.032 10.422h-7.036l7.036 10.428h-7.045l-7.412-11.15 6.948.024-6.948-10.451z",
  warlock:
    "m5.442 23.986 7.255-11.65-2.71-4.322-9.987 15.972zm5.986 0 4.28-6.849-2.717-4.333-6.992 11.182zm7.83-11.611 7.316 11.611h5.426l-10.015-15.972zm-7.26 11.611h8.004l-4.008-6.392zm6.991-11.182-2.703 4.324 4.302 6.858h5.413zm-5.707-.459 2.71-4.331 2.71 4.331-2.703 4.326z",
};

function ClassIcon({ classType, className }: { classType: string; className?: string }) {
  const d = CLASS_ICON_PATHS[classType];
  if (!d) return null;
  return (
    <svg viewBox="0 0 32 32" fill="currentColor" className={`block shrink-0 ${className || ""}`} aria-hidden>
      <path d={d} />
    </svg>
  );
}

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
              {item.power != null && (
                <span className="text-white/40 font-normal ml-1.5 tabular-nums">{item.power}</span>
              )}
            </div>
            <div className="text-xs text-white/50 truncate">
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
  const [equipping, setEquipping] = useState(false);
  const [equipMsg, setEquipMsg] = useState<string | null>(null);
  const [wishlist, setWishlist] = useState<{ items: number; rolls: number } | null>(null);
  const [wlBusy, setWlBusy] = useState(false);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState<string>("");
  const [classType, setClassType] = useState<string>("");
  const [includeVault, setIncludeVault] = useState(true);

  const selectedChar = useMemo(
    () => characters.find((c) => c.characterId === characterId) || null,
    [characters, characterId]
  );

  useEffect(() => {
    if (selectedChar?.classType && selectedChar.classType !== "unknown") {
      setClassType(selectedChar.classType);
    }
  }, [selectedChar]);

  async function loadWishlist() {
    try {
      setWishlist(await api.wishlistStatus());
    } catch {
      /* ignore */
    }
  }

  async function loadCharacters() {
    if (!authed) {
      setCharacters([]);
      return;
    }
    try {
      const res = await api.characters();
      setCharacters(res.characters || []);
    } catch {
      setCharacters([]);
    }
  }

  useEffect(() => {
    loadWishlist();
  }, []);

  useEffect(() => {
    loadCharacters();
  }, [authed]);

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

  async function equipBuildArmor() {
    if (!build || !characterId) {
      setEquipMsg("Pick a character to equip this armor.");
      return;
    }
    const ids = ["helmet", "gauntlets", "chest", "legs", "class"]
      .map((slot) => build.armor[slot]?.itemInstanceId)
      .filter((id): id is string => !!id);
    if (!ids.length) {
      setEquipMsg("No armor instance ids on this build.");
      return;
    }
    setEquipping(true);
    setEquipMsg(null);
    try {
      const res = await api.equipLoadout({ characterId, itemInstanceIds: ids });
      setEquipMsg(res.message);
    } catch (e) {
      setEquipMsg((e as Error).message);
    } finally {
      setEquipping(false);
    }
  }

  async function submit() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setBuild(
        await api.createBuild({
          query,
          classType: classType || null,
          characterId: characterId || null,
          includeVault,
        })
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const classLocked = !!selectedChar;

  return (
    <div className="space-y-10">
      {!authed && (
        <p className="text-white/60">Log in with Bungie to optimize armor from your inventory.</p>
      )}

      <ArmorPicker authed={authed} characters={characters} />

      <div className="border-t border-white/10 pt-8">
        <div className="flex items-center gap-2 mb-3 text-xs text-white/50">
          <span className="text-sm font-medium text-white/80 mr-2">Quick exotic build</span>
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

        <div className="grid sm:grid-cols-2 gap-3 mb-3 p-3 rounded border border-white/10 bg-white/[0.03]">
          <div>
            <label className="block text-[11px] uppercase tracking-wide text-white/40 mb-1">
              Character
            </label>
            <select
              value={characterId}
              onChange={(e) => setCharacterId(e.target.value)}
              disabled={!authed}
              className="w-full px-3 py-2 rounded bg-white/5 border border-white/10 text-sm disabled:opacity-50"
            >
              <option value="">All characters</option>
              {characters.map((c) => (
                <option key={c.characterId} value={c.characterId}>
                  {c.classType.charAt(0).toUpperCase() + c.classType.slice(1)}
                  {c.light != null ? ` · ${c.light}` : ""}
                </option>
              ))}
            </select>
            {characterId && (
              <label className="mt-1.5 flex items-center gap-2 text-xs text-white/50">
                <input
                  type="checkbox"
                  checked={includeVault}
                  onChange={(e) => setIncludeVault(e.target.checked)}
                />
                Include vault
              </label>
            )}
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wide text-white/40 mb-1">
              Class {classLocked ? "(from character)" : ""}
            </label>
            <div className="flex gap-1.5">
              {CLASSES.map((cl) => {
                const active = classType === cl;
                return (
                  <button
                    key={cl}
                    type="button"
                    disabled={classLocked && classType !== cl}
                    onClick={() => setClassType(active && !classLocked ? "" : cl)}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded border text-sm capitalize ${
                      active
                        ? "bg-exotic/20 border-exotic/50 text-exotic"
                        : "bg-white/5 border-white/10 text-white/70 hover:bg-white/10"
                    } disabled:opacity-40`}
                  >
                    <ClassIcon classType={cl} className="w-3.5 h-3.5" />
                    {cl}
                  </button>
                );
              })}
            </div>
          </div>
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
            className="px-5 py-2.5 rounded bg-white/15 hover:bg-white/25 font-medium disabled:opacity-50"
          >
            {loading ? "Building…" : "Generate"}
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        {build && (
          <div className="space-y-5">
            <div className="p-4 rounded bg-white/5 border border-white/10">
              <div className="flex items-center gap-3 mb-2">
                <h2 className="text-xl font-bold text-exotic">
                  {build.exotic ? build.exotic.name : "No exotic matched"}
                </h2>
                {build.exotic && <OwnedBadge owned={build.exotic.owned} />}
                <span className="text-sm text-white/50 capitalize ml-auto flex items-center gap-1.5">
                  {build.classType !== "any" && (
                    <ClassIcon classType={build.classType} className="w-3.5 h-3.5 opacity-70" />
                  )}
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
              <div className="mt-3 flex flex-wrap items-center gap-2">
                  {build.dim && (
                    <>
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
                    </>
                  )}
                  <button
                    type="button"
                    onClick={equipBuildArmor}
                    disabled={equipping || !characterId || !authed}
                    className="px-3 py-1.5 rounded bg-exotic/90 text-black text-sm font-medium disabled:opacity-40"
                    title={
                      characterId
                        ? "Transfer + equip this build's armor on the selected character"
                        : "Select a character to equip"
                    }
                  >
                    {equipping ? "Equipping…" : "Equip armor"}
                  </button>
                </div>
              {equipMsg && (
                <p className="text-xs text-white/60 mt-2">{equipMsg}</p>
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
    </div>
  );
}
