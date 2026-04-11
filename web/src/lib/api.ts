/**
 * Cliente API — FacturAI
 * Todas las llamadas al backend FastAPI.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Token helper ─────────────────────────────────────
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("factura_ai_token");
}

export function setToken(token: string) {
  localStorage.setItem("factura_ai_token", token);
}

export function clearToken() {
  localStorage.removeItem("factura_ai_token");
  localStorage.removeItem("factura_ai_user");
}

// ── Auth ─────────────────────────────────────────────
export async function login(email: string, password: string) {
  const form = new FormData();
  form.append("email", email);
  form.append("password", password);

  const res = await fetch(`${API_URL}/auth/login`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Credenciales incorrectas");
  }
  const data = await res.json();
  setToken(data.access_token);
  localStorage.setItem("factura_ai_user", JSON.stringify(data));
  return data;
}

export async function register(email: string, password: string, fullName: string) {
  const form = new FormData();
  form.append("email", email);
  form.append("password", password);
  form.append("full_name", fullName);

  const res = await fetch(`${API_URL}/auth/register`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al registrarse");
  }
  return res.json();
}

// ── Usuario ──────────────────────────────────────────
export async function getMe() {
  const token = getToken();
  if (!token) throw new Error("No autenticado");

  const res = await fetch(`${API_URL}/user/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) { clearToken(); throw new Error("Sesión expirada"); }
  if (!res.ok) throw new Error("Error obteniendo perfil");
  return res.json();
}

// ── Extracción ───────────────────────────────────────
export async function extractPdf(
  file: File,
  tipo: "autonomo" | "gastos_pf",
  onProgress?: (msg: string) => void,
): Promise<Blob> {
  const token = getToken();
  if (!token) throw new Error("No autenticado");

  const form = new FormData();
  form.append("file", file);
  form.append("tipo", tipo);

  onProgress?.("Enviando PDF al servidor...");

  const res = await fetch(`${API_URL}/extract`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (res.status === 402) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Límite de plan alcanzado");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error procesando el PDF");
  }

  onProgress?.("Generando Excel...");
  return res.blob();
}

// ── Historial ────────────────────────────────────────
export async function getHistory() {
  const token = getToken();
  if (!token) throw new Error("No autenticado");

  const res = await fetch(`${API_URL}/history`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Error obteniendo historial");
  return res.json();
}

// ── Billing ──────────────────────────────────────────
export async function getCheckoutUrl(plan: string): Promise<string> {
  const token = getToken();
  if (!token) throw new Error("No autenticado");

  const form = new FormData();
  form.append("plan", plan);

  const res = await fetch(`${API_URL}/billing/checkout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) throw new Error("Error creando sesión de pago");
  const data = await res.json();
  return data.checkout_url;
}

export async function getPortalUrl(): Promise<string> {
  const token = getToken();
  if (!token) throw new Error("No autenticado");

  const res = await fetch(`${API_URL}/billing/portal`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Error abriendo portal de facturación");
  const data = await res.json();
  return data.portal_url;
}
