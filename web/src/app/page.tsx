"use client";
import Link from "next/link";

const features = [
  { icon: "🤖", title: "IA avanzada", desc: "Claude Vision analiza cada página y extrae fecha, total, IVA y base imponible." },
  { icon: "⚡", title: "En segundos", desc: "Un PDF de 30 facturas procesado en menos de 2 minutos." },
  { icon: "📊", title: "Excel perfecto", desc: "Hoja formateada con colores por estado, filtros y hoja de resumen automática." },
  { icon: "🔒", title: "100% seguro", desc: "Los PDFs se eliminan tras el procesado. Tus datos nunca se almacenan." },
  { icon: "🧾", title: "Autónomos", desc: "Optimizado para facturas de autónomos: IVA 21%, base, cuota y numeración." },
  { icon: "💸", title: "Gastos PF", desc: "También procesa tickets y gastos personales para declaración de IRPF." },
];

const plans = [
  { name: "Free", price: "0€", period: "/mes", pdfs: "3 PDFs", pages: "10 pág máx", history: "7 días historial", cta: "Empezar gratis", href: "/register", highlight: false },
  { name: "Básico", price: "9€", period: "/mes", pdfs: "30 PDFs", pages: "50 pág máx", history: "30 días historial", cta: "Suscribirme", href: "/register?plan=basic", highlight: true },
  { name: "Pro", price: "29€", period: "/mes", pdfs: "Ilimitado", pages: "200 pág máx", history: "1 año historial", cta: "Suscribirme", href: "/register?plan=pro", highlight: false },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* NAV */}
      <nav className="gradient-brand text-white px-6 py-4 flex items-center justify-between">
        <span className="text-xl font-bold tracking-tight">FacturAI</span>
        <div className="flex gap-4 text-sm font-medium">
          <Link href="#precios" className="hover:text-blue-200 transition-colors">Precios</Link>
          <Link href="/login" className="hover:text-blue-200 transition-colors">Entrar</Link>
          <Link href="/register" className="bg-white text-[#1F3864] px-4 py-1.5 rounded-full font-semibold hover:bg-blue-50 transition-colors">
            Empezar gratis
          </Link>
        </div>
      </nav>

      {/* HERO */}
      <section className="gradient-brand text-white text-center py-24 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="inline-block bg-white/10 text-blue-100 text-sm px-4 py-1 rounded-full mb-6 font-medium">
            🚀 Impulsado por Claude AI · Datos 100% seguros
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold leading-tight mb-6">
            Convierte tus facturas en PDF<br />a Excel en segundos
          </h1>
          <p className="text-lg text-blue-100 mb-10 max-w-xl mx-auto">
            Sube un PDF con todas tus facturas del mes. La IA extrae fecha, total, IVA y base por cada factura y te entrega un Excel listo para tu contable o declaración.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/register" className="bg-white text-[#1F3864] font-bold px-8 py-3 rounded-xl text-base hover:bg-blue-50 transition-all shadow-lg">
              Empezar gratis — sin tarjeta
            </Link>
            <Link href="#como-funciona" className="border border-white/40 text-white px-8 py-3 rounded-xl text-base hover:bg-white/10 transition-all">
              Ver cómo funciona
            </Link>
          </div>
        </div>
      </section>

      {/* CÓMO FUNCIONA */}
      <section id="como-funciona" className="py-20 px-6 bg-white">
        <div className="max-w-4xl mx-auto text-center mb-12">
          <h2 className="text-3xl font-bold text-slate-800 mb-3">Tan simple como 1, 2, 3</h2>
          <p className="text-slate-500">Sin instalaciones, sin configuración, desde el navegador.</p>
        </div>
        <div className="max-w-4xl mx-auto grid md:grid-cols-3 gap-8">
          {[
            { step: "1", title: "Sube tu PDF", desc: "Arrastra el PDF con todas tus facturas del mes al panel." },
            { step: "2", title: "La IA procesa", desc: "Claude analiza cada página y extrae los datos fiscales." },
            { step: "3", title: "Descarga el Excel", desc: "Recibes un Excel formateado con colores y hoja resumen." },
          ].map(({ step, title, desc }) => (
            <div key={step} className="text-center p-6 rounded-2xl border border-slate-100 shadow-sm">
              <div className="w-12 h-12 gradient-brand rounded-full flex items-center justify-center text-white font-bold text-xl mx-auto mb-4">{step}</div>
              <h3 className="font-bold text-slate-800 mb-2">{title}</h3>
              <p className="text-slate-500 text-sm">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section className="py-20 px-6 bg-slate-50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-slate-800 mb-12">Todo lo que necesitas</h2>
          <div className="grid md:grid-cols-3 gap-6">
            {features.map(({ icon, title, desc }) => (
              <div key={title} className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                <div className="text-3xl mb-3">{icon}</div>
                <h3 className="font-semibold text-slate-800 mb-1">{title}</h3>
                <p className="text-slate-500 text-sm">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PRECIOS */}
      <section id="precios" className="py-20 px-6 bg-white">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-slate-800 mb-3">Precios claros y sin sorpresas</h2>
          <p className="text-center text-slate-500 mb-12">Empieza gratis. Actualiza cuando lo necesites.</p>
          <div className="grid md:grid-cols-3 gap-6">
            {plans.map(({ name, price, period, pdfs, pages, history, cta, href, highlight }) => (
              <div key={name} className={`rounded-2xl p-8 border-2 flex flex-col ${highlight ? "border-[#4F7FE8] shadow-xl relative" : "border-slate-200 shadow-sm"}`}>
                {highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 gradient-brand text-white text-xs font-bold px-4 py-1 rounded-full">
                    MÁS POPULAR
                  </div>
                )}
                <h3 className="font-bold text-slate-800 text-xl mb-1">{name}</h3>
                <div className="flex items-end gap-1 mb-6">
                  <span className="text-4xl font-extrabold text-[#1F3864]">{price}</span>
                  <span className="text-slate-400 mb-1">{period}</span>
                </div>
                <ul className="space-y-2 mb-8 flex-1">
                  {[pdfs, pages, history].map((item) => (
                    <li key={item} className="flex items-center gap-2 text-sm text-slate-600">
                      <span className="text-green-500 font-bold">✓</span>{item}
                    </li>
                  ))}
                </ul>
                <Link href={href} className={`block text-center py-3 rounded-xl font-semibold transition-all ${highlight ? "gradient-brand text-white hover:opacity-90" : "border-2 border-[#1F3864] text-[#1F3864] hover:bg-slate-50"}`}>
                  {cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="gradient-brand text-white py-10 px-6 text-center text-sm">
        <p className="font-bold text-lg mb-1">FacturAI</p>
        <p className="text-blue-200">Datos cifrados · Servidores en la UE · Cumple LOPD/GDPR</p>
        <p className="text-blue-300 mt-4">© {new Date().getFullYear()} FacturAI. Todos los derechos reservados.</p>
      </footer>
    </div>
  );
}
