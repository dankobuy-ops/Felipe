#!/usr/bin/env node
/**
 * sync-db.js — Seguros Aegis
 * Lee cambios pendientes de Supabase y genera instrucciones para Claude.
 *
 * Uso:
 *   node sync-db.js          → muestra cambios pendientes
 *   node sync-db.js --apply  → marca los cambios como "processing"
 */

const fs   = require('fs');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
  console.error('\n❌ Faltan variables de entorno en .env:\n   SUPABASE_URL\n   SUPABASE_SERVICE_KEY\n');
  process.exit(1);
}

const applyMode = process.argv.includes('--apply');

async function fetchPendingChanges() {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/pending_changes?status=eq.pending&order=created_at.asc`,
    { headers: { apikey: SUPABASE_SERVICE_KEY, Authorization: `Bearer ${SUPABASE_SERVICE_KEY}` } }
  );
  if (!res.ok) throw new Error(`Error DB: ${res.status} ${await res.text()}`);
  return res.json();
}

async function markProcessing(ids) {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/pending_changes?id=in.(${ids.join(',')})`,
    {
      method: 'PATCH',
      headers: {
        apikey:        SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
        'Content-Type': 'application/json',
        Prefer:        'return=minimal',
      },
      body: JSON.stringify({ status: 'processing' }),
    }
  );
  if (!res.ok) throw new Error(`Error al marcar: ${res.status}`);
}

async function recordHistory(changes, commitHash) {
  await fetch(`${SUPABASE_URL}/rest/v1/change_history`, {
    method: 'POST',
    headers: {
      apikey:        SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
      'Content-Type': 'application/json',
      Prefer:        'return=minimal',
    },
    body: JSON.stringify({
      description:   `Sincronización CLI: ${changes.length} cambio(s)`,
      changes_count: changes.length,
      commit_hash:   commitHash || null,
    }),
  });
}

function buildOutput(changes) {
  const lines = [
    '',
    '╔══════════════════════════════════════════════════════════╗',
    '║    SEGUROS AEGIS — CAMBIOS PENDIENTES PARA CLAUDE        ║',
    '╚══════════════════════════════════════════════════════════╝',
    `  Generado: ${new Date().toLocaleString('es-CL')}`,
    `  Total:    ${changes.length} cambio(s)`,
    '',
    '  Instrucciones: Aplica TODOS los cambios, luego ejecuta:',
    '  cd saegis-web && npm run build',
    '  git add -A && git commit -m "..." && git push origin main',
    '',
    '══════════════════════════════════════════════════════════',
  ];

  changes.forEach((c, i) => {
    lines.push('');
    lines.push(`CAMBIO ${i + 1} de ${changes.length}: ${c.description}`);
    if (c.target_page) lines.push(`  Página:  /${c.target_page}`);
    if (c.astro_file)  lines.push(`  Archivo: ${c.astro_file}`);
    lines.push('  ──────────────────────────────────────────────────────');
    c.instructions.split('\n').forEach(l => lines.push(`  ${l}`));
  });

  lines.push('');
  lines.push('══════════════════════════════════════════════════════════');
  lines.push('FIN DE INSTRUCCIONES');
  lines.push('');
  return lines.join('\n');
}

async function main() {
  console.log('\n🔄 Conectando a Supabase...');

  let changes;
  try {
    changes = await fetchPendingChanges();
  } catch (err) {
    console.error('❌ Error:', err.message);
    process.exit(1);
  }

  if (changes.length === 0) {
    console.log('\n✅ No hay cambios pendientes.\n');
    return;
  }

  const output = buildOutput(changes);
  console.log(output);

  // Guardar en archivo
  const outFile = path.join(__dirname, 'PENDING_CHANGES.md');
  fs.writeFileSync(outFile, output);
  console.log(`\n📄 Guardado en: ${outFile}`);
  console.log('   Muéstrale ese archivo a Claude y dile: "aplica los cambios pendientes"\n');

  if (applyMode) {
    const ids = changes.map(c => c.id);
    await markProcessing(ids);
    console.log(`✅ ${ids.length} cambio(s) marcados como "processing" en la DB.\n`);
  }
}

main().catch(err => { console.error('❌ Error inesperado:', err); process.exit(1); });
