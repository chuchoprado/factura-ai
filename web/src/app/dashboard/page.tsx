"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, extractPdf, getHistory, getMe, getPortalUrl } from "@/lib/api";

type UserInfo = { email: string; plan: string; plan_label: string; pdfs_used: number; pdfs_limit: number };
type Conversion = { id: string; filename: string; pages: number; completas: number; verificar: number; pendientes: number; tipo: string; created_at: string };

export default function DashboardPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);

  const [user, setUser] = useState<UserInfo | null>(null);
  const [history, setHistory] = useState<Conversion[]>([]);
  const [tipo, setTipo] = useState<"autonomo" | "gastos_pf">("autonomo");
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  // Cargar usuario e historial al entrar
  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => router.push("/login"));
    getHistory()
      .then((d) => setHistory(d.conversions || []))
      .catch(() => {});
  }, [router]);

  const processFile = useCallback(async (file: File) => {
    if (!file || file.type !== "application/pdf") {
      setError("Por favor selecciona un archivo PDF válido.");
      return;
    }
    setError(""); setProcessing(true); setProgress("Iniciando...");
    try {
      const blob = await extractPdf(file, tipo, setProgress);

      // Descargar Excel automáticamente — el <a> debe estar en el DOM para funcionar
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      const date = new Date().toLocaleDateString("es-ES").replace(/\//g, "-");
      a.href     = url;
      a.download = `Facturas_${tipo}_${date}.xlsx`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 1500);

      setProgress("✅ Excel descargado");
      // Refrescar usuario e historial
      getMe().then(setUser).catch(() => {});
      getHistory().then((d) => setHistory(d.conversions || [])).catch(() => {});
    } catch (err: any) {
      setError(err.message || "Error procesando el PDF");
    } finally {
      setProcessing(false);
      setTimeout(() => setProgress(""), 4000);
    }
  }, [tipo]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  const usedPct = user ? Math.min(100, Math.round((user.pdfs_used / user.pdfs_limit) * 100)) : 0;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* HEADER */}
      <header className="gradient-brand text-white px-6 py-4 flex items-center justify-between shadow-md">
        <span className="text-xl font-bold">FacturAI</span>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-blue-200">{user?.email}</span>
          <button
            onClick={() => { clearToken(); router.push("/login"); }}
            className="border border-white/30 px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >Salir</button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* PLAN */}
        {user && (
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex flex-wrap items-center gap-4 justify-between">
            <div>
              <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">Plan activo</p>
              <p className="font-bold text-[#1F3864] text-lg">{user.plan_label}</p>
            </div>
            <div className="flex-1 min-w-[180px]">
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>PDFs usados este mes</span>
                <span className="font-semibold">{user.pdfs_used} / {user.pdfs_limit === 999999 ? "∞" : user.pdfs_limit}</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${usedPct > 80 ? "bg-red-400" : "bg-[#4F7FE8]"}`} style={{ width: `${usedPct}%` }} />
              </div>
            </div>
            <div className="flex gap-2">
              {user.plan === "free" && (
                <button onClick={() => router.push("/pricing")} className="gradient-brand text-white px-4 py-2 rounded-xl text-sm font-semibold hover:opacity-90 transition-opacity">
                  Actualizar plan
                </button>
              )}
              {user.plan !== "free" && (
                <button onClick={async () => { const url = await getPortalUrl(); window.open(url, "_blank"); }} className="border border-slate-200 px-4 py-2 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors">
                  Gestionar suscripción
                </button>
              )}
            </div>
          </div>
        )}

        {/* SELECTOR DE TIPO */}
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <p className="text-sm font-semibold text-slate-700 mb-3">Tipo de documento</p>
          <div className="flex gap-3">
            {[{ val: "autonomo", label: "🧾 Autónomos", desc: "Facturas emitidas/recibidas" },
              { val: "gastos_pf", label: "💸 Gastos PF", desc: "Tickets y gastos personales" }].map(({ val, label, desc }) => (
              <button
                key={val}
                onClick={() => setTipo(val as "autonomo" | "gastos_pf")}
                className={`flex-1 p-4 rounded-xl border-2 text-left transition-all ${tipo === val ? "border-[#4F7FE8] bg-blue-50" : "border-slate-200 hover:border-slate-300"}`}
              >
                <p className="font-semibold text-sm text-slate-800">{label}</p>
                <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* ZONA DE UPLOAD */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !processing && fileRef.current?.click()}
          className={`bg-white rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer transition-all shadow-sm
            ${dragging ? "border-[#4F7FE8] bg-blue-50 scale-[1.01]" : "border-slate-200 hover:border-[#4F7FE8] hover:bg-slate-50"}
            ${processing ? "pointer-events-none opacity-70" : ""}`}
        >
          <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) processFile(f); }} />
          {processing ? (
            <div className="space-y-3">
              <div className="text-4xl animate-bounce">⚙️</div>
              <p className="font-semibold text-[#1F3864]">Procesando...</p>
              <p className="text-slate-400 text-sm">{progress}</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-5xl">📄</div>
              <p className="font-semibold text-slate-700 text-lg">Arrastra tu PDF aquí</p>
              <p className="text-slate-400 text-sm">o haz clic para seleccionar</p>
              <p className="text-xs text-slate-300">Solo archivos PDF · Máx. páginas según tu plan</p>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-5 py-4 flex items-start gap-3">
            <span className="text-lg">⚠️</span>
            <div>
              <p className="font-semibold">Error</p>
              <p>{error}</p>
              {error.includes("límite") && (
                <button onClick={() => router.push("/pricing")} className="text-[#4F7FE8] underline mt-1">
                  Ver planes disponibles
                </button>
              )}
            </div>
          </div>
        )}

        {/* HISTORIAL */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="font-bold text-slate-800">Historial de conversiones</h2>
          </div>
          {history.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <div className="text-4xl mb-3">📂</div>
              <p className="text-sm">Aún no has procesado ningún PDF</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                  <tr>
                    {["Archivo", "Fecha", "Tipo", "Págs.", "✅", "⚠️", "❌", "Acción"].map((h) => (
                      <th key={h} className="px-4 py-3 text-left font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {history.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-700 truncate max-w-[160px]" title={c.filename}>{c.filename}</td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{new Date(c.created_at).toLocaleDateString("es-ES")}</td>
                      <td className="px-4 py-3"><span className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full">{c.tipo}</span></td>
                      <td className="px-4 py-3 text-slate-600">{c.pages}</td>
                      <td className="px-4 py-3 text-green-600 font-semibold">{c.completas}</td>
                      <td className="px-4 py-3 text-amber-500 font-semibold">{c.verificar}</td>
                      <td className="px-4 py-3 text-red-500 font-semibold">{c.pendientes}</td>
                      <td className="px-4 py-3">
                        <label className="cursor-pointer bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-600 text-xs px-3 py-1.5 rounded-lg transition-colors font-medium whitespace-nowrap">
                          ↩ Re-procesar
                          <input type="file" accept=".pdf" className="hidden"
                            onChange={(e) => { const f = e.target.files?.[0]; if (f) { e.target.value = ""; processFile(f); } }} />
                        </label>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
