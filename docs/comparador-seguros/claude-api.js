const ClaudeAPI = (() => {
  function detectType(rawText) {
    const text = rawText.toLowerCase().substring(0, 3000);
    const allKeywords = CMF_DATA.categorias.flatMap(c =>
      c.keywords.map(kw => ({ kw, categoria: c }))
    );
    for (const { kw, categoria } of allKeywords) {
      if (text.includes(kw)) return categoria.nombre;
    }
    return '';
  }

  function findInsurer(text) {
    for (const company of CMF_DATA.companias) {
      if (text.toLowerCase().includes(company.toLowerCase())) return company;
    }
    const m = text.match(/([A-ZÁÉÍÓÚ][a-záéíóúA-ZÁÉÍÓÚ\s]{2,40}?)\s*(?:Seguros|Life|Vida|Salud)\s*(?:Chile|S\.A\.?)?/);
    if (m) return m[0].trim().replace(/\s{2,}/g, ' ');
    return 'No determinado en el documento';
  }

  function findAmounts(text) {
    const uf = [...text.matchAll(/UF\s*[\d.,]+/gi)].map(m => m[0]);
    const clp = [...text.matchAll(/\$\s*[\d.,]+/g)].map(m => m[0]);
    return { uf, clp, all: [...uf, ...clp] };
  }

  function findNearAmount(text, keywords) {
    const lower = text.toLowerCase();
    for (const kw of keywords) {
      const idx = lower.indexOf(kw.toLowerCase());
      if (idx === -1) continue;
      const win = text.substring(Math.max(0, idx - 80), idx + 180);
      const uf = win.match(/UF\s*[\d.,]+/i);
      if (uf) return uf[0];
      const clp = win.match(/\$\s*[\d.,]+/);
      if (clp) return clp[0];
    }
    return null;
  }

  function findFrequency(text) {
    const t = text.toLowerCase();
    if (t.match(/pago\s*(único|unico)|prima\s*(única|unica)/)) return 'Única';
    if (t.match(/\bmensual(mente)?\b/)) return 'Mensual';
    if (t.match(/\btrimestral(mente)?\b/)) return 'Trimestral';
    if (t.match(/\bsemestral(mente)?\b/)) return 'Semestral';
    if (t.match(/\banual(mente)?\b|\bprima\s*anual\b/)) return 'Anual';
    return 'No especificado';
  }

  function findDates(text) {
    const seen = new Set();
    const re = /\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b/g;
    let m;
    while ((m = re.exec(text)) !== null && seen.size < 10) seen.add(m[0]);
    return [...seen];
  }

  function findVigencia(text, dates) {
    const lower = text.toLowerCase();
    const idx = lower.indexOf('vigencia');
    if (idx !== -1) {
      const win = text.substring(idx, idx + 200);
      const ds = [...win.matchAll(/\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b/g)].map(m => m[0]);
      return { inicio: ds[0] || 'No especificado', fin: ds[1] || 'No especificado' };
    }
    return { inicio: dates[0] || 'No especificado', fin: dates[1] || 'No especificado' };
  }

  function detectCoberturas(text, categoria) {
    if (!categoria) return [];
    const found = [];
    for (const cob of categoria.coberturasTipicas) {
      const words = cob.toLowerCase().split(/\s+/).filter(w => w.length > 3);
      const hits = words.filter(w => text.toLowerCase().includes(w));
      if (hits.length >= Math.ceil(words.length * 0.5)) {
        const monto = findNearAmount(text, [cob]) || 'Ver documento';
        found.push({ nombre: cob, descripcion: 'Cobertura detectada en el documento', monto });
      }
    }
    if (found.length === 0) {
      return categoria.coberturasTipicas.slice(0, 3).map(c => ({
        nombre: c,
        descripcion: 'Cobertura típica para este tipo de seguro — verificar en documento',
        monto: 'No especificado'
      }));
    }
    return found;
  }

  function detectExclusiones(text, categoria) {
    if (!categoria) return [{ descripcion: 'Revisar exclusiones en el documento original', impacto: 'media' }];
    const found = [];
    for (const excl of categoria.exclusionesComunes) {
      const words = excl.toLowerCase().split(/\s+/).filter(w => w.length > 4);
      if (words.some(w => text.toLowerCase().includes(w))) {
        found.push({ descripcion: excl, impacto: 'media' });
      }
    }
    if (found.length === 0) {
      return categoria.exclusionesComunes.slice(0, 2).map(e => ({
        descripcion: e + ' (exclusión típica — verificar en documento)',
        impacto: 'media'
      }));
    }
    return found;
  }

  function calcScore(insurer, coberturas, amounts, dates, isScanned) {
    let s = 4;
    if (insurer !== 'No determinado en el documento') s++;
    if (coberturas.some(c => !c.descripcion.includes('típica'))) s++;
    if (amounts.all.length > 0) s++;
    if (dates.length > 1) s++;
    if (isScanned) s -= 2;
    return Math.max(1, Math.min(10, s));
  }

  async function analyzePolicy(rawText, fileName, extractionMethod) {
    const isScanned = extractionMethod === 'fallback';
    const policyType = detectType(rawText) || 'Seguro General';
    const insurer = findInsurer(rawText);
    const amounts = findAmounts(rawText);
    const dates = findDates(rawText);
    const vigencia = findVigencia(rawText, dates);
    const frequency = findFrequency(rawText);

    const categoria = CMF_DATA.categorias.find(c => c.nombre === policyType);
    const coberturas = detectCoberturas(rawText, categoria);
    const exclusiones = detectExclusiones(rawText, categoria);

    const prima = findNearAmount(rawText, ['prima', 'valor del seguro', 'costo del seguro'])
      || amounts.all[0]
      || 'No especificado';

    const deducible = findNearAmount(rawText, ['deducible', 'franquicia', 'copago'])
      || 'Sin deducible detectado';

    const score = calcScore(insurer, coberturas, amounts, dates, isScanned);
    const confianza = isScanned ? 'baja' : score >= 7 ? 'alta' : score >= 5 ? 'media' : 'baja';

    const comision = categoria?.comisionTipica || 'No determinado en el documento';
    const refNormativa = categoria?.referenciaCMF || 'Ley 20.667 - Contrato de Seguro';

    const advertencias = [];
    if (isScanned) advertencias.push('PDF escaneado — texto extraído puede tener errores de OCR');
    advertencias.push('Análisis automático local. Verifique todos los datos en el documento original.');

    return {
      policyType,
      insurer,
      asegurado: {
        resumen: `Documento de ${policyType} emitido por ${insurer}. Análisis automático detectó ${coberturas.length} coberturas y ${exclusiones.length} exclusiones.${isScanned ? ' PDF escaneado — revisar documento original.' : ''}`,
        coberturas,
        exclusiones,
        precio: {
          prima,
          frecuencia: frequency,
          deducibles: deducible,
          carencias: categoria?.carenciasHabituales || 'No aplica'
        },
        relacionCalidadPrecio: {
          puntuacion: score,
          justificacion: `Análisis automático local. Puntuación basada en información encontrada: ${coberturas.length} coberturas, ${amounts.all.length} montos y ${dates.length} fechas detectados. Se recomienda análisis profesional para evaluación completa.`
        },
        alertas: [
          { titulo: 'Verificar con documento original', descripcion: 'Este es un análisis automático sin IA. Confirme todos los datos directamente en su documento y/o con la compañía aseguradora.', prioridad: 'alta' },
          ...advertencias.map(d => ({ titulo: 'Nota', descripcion: d, prioridad: 'media' }))
        ],
        recomendacion: `Verifique coberturas y exclusiones en el documento original de ${insurer}. Para consultas, use el sistema conocetuseguro.cl de la CMF.`
      },
      corredor: {
        comision: {
          porcentaje: comision,
          tipo: 'corredor',
          notas: 'Rango típico en el mercado chileno según datos CMF. El porcentaje real está en el contrato.'
        },
        vigencia: {
          inicio: vigencia.inicio,
          fin: vigencia.fin,
          renovacion: 'Verificar en documento'
        },
        clausulasEspeciales: [],
        competitividad: {
          evaluacion: 'media',
          justificacion: 'Para evaluar competitividad, cargue múltiples pólizas del mismo tipo y compare en la tabla comparativa.'
        },
        argumentosVenta: [
          `${policyType} de ${insurer}, compañía regulada por CMF Chile`,
          `Coberturas detectadas: ${coberturas.map(c => c.nombre).join(', ')}`,
          `Comisión típica para corredores: ${comision}`,
          `Referencia normativa: ${refNormativa}`
        ],
        condicionesContrato: 'Revisar condiciones generales y particulares en el documento original emitido por la compañía.',
        alertasLegales: [{
          descripcion: `Seguro sujeto a ${refNormativa}`,
          referenciaNormativa: refNormativa
        }]
      },
      metadatos: {
        confianza,
        razonConfianza: `Análisis local sin IA. Confianza "${confianza}" — ${amounts.all.length} montos, ${dates.length} fechas y ${coberturas.length} coberturas detectados automáticamente.`,
        advertencias
      }
    };
  }

  return { analyzePolicy };
})();
