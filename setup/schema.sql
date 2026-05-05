-- ============================================================
-- SEGUROS AEGIS — Schema Supabase
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

-- Páginas del sitio
CREATE TABLE IF NOT EXISTS pages (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  slug        TEXT UNIQUE NOT NULL,
  title       TEXT NOT NULL,
  meta_description TEXT,
  status      TEXT DEFAULT 'published' CHECK (status IN ('draft', 'published')),
  hero_config JSONB DEFAULT '{}',
  content_config JSONB DEFAULT '{}',
  layout_config  JSONB DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Cambios pendientes (cola de trabajo para Claude)
CREATE TABLE IF NOT EXISTS pending_changes (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  change_type  TEXT NOT NULL,
  target_page  TEXT,
  description  TEXT NOT NULL,
  payload      JSONB NOT NULL DEFAULT '{}',
  astro_file   TEXT,
  instructions TEXT NOT NULL,
  status       TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'applied', 'failed')),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  applied_at   TIMESTAMPTZ,
  commit_hash  TEXT
);

-- Historial de cambios aplicados
CREATE TABLE IF NOT EXISTS change_history (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  description     TEXT NOT NULL,
  changes_count   INT DEFAULT 0,
  commit_hash     TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Configuración global del sitio
CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── RLS: solo usuarios autenticados ──────────────────────────
ALTER TABLE pages           ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_history  ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings        ENABLE ROW LEVEL SECURITY;

CREATE POLICY "auth_only" ON pages           FOR ALL USING (auth.uid() IS NOT NULL);
CREATE POLICY "auth_only" ON pending_changes FOR ALL USING (auth.uid() IS NOT NULL);
CREATE POLICY "auth_only" ON change_history  FOR ALL USING (auth.uid() IS NOT NULL);
CREATE POLICY "auth_only" ON settings        FOR ALL USING (auth.uid() IS NOT NULL);

-- ── Datos iniciales: páginas actuales ────────────────────────
INSERT INTO pages (slug, title, meta_description, status, hero_config, content_config, layout_config) VALUES

('inicio', 'Seguros Aegis', 'Tu aliado estratégico en seguros. Asesoría experta, acceso a múltiples compañías y sin costo para ti.', 'published',
  '{"type":"custom","note":"Hero especial con skyline — ver index.astro"}',
  '{"type":"custom"}',
  '{"showPartners":true,"showCTA":false}'),

('nosotros', 'Sobre Nosotros', 'Somos una empresa familiar de corretaje de seguros con más de 40 años de experiencia en Chile.', 'published',
  '{"label":null,"title":"Sobre Nosotros","subtitle":null,"image":"hero-nosotros.png","bgColor":"#4D3B62","overlayOpacity":0.2,"minHeight":500,"align":"center"}',
  '{"type":"text_columns"}',
  '{"showPartners":true,"showCTA":true}'),

('personas', 'Seguros para Personas', 'Vehicular, hogar, salud, viajes, bicicleta, deportivo y responsabilidad civil.', 'published',
  '{"label":"Personas","title":"Seguros Para Personas","subtitle":"Coberturas flexibles que acompañan cada etapa de tu vida.","image":"fondo-inicio.webp","bgColor":"#4D3B62","overlayOpacity":0.28,"minHeight":500,"align":"left"}',
  '{"type":"accordion","dataSource":"personasInsurances","csvFile":"Guía Web - Personas.csv"}',
  '{"showPartners":true,"showCTA":false}'),

('empresas', 'Seguros para Empresas', 'Programas integrales de seguros para empresas.', 'published',
  '{"label":"Empresas","title":"Protege lo que tu negocio ha construido","subtitle":"Diseñamos programas de seguros para PyMEs y empresas grandes.","image":null,"bgColor":"#4D3B62","overlayOpacity":0.15,"minHeight":500,"align":"left"}',
  '{"type":"accordion","dataSource":"businessInsurances","csvFile":"Guía Web - Empresas.csv"}',
  '{"showPartners":true,"showCTA":false}'),

('comunidades', 'Seguros para Comunidades', 'Pólizas especializadas para edificios y condominios.', 'published',
  '{"label":"Comunidades","title":"La tranquilidad que tu edificio merece","subtitle":"Pólizas específicas para condominios y edificios residenciales.","image":null,"bgColor":"#4D3B62","overlayOpacity":0.15,"minHeight":500,"align":"left"}',
  '{"type":"coverage_list"}',
  '{"showPartners":true,"showCTA":false}'),

('contacto', 'Contacto', 'Cotiza tu seguro con Seguros Aegis.', 'published',
  '{"label":"Contacto","title":"Conversemos sobre tu protección","subtitle":"Cuéntanos qué necesitas y te respondemos el mismo día hábil.","image":null,"bgColor":"#4D3B62","overlayOpacity":0.15,"minHeight":500,"align":"left"}',
  '{"type":"contact_form"}',
  '{"showPartners":true,"showCTA":false}')

ON CONFLICT (slug) DO NOTHING;

-- Configuración global
INSERT INTO settings (key, value) VALUES
  ('colors',  '{"primary":"#4D3B62","accent":"#C7A965","dark":"#261c30","surface":"#f2f4f6"}'),
  ('fonts',   '{"main":"Cinzel"}'),
  ('hero',    '{"defaultMinHeight":500,"defaultOverlayOpacity":0.15,"defaultBgColor":"#4D3B62"}')
ON CONFLICT (key) DO NOTHING;
