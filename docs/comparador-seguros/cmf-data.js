const CMF_DATA = {
  mercado: {
    regulador: 'Comisión para el Mercado Financiero (CMF Chile)',
    leyPrincipal: 'Ley 20.667 - Contrato de Seguro',
    totalCompanias: 32,
    sistemaVerificacion: 'conocetuseguro.cl (SICS)'
  },

  companias: [
    'Zurich Chile', 'MetLife Chile', 'MAPFRE Chile', 'HDI Seguros',
    'Chubb Seguros Chile', 'Liberty Seguros', 'Bupa Chile',
    'Cruz Blanca Salud', 'Consorcio Nacional de Seguros', 'Penta Vida',
    'Cardif Chile', 'BCI Seguros', 'Chilena Consolidada', 'SURA Chile',
    'Principal Seguros', 'Mutual de Seguridad CChC', 'Vida Cámara',
    'Euroamerica Seguros', 'Orbis Seguros', 'HDI Seguros Generales',
    'ACE Seguros', 'AXA Seguros', 'Falabella Seguros', 'Ripley Seguros',
    'Zurich Santander', 'CN Life'
  ],

  categorias: [
    {
      id: 'vida',
      keywords: ['vida', 'life', 'fallecimiento', 'muerte', 'diba', 'itp'],
      nombre: 'Seguro de Vida',
      descripcion: 'Cubre fallecimiento, invalidez total y permanente',
      coberturasTipicas: ['Muerte natural', 'Muerte accidental', 'Invalidez Total y Permanente (ITP)', 'DIBA (Doble Indemnización por Accidente)'],
      exclusionesComunes: ['Suicidio durante el primer año de vigencia', 'Deportes extremos no declarados', 'Guerra y actos terroristas', 'Preexistencias no declaradas'],
      comisionTipica: '15-25% de la prima anual',
      referenciaCMF: 'NCG 306 - Norma de seguros de vida'
    },
    {
      id: 'salud',
      keywords: ['salud', 'health', 'hospitalización', 'médico', 'complementario', 'dental', 'fonasa', 'isapre'],
      nombre: 'Seguro de Salud Complementario',
      descripcion: 'Complementa cobertura FONASA o Isapre',
      coberturasTipicas: ['Hospitalización', 'Cirugías', 'Medicamentos ambulatorios', 'Dental', 'Maternidad'],
      exclusionesComunes: ['Preexistencias durante el primer año', 'Tratamientos cosméticos', 'Tratamientos experimentales', 'Enfermedades crónicas no declaradas'],
      comisionTipica: '8-15% de la prima',
      carenciasHabituales: '3 meses general, 6 meses maternidad, 12 meses preexistencias',
      referenciaCMF: 'NCG 124 - Seguros de salud'
    },
    {
      id: 'vehiculos',
      keywords: ['vehículo', 'vehiculo', 'auto', 'automóvil', 'automovil', 'moto', 'camión', 'camion', 'colisión', 'collision', 'todo riesgo'],
      nombre: 'Seguro de Vehículos Motorizados',
      descripcion: 'Todo riesgo o terceros para vehículos motorizados',
      coberturasTipicas: ['Colisión y vuelco', 'Robo total', 'Robo parcial', 'Responsabilidad Civil', 'Asistencia en ruta 24/7', 'Gastos médicos ocupantes'],
      exclusionesComunes: ['Conducción bajo influencia de alcohol o drogas', 'Carreras y competencias', 'Uso comercial no declarado', 'Conductor no autorizado'],
      comisionTipica: '10-20% de la prima',
      referenciaCMF: 'NCG 309 - Seguros de vehículos motorizados'
    },
    {
      id: 'soap',
      keywords: ['soap', 'obligatorio', 'ley 18.490', '18490', 'accidente tránsito', 'transito'],
      nombre: 'SOAP (Seguro Obligatorio de Accidentes Personales)',
      descripcion: 'Seguro obligatorio accidentes personales en tránsito - Ley 18.490',
      coberturasTipicas: ['Muerte por accidente de tránsito', 'Invalidez permanente', 'Gastos médicos y hospitalarios'],
      montosCubiertos: {
        muerte: 'UF 300 por víctima',
        invalidezTotal: 'UF 300',
        gastosMedicos: 'UF 120 por accidente',
        invalidezParcial: 'Hasta UF 200 según tabla de invalideces'
      },
      vigencia: '1 año calendario',
      comisionTipica: '5-8%',
      referenciaCMF: 'Ley 18.490 Art. 1-25'
    },
    {
      id: 'incendio',
      keywords: ['incendio', 'hogar', 'vivienda', 'inmueble', 'propiedad', 'multiriesgo', 'terremoto', 'sismo', 'explosión'],
      nombre: 'Seguro de Incendio y Hogar',
      descripcion: 'Protección para inmuebles y contenido del hogar',
      coberturasTipicas: ['Incendio y explosión', 'Sismo/Terremoto (cláusula adicional)', 'Robo de contenido', 'Responsabilidad Civil arrendatario', 'Rotura de cañerías'],
      exclusionesComunes: ['Daños por humedad gradual', 'Guerra y conmoción civil', 'Terremoto sin cláusula adicional', 'Desgaste natural'],
      comisionTipica: '12-22% de la prima',
      notaChile: 'Chile es zona sísmica de alto riesgo — la cláusula de cobertura de terremoto es una adición CRÍTICA en el mercado chileno',
      referenciaCMF: 'NCG 255 - Seguros de incendio'
    },
    {
      id: 'desgravamen',
      keywords: ['desgravamen', 'hipotecario', 'crédito hipotecario', 'saldo insoluto', 'mutuo'],
      nombre: 'Seguro de Desgravamen Hipotecario',
      descripcion: 'Cubre el saldo insoluto del crédito hipotecario ante muerte o ITP del deudor',
      coberturasTipicas: ['Fallecimiento del deudor', 'Invalidez Total y Permanente', 'Desempleo involuntario (cláusula adicional)'],
      exclusionesComunes: ['Preexistencias no declaradas en solicitud', 'Suicidio durante el primer año', 'Invalidez preexistente'],
      comisionTipica: '3-8% (generalmente incluido en la tasa del crédito hipotecario)',
      referenciaCMF: 'NCG 283 - Seguros de desgravamen'
    },
    {
      id: 'apv',
      keywords: ['apv', 'ahorro previsional', 'previsional voluntario', 'apvc', '42 bis'],
      nombre: 'Seguro con Ahorro Previsional Voluntario (APV)',
      descripcion: 'Seguro con componente de ahorro y beneficios tributarios Art. 42 bis LIR',
      coberturasTipicas: ['Seguro de vida base', 'Ahorro acumulado con rentabilidad', 'Invalidez'],
      beneficioTributario: '15% descuento base imponible (Régimen A), máx 600 UF/año. O exención de impuesto al retiro (Régimen B)',
      comisionTipica: '2-5% del fondo administrado anualmente',
      referenciaCMF: 'NCG 167 - Seguros APV'
    },
    {
      id: 'rc',
      keywords: ['responsabilidad civil', 'daños a terceros', 'rc', 'liability'],
      nombre: 'Seguro de Responsabilidad Civil',
      descripcion: 'Protección ante daños materiales o corporales causados a terceros',
      coberturasTipicas: ['Daños materiales a terceros', 'Daños corporales a terceros', 'Gastos de defensa legal', 'Costas judiciales'],
      exclusionesComunes: ['Daño intencional o doloso', 'Contaminación ambiental gradual', 'Responsabilidad contractual pura', 'Multas y sanciones'],
      comisionTipica: '15-25% de la prima',
      referenciaCMF: 'NCG 223 - Seguros de Responsabilidad Civil'
    }
  ],

  getContextForType(tipoSeguro) {
    if (!tipoSeguro) return this._defaultContext();

    const tipoLower = tipoSeguro.toLowerCase();
    const categoria = this.categorias.find(c =>
      c.keywords.some(kw => tipoLower.includes(kw))
    );

    if (!categoria) return this._defaultContext();

    let ctx = `Tipo de seguro identificado: ${categoria.nombre}
Descripción: ${categoria.descripcion}
Coberturas típicas en el mercado chileno: ${categoria.coberturasTipicas.join(', ')}
Exclusiones comunes en Chile: ${categoria.exclusionesComunes.join(', ')}
Rango de comisión típica para corredores: ${categoria.comisionTipica}
Referencia normativa CMF: ${categoria.referenciaCMF}`;

    if (categoria.notaChile) ctx += `\nNota especial mercado chileno: ${categoria.notaChile}`;
    if (categoria.montosCubiertos) ctx += `\nMontos cubiertos por ley: ${JSON.stringify(categoria.montosCubiertos)}`;
    if (categoria.carenciasHabituales) ctx += `\nCarencias habituales en mercado: ${categoria.carenciasHabituales}`;
    if (categoria.beneficioTributario) ctx += `\nBeneficio tributario: ${categoria.beneficioTributario}`;

    return ctx;
  },

  _defaultContext() {
    return `Mercado asegurador chileno regulado por CMF (Comisión para el Mercado Financiero).
Compañías principales registradas: ${this.companias.slice(0, 12).join(', ')}.
Marco legal principal: ${this.mercado.leyPrincipal}.
Total compañías reguladas: ${this.mercado.totalCompanias}.
Sistema de verificación de pólizas activas: ${this.mercado.sistemaVerificacion}.`;
  }
};
