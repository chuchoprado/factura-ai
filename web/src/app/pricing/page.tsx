"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCheckoutUrl, getToken } from "@/lib/api";
import { useState } from "react";

const plans = [
  {
    id: "free", name: "Free", price: "0€", period: "/mes",
    features: ["3 PDFs por mes", "Máx. 10 páginas por PDF", "7 días de historial", "Soporte por email"],
    cta: "Empezar gratis", highlight: false,
  },
  {
    id: "basic", name: "Básico", price: "9€", period: "/mes",
    features: ["30 PDFs por mes", "Máx. 50 páginas por PDF", "30 días de historial", "Soporte prioritario"],
    cta: "Suscribirme al Básico", highlight: true,
  },
  {
    id: "pro", name: "Pro", price: "29€", period: "/mes",
    features: ["PDFs ilimitados", "Máx. 200 páginas por PDF", "1 año de historial", "Soporte dedicado"],
    cta: "Suscribirme al Pro", highlight: false,
  },
];

export default function PricingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handlePlan = async (planId: string) => {
    if (planId === "free") { router.push("/register"); return; }
    const token = getToken();
    if (!token) { router.push(`/register?plan=${planId}`); return; }

    setLoading(planId); setError("");
    try {
      const url = await getCheckoutUrl(planId);
      window.location.href = url;
    } catch (err: any) {
      setError(err.message || "Error al procesar el pago");
      setLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="gradient-brand text-white px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold">FacturAI</Link>
        <Link href="/dashboard" className="text-sm hover:text-blue-200 transition-colors">Mi cuenta</Link>
      </nav>

      <section className="py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h1 className="text-3xl font-extrabold text-slate-800 mb-3">Planes y precios</h1>
            <p className="text-slate-500">Sin compromisos. Cancela cuando quieras.</p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-5 py-4 mb-8 text-center">
              {error}
            </div>
          )}

          <div className="grid md:grid-cols-3 gap-6">
            {plans.map(({ id, name, price, period, features, cta, highlight }) => (
              <div key={id} className={`bg-white rounded-2xl p-8 border-2 flex flex-col relative ${highlight ? "border-[#4F7FE8] shadow-xl" : "border-slate-200 shadow-sm"}`}>
                {highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 gradient-brand text-white text-xs font-bold px-4 py-1 rounded-full">
                    MÁS POPULAR
                  </div>
                )}
                <h3 className="text-xl font-bold text-slate-800 mb-1">{name}</h3>
                <div className="flex items-end gap-1 mb-6">
                  <span className="text-4xl font-extrabold text-[#1F3864]">{price}</span>
                  <span className="text-slate-400 mb-1">{period}</span>
                </div>
                <ul className="space-y-2 mb-8 flex-1">
                  {features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
                      <span className="text-green-500 font-bold">✓</span>{f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handlePlan(id)}
                  disabled={loading === id}
                  className={`w-full py-3 rounded-xl font-semibold transition-all disabled:opacity-60 ${highlight ? "gradient-brand text-white hover:opacity-90" : "border-2 border-[#1F3864] text-[#1F3864] hover:bg-slate-50"}`}
                >
                  {loading === id ? "Redirigiendo..." : cta}
                </button>
              </div>
            ))}
          </div>

          <p className="text-center text-xs text-slate-400 mt-8">
            Precios en EUR. IVA no incluido. Pago procesado de forma segura por Stripe.
          </p>
        </div>
      </section>
    </div>
  );
}
