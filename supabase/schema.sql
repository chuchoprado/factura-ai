-- =====================================================
-- FacturAI — Schema Supabase
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- =====================================================

-- ── Extensiones ──────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Tabla: profiles ──────────────────────────────────
-- Una fila por usuario. Se crea automáticamente al registrarse.
CREATE TABLE IF NOT EXISTS public.profiles (
    id                   UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email                TEXT NOT NULL,
    full_name            TEXT,
    plan                 TEXT NOT NULL DEFAULT 'free'
                         CHECK (plan IN ('free', 'basic', 'pro')),
    pdfs_used_month      INTEGER NOT NULL DEFAULT 0,
    reset_date           DATE NOT NULL DEFAULT date_trunc('month', now())::date,
    stripe_customer_id   TEXT,
    subscription_status  TEXT DEFAULT 'inactive',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Tabla: conversions ───────────────────────────────
-- Historial de PDFs procesados por cada usuario.
CREATE TABLE IF NOT EXISTS public.conversions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    pages       INTEGER NOT NULL DEFAULT 0,
    completas   INTEGER NOT NULL DEFAULT 0,
    verificar   INTEGER NOT NULL DEFAULT 0,
    pendientes  INTEGER NOT NULL DEFAULT 0,
    tipo        TEXT NOT NULL DEFAULT 'autonomo'
                CHECK (tipo IN ('autonomo', 'gastos_pf')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Índices ───────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_conversions_user_id   ON public.conversions(user_id);
CREATE INDEX IF NOT EXISTS idx_conversions_created   ON public.conversions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe       ON public.profiles(stripe_customer_id);

-- ── Row Level Security (RLS) — cada usuario solo ve SUS datos ──
ALTER TABLE public.profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversions ENABLE ROW LEVEL SECURITY;

-- Policies: profiles
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- Policies: conversions
CREATE POLICY "Users can view own conversions"
    ON public.conversions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own conversions"
    ON public.conversions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- El backend (service_role) puede hacer todo — bypasea RLS automáticamente.

-- ── Función: reset mensual de cuota ──────────────────
CREATE OR REPLACE FUNCTION reset_monthly_quotas()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.profiles
    SET pdfs_used_month = 0,
        reset_date = date_trunc('month', now())::date
    WHERE reset_date < date_trunc('month', now())::date;
END;
$$;

-- ── Función: incrementar contador de PDFs usados ─────
CREATE OR REPLACE FUNCTION increment_pdfs_used(uid UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Reset automático si cambió el mes
    UPDATE public.profiles
    SET pdfs_used_month = CASE
            WHEN reset_date < date_trunc('month', now())::date THEN 1
            ELSE pdfs_used_month + 1
        END,
        reset_date = date_trunc('month', now())::date,
        updated_at = now()
    WHERE id = uid;
END;
$$;

-- ── Trigger: updated_at automático ───────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Cron: resetear cuotas el 1 de cada mes (requiere pg_cron) ──
-- Descomentar si tienes pg_cron habilitado en Supabase Pro:
-- SELECT cron.schedule('reset-monthly-quotas', '0 0 1 * *', 'SELECT reset_monthly_quotas()');
