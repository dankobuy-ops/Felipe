const UIRenderer = (() => {
  function scoreColor(score) {
    const n = Number(score);
    if (n >= CONFIG.SCORE_HIGH) return 'score-high';
    if (n >= CONFIG.SCORE_MEDIUM) return 'score-medium';
    return 'score-low';
  }

  function priorityClass(p) {
    return { alta: 'priority-high', media: 'priority-medium', baja: 'priority-low' }[p] || 'priority-low';
  }

  function competenciaClass(e) {
    return { alta: 'comp-high', media: 'comp-medium', baja: 'comp-low' }[e] || 'comp-medium';
  }

  function confidenceBadge(conf) {
    const map = {
      alta: { cls: 'badge-high', label: 'Confianza Alta' },
      media: { cls: 'badge-medium', label: 'Confianza Media' },
      baja: { cls: 'badge-low', label: 'Confianza Baja' }
    };
    const b = map[conf] || map['media'];
    return `<span class="confidence-badge ${b.cls}">${b.label}</span>`;
  }

  function escHtml(str) {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderCoberturas(coberturas) {
    if (!coberturas || !coberturas.length) return '<p class="empty-state">No se determinaron coberturas</p>';
    return coberturas.map(c => `
      <div class="cobertura-item">
        <div class="cobertura-header">
          <span class="cobertura-check">✓</span>
          <strong>${escHtml(c.nombre)}</strong>
          ${c.monto && c.monto !== 'No especificado' ? `<span class="cobertura-monto">${escHtml(c.monto)}</span>` : ''}
        </div>
        <p class="cobertura-desc">${escHtml(c.descripcion)}</p>
      </div>`).join('');
  }

  function renderExclusiones(exclusiones) {
    if (!exclusiones || !exclusiones.length) return '<p class="empty-state">No se determinaron exclusiones</p>';
    return exclusiones.map(e => `
      <div class="exclusion-item">
        <span class="exclusion-x">✗</span>
        <div class="exclusion-content">
          <span class="exclusion-text">${escHtml(e.descripcion)}</span>
          <span class="impact-badge ${priorityClass(e.impacto)}">${e.impacto || 'bajo'}</span>
        </div>
      </div>`).join('');
  }

  function renderAlertas(alertas) {
    if (!alertas || !alertas.length) return '';
    return alertas.map(a => `
      <div class="alerta-item ${priorityClass(a.prioridad)}">
        <div class="alerta-header">
          <span class="alerta-icon">${a.prioridad === 'alta' ? '🔴' : a.prioridad === 'media' ? '🟡' : 'ℹ️'}</span>
          <strong>${escHtml(a.titulo)}</strong>
          <span class="priority-label">${a.prioridad || 'baja'}</span>
        </div>
        <p>${escHtml(a.descripcion)}</p>
      </div>`).join('');
  }

  function renderAseguradoTab(analysis) {
    const a = analysis.asegurado;
    const score = a.relacionCalidadPrecio;
    return `
      <div class="tab-content">
        <div class="analysis-grid">
          <div class="card">
            <h3 class="card-title">📋 Resumen</h3>
            <p class="resumen-text">${escHtml(a.resumen)}</p>
          </div>
          <div class="card">
            <h3 class="card-title">💰 Precio</h3>
            <div class="precio-grid">
              <div class="precio-item">
                <span class="precio-label">Prima</span>
                <span class="precio-value">${escHtml(a.precio.prima)}</span>
              </div>
              <div class="precio-item">
                <span class="precio-label">Frecuencia</span>
                <span class="precio-value">${escHtml(a.precio.frecuencia)}</span>
              </div>
              <div class="precio-item">
                <span class="precio-label">Deducible</span>
                <span class="precio-value">${escHtml(a.precio.deducibles)}</span>
              </div>
              <div class="precio-item">
                <span class="precio-label">Carencias</span>
                <span class="precio-value">${escHtml(a.precio.carencias)}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">✅ Coberturas</h3>
          <div class="coberturas-list">${renderCoberturas(a.coberturas)}</div>
        </div>

        <div class="card">
          <h3 class="card-title">⚠️ Exclusiones</h3>
          <div class="exclusiones-list">${renderExclusiones(a.exclusiones)}</div>
        </div>

        ${a.alertas && a.alertas.length ? `
        <div class="card">
          <h3 class="card-title">🚨 Alertas para el Asegurado</h3>
          <div class="alertas-list">${renderAlertas(a.alertas)}</div>
        </div>` : ''}

        <div class="card card-score">
          <h3 class="card-title">⭐ Relación Calidad / Precio</h3>
          <div class="score-container">
            <div class="score-circle ${scoreColor(score.puntuacion)}">
              <span class="score-number">${score.puntuacion}</span>
              <span class="score-max">/10</span>
            </div>
            <p class="score-justificacion">${escHtml(score.justificacion)}</p>
          </div>
        </div>

        <div class="card card-recomendacion">
          <h3 class="card-title">💡 Recomendación</h3>
          <p class="recomendacion-text">${escHtml(a.recomendacion)}</p>
        </div>
      </div>`;
  }

  function renderCorredorTab(analysis) {
    const c = analysis.corredor;
    return `
      <div class="tab-content">
        <div class="analysis-grid">
          <div class="card">
            <h3 class="card-title">💼 Comisión</h3>
            <div class="comision-block">
              <div class="comision-pct">${escHtml(c.comision.porcentaje)}</div>
              <div class="comision-tipo">Tipo: ${escHtml(c.comision.tipo)}</div>
              ${c.comision.notas ? `<p class="comision-notas">${escHtml(c.comision.notas)}</p>` : ''}
            </div>
          </div>
          <div class="card">
            <h3 class="card-title">📅 Vigencia</h3>
            <div class="vigencia-block">
              <div class="vigencia-item"><span>Inicio:</span> <strong>${escHtml(c.vigencia.inicio)}</strong></div>
              <div class="vigencia-item"><span>Fin:</span> <strong>${escHtml(c.vigencia.fin)}</strong></div>
              <div class="vigencia-item"><span>Renovación:</span> <strong>${escHtml(c.vigencia.renovacion)}</strong></div>
            </div>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">📊 Competitividad en el Mercado</h3>
          <div class="competitividad-block">
            <span class="comp-badge ${competenciaClass(c.competitividad.evaluacion)}">${c.competitividad.evaluacion}</span>
            <p>${escHtml(c.competitividad.justificacion)}</p>
          </div>
        </div>

        ${c.argumentosVenta && c.argumentosVenta.length ? `
        <div class="card">
          <h3 class="card-title">🎯 Argumentos de Venta</h3>
          <ul class="argumentos-list">
            ${c.argumentosVenta.map(a => `<li>${escHtml(a)}</li>`).join('')}
          </ul>
        </div>` : ''}

        ${c.clausulasEspeciales && c.clausulasEspeciales.length ? `
        <div class="card">
          <h3 class="card-title">📜 Cláusulas Especiales</h3>
          ${c.clausulasEspeciales.map(cl => `
            <div class="clausula-item">
              <strong>${escHtml(cl.nombre)}</strong>
              <p>${escHtml(cl.descripcion)}</p>
              <span class="relevancia-tag">Relevancia: ${escHtml(cl.relevanciaComercial)}</span>
            </div>`).join('')}
        </div>` : ''}

        <div class="card">
          <h3 class="card-title">📋 Condiciones del Contrato</h3>
          <p>${escHtml(c.condicionesContrato)}</p>
        </div>

        ${c.alertasLegales && c.alertasLegales.length ? `
        <div class="card card-legal">
          <h3 class="card-title">⚖️ Alertas Legales y Normativas</h3>
          ${c.alertasLegales.map(al => `
            <div class="alerta-legal-item">
              <p>${escHtml(al.descripcion)}</p>
              ${al.referenciaNormativa ? `<span class="ref-normativa">📌 ${escHtml(al.referenciaNormativa)}</span>` : ''}
            </div>`).join('')}
        </div>` : ''}
      </div>`;
  }

  function renderPolicyCard(policy) {
    const a = policy.analysis;
    const cardId = `policy-${policy.id}`;
    return `
      <div class="policy-card" id="${cardId}">
        <div class="policy-card-header">
          <div class="policy-info">
            <h2 class="policy-name">${escHtml(a.insurer || 'Compañía no determinada')}</h2>
            <div class="policy-meta">
              <span class="policy-type-badge">${escHtml(a.policyType || 'Tipo no determinado')}</span>
              ${confidenceBadge(a.metadatos?.confianza)}
              <span class="file-name">📄 ${escHtml(policy.fileName)}</span>
            </div>
          </div>
        </div>

        ${policy.extractionMethod === 'fallback' ? `
          <div class="scan-warning">
            ⚠️ PDF escaneado detectado — el análisis puede ser limitado
          </div>` : ''}

        ${a.metadatos?.advertencias?.length ? `
          <div class="meta-warnings">
            ${a.metadatos.advertencias.map(w => `<p>ℹ️ ${escHtml(w)}</p>`).join('')}
          </div>` : ''}

        <div class="tabs-container">
          <div class="tabs-nav">
            <button class="tab-btn tab-btn-active" data-policy="${policy.id}" data-tab="asegurado">
              👤 Perspectiva Asegurado
            </button>
            <button class="tab-btn" data-policy="${policy.id}" data-tab="corredor">
              🤝 Perspectiva Corredor
            </button>
          </div>
          <div class="tab-panel" id="panel-asegurado-${policy.id}">
            ${renderAseguradoTab(a)}
          </div>
          <div class="tab-panel tab-panel-hidden" id="panel-corredor-${policy.id}">
            ${renderCorredorTab(a)}
          </div>
        </div>
      </div>`;
  }

  function renderComparisonTable(policies) {
    const done = policies.filter(p => p.status === 'done' && p.analysis);
    if (done.length < 2) return '';

    const fields = [
      { label: 'Compañía', get: p => p.analysis.insurer || '—' },
      { label: 'Tipo de Seguro', get: p => p.analysis.policyType || '—' },
      { label: 'Prima', get: p => p.analysis.asegurado?.precio?.prima || '—', compare: false },
      { label: 'Frecuencia', get: p => p.analysis.asegurado?.precio?.frecuencia || '—', compare: false },
      { label: 'Deducible', get: p => p.analysis.asegurado?.precio?.deducibles || '—', compare: false },
      { label: 'Calidad/Precio', get: p => p.analysis.asegurado?.relacionCalidadPrecio?.puntuacion?.toString() || '—', bestIsHigher: true },
      { label: 'Competitividad', get: p => p.analysis.corredor?.competitividad?.evaluacion || '—', compare: false },
      { label: 'Comisión Corredor', get: p => p.analysis.corredor?.comision?.porcentaje || '—', compare: false },
      { label: 'Vigencia Inicio', get: p => p.analysis.corredor?.vigencia?.inicio || '—', compare: false },
      { label: 'Vigencia Fin', get: p => p.analysis.corredor?.vigencia?.fin || '—', compare: false }
    ];

    const headers = done.map(p => `<th>${escHtml(p.fileName)}</th>`).join('');

    const rows = fields.map(field => {
      const vals = done.map(p => field.get(p));
      let bestIdx = -1;

      if (field.bestIsHigher) {
        const nums = vals.map(v => parseFloat(v));
        const max = Math.max(...nums.filter(n => !isNaN(n)));
        bestIdx = nums.findIndex(n => n === max);
      }

      const cells = vals.map((v, i) => {
        const isBest = bestIdx === i;
        return `<td class="${isBest ? 'best-value' : ''}">${escHtml(v)}${isBest ? ' ⭐' : ''}</td>`;
      }).join('');

      return `<tr><td class="row-label">${field.label}</td>${cells}</tr>`;
    }).join('');

    return `
      <div class="comparison-section">
        <h2 class="section-title">📊 Tabla Comparativa</h2>
        <div class="table-wrapper">
          <table class="comparison-table">
            <thead>
              <tr>
                <th class="row-label-header">Campo</th>
                ${headers}
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <p class="table-note">⭐ indica el mejor valor en esa categoría</p>
      </div>`;
  }

  function renderLoadingCard(policy) {
    const steps = {
      extracting: { icon: '📄', msg: 'Extrayendo texto del PDF...' },
      analyzing: { icon: '🤖', msg: 'Analizando con IA...' },
      error: { icon: '❌', msg: policy.error || 'Error al procesar' }
    };
    const step = steps[policy.status] || { icon: '⏳', msg: 'Procesando...' };

    if (policy.status === 'error') {
      return `
        <div class="policy-card policy-card-error">
          <div class="error-header">
            <span class="error-icon">❌</span>
            <div>
              <strong>${escHtml(policy.fileName)}</strong>
              <p class="error-msg">${escHtml(policy.error)}</p>
            </div>
          </div>
        </div>`;
    }

    return `
      <div class="policy-card policy-card-loading">
        <div class="loading-card-content">
          <div class="loading-spinner-small"></div>
          <div>
            <strong>${escHtml(policy.fileName)}</strong>
            <p class="loading-step">${step.icon} ${step.msg}</p>
          </div>
        </div>
      </div>`;
  }

  function renderAll(policies) {
    const container = document.getElementById('resultsContent');
    if (!container) return;

    const done = policies.filter(p => p.status === 'done' && p.analysis);
    const processing = policies.filter(p => ['extracting', 'analyzing'].includes(p.status));
    const errors = policies.filter(p => p.status === 'error');

    let html = '';

    if (done.length >= 2) {
      html += renderComparisonTable(policies);
      html += `<h2 class="section-title" style="margin-top:2rem">📋 Análisis Individual</h2>`;
    }

    for (const p of done) {
      html += renderPolicyCard(p);
    }
    for (const p of processing) {
      html += renderLoadingCard(p);
    }
    for (const p of errors) {
      html += renderLoadingCard(p);
    }

    container.innerHTML = html;

    container.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const policyId = btn.dataset.policy;
        const tabName = btn.dataset.tab;

        container.querySelectorAll(`[data-policy="${policyId}"].tab-btn`).forEach(b => b.classList.remove('tab-btn-active'));
        btn.classList.add('tab-btn-active');

        container.querySelectorAll(`#panel-asegurado-${policyId}, #panel-corredor-${policyId}`).forEach(panel => {
          panel.classList.add('tab-panel-hidden');
        });
        const target = container.querySelector(`#panel-${tabName}-${policyId}`);
        if (target) target.classList.remove('tab-panel-hidden');
      });
    });

    const hasContent = done.length + processing.length + errors.length > 0;
    const section = document.getElementById('resultsSection');
    if (section) section.style.display = hasContent ? 'block' : 'none';
  }

  return { renderAll, renderLoadingCard };
})();
