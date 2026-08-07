// Dev: same-origin `/api` via Vite proxy (avoids self-signed HTTPS fetch failures).
// OAuth login still hits the HTTPS backend directly (Bungie redirect URI).
const API_ORIGIN = "https://localhost:8000";
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    const where = BASE || "the Vite /api proxy";
    throw new Error(
      `Cannot reach API (${where}). Is the backend running on ${API_ORIGIN}? ` +
        "Restart the backend if it looks hung."
    );
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json();
}

export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  membershipId: string | null;
}

export interface Item {
  itemHash: number;
  itemInstanceId: string | null;
  name: string;
  icon: string | null;
  kind: string | null;
  slot: string | null;
  tier: string;
  isExotic: boolean;
  ammoType: string;
  classType: string;
  location: string;
  characterId: string | null;
  itemTypeName?: string | null;
  state?: number;
  isMasterwork?: boolean;
  isCrafted?: boolean;
  hasOrnament?: boolean;
  damageIcon?: string | null;
  damageName?: string | null;
  power?: number | null;
  perks?: number[] | null;
}

export interface ItemDetailPlug {
  name: string;
  icon: string | null;
  enabled: boolean;
}

export interface ItemDetail {
  itemInstanceId: string;
  itemHash: number;
  name: string;
  icon: string | null;
  hasOrnament?: boolean;
  typeName: string | null;
  flavor: string | null;
  tier: string;
  isExotic: boolean;
  isMasterwork: boolean;
  isCrafted: boolean;
  power: number | null;
  damageName: string | null;
  damageIcon: string | null;
  stats: { hash: number; name: string; value: number }[];
  socketGroups: { name: string; plugs: ItemDetailPlug[] }[];
}

export interface Character {
  characterId: string;
  classType: string;
  light: number | null;
  emblemPath: string | null;
}

export interface Profile {
  membership: { display_name?: string; bungie_global_display_name?: string };
  characters: Character[];
  items: Item[];
}

export interface ReferenceSummary {
  id: number;
  source_type: string;
  url: string;
  title: string | null;
  status: string;
  error: string | null;
  fetched_at: number | null;
  fact_count: number;
}

export interface Fact {
  entity_type: string;
  manifest_hash: number;
  name: string;
  mention_count: number;
  snippet: string | null;
}

export interface ReferenceDetail extends ReferenceSummary {
  facts: Fact[];
  raw_meta?: any;
}

export interface BuildItem extends Item {
  reason?: string;
  wishlist?: { is_wishlisted: boolean; matched_perks: number; notes: string | null };
}

export interface NamedRec {
  name: string;
  hash: number | null;
  sources: number;
  owned: boolean | null;
  from: string;
}

export interface BuildRequest {
  query: string;
  classType?: string | null;
  characterId?: string | null;
  statPriority?: string[];
  includeVault?: boolean;
}

export interface Build {
  query: string;
  matched: boolean;
  exotic: { name: string; hash: number; type: string; owned: boolean } | null;
  classType: string;
  characterId?: string | null;
  subclass: string | null;
  weapons: Record<string, BuildItem | null>;
  armor: Record<string, BuildItem | null>;
  aspects: NamedRec[];
  fragments: NamedRec[];
  mods: NamedRec[];
  statPriority: string[];
  availableStats?: string[];
  rationale: string;
  references: { url: string; title: string; type: string }[];
  notes: string | null;
  dim: { search: string; url: string } | null;
}

export type ArmorStatKey =
  | "Weapons"
  | "Health"
  | "Class"
  | "Grenade"
  | "Super"
  | "Melee";

export interface ExoticArmorOption {
  hash: number;
  name: string;
  icon: string | null;
  classType: string;
  slot: string | null;
  owned: boolean;
}

export interface SubclassPlug {
  hash: number;
  name: string;
  icon: string | null;
  element: string | null;
  type: "aspect" | "fragment";
  bonus: Record<string, number>;
  hasStatBonus?: boolean;
}

export interface SubclassOptions {
  elements: string[];
  aspects: SubclassPlug[];
  fragments: SubclassPlug[];
}

export interface ArmorSolveRequest {
  classType: string;
  characterId?: string | null;
  includeVault?: boolean;
  exoticHash?: number | null;
  targets: Partial<Record<ArmorStatKey | string, number>>;
  fragmentHashes?: number[];
  aspectHashes?: number[];
  maxResults?: number;
}

