"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) { setError("La contraseña debe tener al menos 8 caracteres."); return; }
    setError(""); setLoading(true);
    try {
      await register(email, password, fullName);
      setSuccess(true);
    } catch (err: any) {
      setError(err.message || "Error al registrarse");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen gradient-brand flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md text-center">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-xl font-bold text-[#1F3864] mb-2">¡Cuenta creada!</h2>
          <p className="text-slate-500 text-sm mb-6">
            Tu cuenta está lista. Ya puedes iniciar sesión con <strong>{email}</strong>.
          </p>
          <Link href="/login" className="gradient-brand text-white px-6 py-2.5 rounded-xl font-semibold text-sm hover:opacity-90 transition-opacity">
            Iniciar sesión
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen gradient-brand flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-extrabold text-[#1F3864]">FacturAI</h1>
          <p className="text-slate-500 mt-1 text-sm">Crea tu cuenta gratuita</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Nombre completo</label>
            <input
              type="text" value={fullName} onChange={(e) => setFullName(e.target.value)}
              placeholder="Juan García" required
              className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-[#4F7FE8] text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              required placeholder="tu@email.com"
              className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-[#4F7FE8] text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Contraseña</label>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              required placeholder="Mínimo 8 caracteres"
              className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-[#4F7FE8] text-sm"
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              {error}
            </div>
          )}

          <button
            type="submit" disabled={loading}
            className="w-full gradient-brand text-white py-3 rounded-xl font-semibold hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {loading ? "Creando cuenta..." : "Crear cuenta gratis"}
          </button>

          <p className="text-xs text-slate-400 text-center">
            Al registrarte aceptas nuestros términos de servicio y política de privacidad.
          </p>
        </form>

        <p className="text-center text-sm text-slate-500 mt-6">
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="text-[#4F7FE8] font-semibold hover:underline">Inicia sesión</Link>
        </p>
      </div>
    </div>
  );
}
