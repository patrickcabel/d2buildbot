import { useEffect, useState } from "react";
import { api, AuthStatus } from "./api";
import Inventory from "./pages/Inventory";
import Builds from "./pages/Builds";
import References from "./pages/References";

type Tab = "builds" | "inventory" | "references";

export default function App() {
  const [tab, setTab] = useState<Tab>("builds");
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [manifestVersion, setManifestVersion] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  async function refresh() {
    const [authRes, manRes] = await Promise.allSettled([
      api.authStatus(),
      api.manifestStatus(),
    ]);
    if (authRes.status === "fulfilled") setAuth(authRes.value);
    else setAuth(null);
    if (manRes.status === "fulfilled") setManifestVersion(manRes.value.version);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function sync() {
    setSyncing(true);
    try {
      const res = await api.syncManifest(false);
      setManifestVersion(res.version);
    } catch (e) {
      alert("Manifest sync failed: " + (e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "builds", label: "Builds" },
    { id: "inventory", label: "Inventory" },
    { id: "references", label: "References" },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-white/10 bg-[#0b0e14]/95 sticky top-0 z-40 backdrop-blur">
        <div className="max-w-[1800px] mx-auto px-4 lg:px-6 py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="text-lg font-bold text-exotic">D2 Build Maker</h1>
          <nav className="flex gap-1 flex-wrap">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded text-sm ${
                  tab === t.id ? "bg-white/15 text-white" : "text-white/60 hover:text-white"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <button
              onClick={sync}
              disabled={syncing}
              className="px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 disabled:opacity-50"
              title={manifestVersion ? `Manifest: ${manifestVersion}` : "Manifest not synced"}
            >
              {syncing ? "Syncing…" : manifestVersion ? "Manifest ✓" : "Sync Manifest"}
            </button>
            {auth?.authenticated ? (
              <button
                onClick={async () => {
                  await api.logout();
                  refresh();
                }}
                className="px-2.5 py-1 rounded bg-white/10 hover:bg-white/20"
              >
                Logout
              </button>
            ) : (
              <a
                href={api.loginUrl()}
                className={`px-2.5 py-1 rounded ${
                  auth?.configured ? "bg-exotic text-black" : "bg-white/10 opacity-50 pointer-events-none"
                }`}
              >
                {auth?.configured ? "Login with Bungie" : "Not configured"}
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1800px] mx-auto px-4 lg:px-6 py-6">
        {auth && !auth.configured && (
          <div className="mb-4 p-3 rounded bg-yellow-500/10 border border-yellow-500/30 text-yellow-200 text-sm">
            Bungie API credentials are not configured. Fill in <code>backend/.env</code> and restart
            the backend.
          </div>
        )}
        {auth && auth.configured && !auth.authenticated && (
          <div className="mb-4 p-3 rounded bg-blue-500/10 border border-blue-500/30 text-blue-200 text-sm">
            Log in with Bungie and sync the manifest to load your inventory.
          </div>
        )}
        {tab === "builds" && <Builds authed={!!auth?.authenticated} />}
        {tab === "inventory" && <Inventory authed={!!auth?.authenticated} />}
        {tab === "references" && <References manifestReady={!!manifestVersion} />}
      </main>
    </div>
  );
}