export interface ArmorSolvePiece {
  itemHash: number;
  itemInstanceId: string | null;
  name: string;
  icon: string | null;
  slot: string;
  tier: string;
  isExotic: boolean;
  power: number | null;
  location: string;
  stats: Record<string, number>;
}

export interface ArmorSolveSet {
  score: number;
  tiersMet: number;
  totals: Record<string, number>;
  under: Record<string, number>;
  over: Record<string, number>;
  armor: Record<string, ArmorSolvePiece>;
  dim: { search: string; url: string } | null;
}

export interface ArmorSolveResult {
  ok: boolean;
  error: string | null;
  classType?: string;
  targets?: Record<string, number>;
  fragmentBonus?: Record<string, number>;
  effectiveTargets?: Record<string, number>;
  selectedPlugs?: { hash: number; name: string; icon: string | null; bonus: Record<string, number> }[];
  searchedCombos?: number;
  results: ArmorSolveSet[];
}

export interface ArmorStatCaps {
  ok: boolean;
  error: string | null;
  absoluteMax: Record<string, number>;
  max: Record<string, number>;
  fragmentBonus?: Record<string, number>;
  targets?: Record<string, number>;
}

export const api = {
  authStatus: () => req<AuthStatus>("/api/auth/status"),
  loginUrl: () => `${API_ORIGIN}/api/auth/login`,
  logout: () => req("/api/auth/logout", { method: "POST" }),
  manifestStatus: () => req<{ version: string | null }>("/api/manifest/status"),
  syncManifest: (force = false) =>
    req<{ status: string; version: string }>(`/api/manifest/sync?force=${force}`, {
      method: "POST",
    }),
  profile: () => req<Profile>("/api/profile"),
  characters: () => req<{ characters: Character[] }>("/api/profile/characters"),
  itemDetail: (instanceId: string, itemHash?: number) =>
    req<ItemDetail>(
      `/api/profile/item/${instanceId}${itemHash != null ? `?itemHash=${itemHash}` : ""}`
    ),
  listReferences: () => req<{ references: ReferenceSummary[] }>("/api/references"),
  getReference: (id: number) => req<ReferenceDetail>(`/api/references/${id}`),
  addReference: (url: string) =>
    req<ReferenceDetail>("/api/references", { method: "POST", body: JSON.stringify({ url }) }),
  refreshReference: (id: number) =>
    req<ReferenceDetail>(`/api/references/${id}/refresh`, { method: "POST" }),
  deleteReference: (id: number) =>
    req(`/api/references/${id}`, { method: "DELETE" }),
  createBuild: (body: BuildRequest) =>
    req<Build>("/api/builds", { method: "POST", body: JSON.stringify(body) }),
  listExotics: (classType: string, characterId?: string | null, includeVault = true) => {
    const q = new URLSearchParams({ classType, includeVault: String(includeVault) });
    if (characterId) q.set("characterId", characterId);
    return req<{ classType: string; exotics: ExoticArmorOption[] }>(`/api/builds/exotics?${q}`);
  },
  subclassOptions: (classType: string, element?: string | null) => {
    const q = new URLSearchParams({ classType });
    if (element) q.set("element", element);
    return req<SubclassOptions>(`/api/builds/subclass-options?${q}`);
  },
  solveArmor: (body: ArmorSolveRequest) =>
    req<ArmorSolveResult>("/api/builds/solve", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  armorStatCaps: (body: ArmorSolveRequest) =>
    req<ArmorStatCaps>("/api/builds/stat-caps", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  moveItem: (body: { itemInstanceId: string; toStore: string }) =>
    req<{ ok: boolean; message: string }>("/api/actions/move", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  equipItem: (body: { itemInstanceId: string; characterId: string }) =>
    req<{ ok: boolean; message: string }>("/api/actions/equip", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  equipLoadout: (body: { characterId: string; itemInstanceIds: string[] }) =>
    req<{ ok: boolean; message: string; equipped: string[]; errors: string[] }>(
      "/api/actions/equip-loadout",
      { method: "POST", body: JSON.stringify(body) }
    ),
  wishlistStatus: () =>
    req<{ items: number; rolls: number; files: string[] }>("/api/wishlists/status"),
  downloadVoltron: () =>
    req<{ ok: boolean; bytes: number; items: number; rolls: number }>(
      "/api/wishlists/download-voltron",
      { method: "POST" }
    ),
};
