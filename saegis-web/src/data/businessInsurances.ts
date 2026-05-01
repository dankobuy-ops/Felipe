export interface InsuranceTab {
  label: string;
  content: string;
}

export interface BusinessInsurance {
  slug: string;
  title: string;
  summary: string;
  tabs: InsuranceTab[];
}

export const businessInsurances: BusinessInsurance[] = [
  {
    slug: "accidentes-personales",
    title: "Accidentes Personales",
    summary:
      "Este seguro está diseñado para entregar un respaldo económico importante si una persona sufre un accidente grave. Puede ser contratado por una empresa para sus trabajadores o por una persona para sí misma.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Apoyo en lo Peor: Si un accidente causa el fallecimiento, la familia (beneficiarios) recibe un monto de dinero (UF) para enfrentar el futuro.\nInvalidez: Si el accidente deja secuelas graves que impiden seguir trabajando (invalidez 2/3), se paga el capital al asegurado.\nGastos Médicos: Ayuda a pagar las cuentas de la clínica o hospital que no cubrió tu Isapre o Fonasa (si se contrata esta cobertura).\nHospitalización: Paga un monto por cada día que debas estar hospitalizado por un accidente, para cubrir gastos extra.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Accidente: Sufres una lesión traumática e involuntaria (caída, choque, golpe).\nAtención Médica: Acudes a un centro médico. Es vital que el médico certifique que las lesiones son por accidente.\nDenuncia: Avisas a la compañía de seguros y presentas los documentos (informes, boletas, certificado de defunción si aplica).\nPago: La compañía evalúa el caso y paga la indemnización correspondiente a los beneficiarios o al asegurado.",
      },
      {
        label: "Requisitos para la Cobertura",
        content:
          "Que sea un Accidente: Debe ser un evento súbito y externo. No cubre infartos, ataques cerebrovasculares o enfermedades repentinas (salvo excepciones muy específicas).\nJornada (en Colectivos): Verificar si te cubre solo en el trabajo/trayecto o las 24 horas del día (incluso fin de semana).\nDenuncia Oportuna: Debes avisar del accidente dentro del plazo establecido (usualmente 30 días).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes bajo influencia del alcohol o drogas.\nDeportes de alto riesgo (paracaidismo, automovilismo, buceo, etc.) a menos que se especifique lo contrario.\nLesiones autoinferidas o suicidio.\nHernias, lumbagos o tirones musculares no causados por un golpe directo.\nEnfermedades preexistentes.",
      },
    ],
  },
  {
    slug: "asiento-pasajero",
    title: "Asiento Pasajero",
    summary:
      "Este seguro protege a todas las personas que viajan en tu vehículo (incluido el conductor) en caso de un accidente de tránsito. Es un complemento vital al Seguro Obligatorio (SOAP).",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección ante Fallecimiento: Si ocurre un accidente fatal, el seguro entrega una indemnización económica (UF) a la familia de cada pasajero fallecido.\nApoyo en Invalidez: Si un pasajero queda con secuelas permanentes o invalidez a causa del accidente, recibe un capital para su sustento.\nCobertura Médica: (Si se contrata, ej. Plan C) Ayuda a pagar gastos médicos (clínica, remedios) que no cubra tu Isapre/Fonasa ni el SOAP, hasta un tope (ej. UF 50).",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Accidente: El vehículo asegurado sufre un siniestro con ocupantes en su interior.\nAtención y Constancia: Se debe trasladar a los heridos al centro asistencial y llamar a Carabineros de inmediato para dejar constancia policial (obligatorio).\nDenuncia: El propietario del vehículo debe avisar a la compañía de seguros.\nPago: La compañía evalúa los antecedentes y paga las indemnizaciones a los afectados o sus familias.",
      },
      {
        label: "Requisitos para la Cobertura",
        content:
          "Capacidad del Vehículo: El seguro cubre hasta el número de asientos declarado (ej. 14 pasajeros). No transportes más personas de lo permitido.\nLicencia de Conducir: El conductor debe tener su licencia al día y competente para el tipo de vehículo (ej. Clase A para transporte de pasajeros).\nAlcohol y Drogas: La cobertura no opera si el conductor está bajo la influencia del alcohol o drogas.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes causados por dolo (intención) del conductor.\nVehículos usados para fines distintos al declarado (ej. usar un auto particular como transporte público sin avisar).\nPasajeros que viajen en lugares no habilitados (pick-up de camionetas, pisaderas, etc.).",
      },
    ],
  },
  {
    slug: "credito",
    title: "Crédito",
    summary: "",
    tabs: [
      { label: "Principales Beneficios", content: "" },
      { label: "¿Cómo funciona?", content: "" },
      { label: "Requisitos para la Cobertura", content: "" },
      { label: "Lo que NO Cubre", content: "" },
    ],
  },
  {
    slug: "equipo-movil-agricola",
    title: "Equipo Móvil Agrícola",
    summary:
      "Este seguro protege tu inversión en maquinaria (tractores, cosechadoras) contra daños accidentales y protege tu patrimonio si dañas a otros con ellas.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Reparación de la Máquina: Si tu tractor choca, se vuelca, se incendia o le cae un árbol encima, el seguro paga la reparación.\nRobo: Si te roban la máquina del predio, estás cubierto.\nResponsabilidad Civil: Si operando el tractor golpeas una camioneta vecina o dañas un cerco ajeno, el seguro paga esos daños (hasta UF 500).\nRepuestos Rápidos: Si se necesita traer un repuesto urgente en avión por un siniestro, el seguro ayuda con ese costo extra.\nCirculación: Te cubre no solo trabajando en el campo, sino también trasladándote por caminos públicos (si se incluye la cláusula).",
      },
      {
        label: "Guía de Uso",
        content:
          "Protege la Máquina: Si hay un accidente, toma medidas razonables para evitar que el daño aumente (ej. apagar fuego, evitar saqueo), pero sin arriesgarte.\nDenuncia Policial: En caso de Robo o si hay lesionados (choque en camino público), llama a Carabineros de inmediato.\nAvisa a la Compañía: Tienes un plazo breve (inmediato o máx. 10 días) para avisar. No repares nada sin autorización del liquidador.\nPresupuesto: Cotiza la reparación y presenta el presupuesto al liquidador asignado.",
      },
      {
        label: "Tus Obligaciones",
        content:
          "Mantención: Debes mantener la máquina en buen estado mecánico. El seguro no paga fallas por falta de aceite o mantención.\nOperadores: Los conductores deben ser idóneos y tener licencia si circulan por caminos públicos.\nDeducible: Recuerda que en cada siniestro de daños o robo tú pagas las primeras UF 20 (aprox. $750.000).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Fallas Mecánicas: Si se rompe el motor por uso, se corta una correa o falla la transmisión por desgaste, eso es mantención, no seguro.\nPinchazos: Si solo se revienta un neumático, no tiene cobertura.\nDolo: Daños causados intencionalmente.",
      },
    ],
  },
  {
    slug: "equipo-movil-contratista",
    title: "Equipo Móvil Contratista",
    summary:
      "Este seguro protege tu inversión en maquinaria pesada o industrial (retroexcavadoras, grúas, rodillos) contra daños accidentales y protege tu patrimonio ante reclamos de terceros.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Todo Riesgo Daños Físicos: Si tu máquina choca, se vuelca, se incendia o cae a un barranco, el seguro cubre la reparación o reposición.\nRobo: Te protege si roban la maquinaria de la obra o lugar de guardado.\nResponsabilidad Civil: Si operando la máquina causas daños a una propiedad vecina, a un vehículo o lesiones a una persona, el seguro cubre esas indemnizaciones.\nGastos Extra: Cubre costos de rescate de la máquina y limpieza del lugar tras un accidente.",
      },
      {
        label: "Guía de Uso",
        content:
          "Seguridad Primero: Detén la operación y toma medidas para evitar que el daño aumente, pero sin arriesgarte.\nDenuncia Policial: En caso de Robo o si hay lesionados (especialmente en vía pública), llama a Carabineros de inmediato.\nAvisa a la Compañía: Tienes un plazo breve (inmediato o máx. 10 días) para avisar. No repares nada sin autorización del liquidador.\nPresupuesto: Cotiza la reparación y presenta el presupuesto al liquidador asignado.",
      },
      {
        label: "Tus Obligaciones",
        content:
          "Mantención: Debes mantener la máquina en buen estado mecánico. El seguro no paga fallas por falta de aceite, filtros o mantención.\nOperadores: Los operadores deben ser calificados y tener licencia (Clase D) al día.\nDeducible: Recuerda que en cada siniestro de daños o robo tú pagas una parte inicial (el deducible).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Fallas Mecánicas: Si se rompe el motor por uso, falla el sistema hidráulico por desgaste o se quema un fusible, eso es mantención, no seguro.\nPinchazos: Si solo se revienta un neumático, no tiene cobertura.\nSobrecarga: Daños por levantar más peso del permitido por el fabricante.\nTerrenos Pantanosos: Hundimiento en terrenos no aptos para la máquina.",
      },
    ],
  },
  {
    slug: "garantia",
    title: "Garantía",
    summary: "",
    tabs: [
      { label: "Principales Beneficios", content: "" },
      { label: "¿Cómo funciona?", content: "" },
      { label: "Requisitos para la Cobertura", content: "" },
      { label: "Lo que NO Cubre", content: "" },
    ],
  },
  {
    slug: "instalaciones-electricas",
    title: "Instalaciones Eléctricas",
    summary:
      "Este seguro protege tu inversión en equipos electrónicos (computadores, servidores, equipos médicos) contra daños accidentales, robo y problemas eléctricos.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Todo Riesgo: Si a tu equipo se le cae un café, se golpea, sufre un alza de voltaje o se incendia, el seguro cubre la reparación.\nRobo: Estás cubierto si entran a robar a tu oficina o casa.\nEquipos Móviles: Si contratas la extensión, tus notebooks y tablets están protegidos también cuando los sacas a la calle o viajas dentro de Chile.\nSismo y Naturaleza: Cubre daños por terremoto o inundación (si se incluye).\nGastos Extra: Si necesitas reparar urgente un equipo crítico, el seguro puede cubrir flete aéreo de repuestos u horas extra del técnico.",
      },
      {
        label: "Guía de Uso",
        content:
          "Protege el Equipo: Desconecta el equipo si hay riesgo eléctrico o de agua para evitar mayores daños.\nDenuncia Policial: En caso de Robo, llama a Carabineros de inmediato y haz la denuncia detallando los equipos sustraídos.\nAvisa a la Compañía: Tienes un plazo breve para avisar. No mandes a reparar sin autorización del liquidador.\nInforme Técnico: Consigue un informe técnico de un servicio autorizado que indique la causa del daño y el presupuesto de reparación.",
      },
      {
        label: "Tus Obligaciones",
        content:
          "Inventario: Mantén actualizada la lista de tus equipos asegurados. Si compras uno nuevo, avisa para incluirlo.\nSeguridad: Mantén las medidas de seguridad (alarmas, chapas) operativas.\nRespaldos: Haz copias de seguridad de tu información frecuentemente. El seguro cubre el equipo físico, pero recuperar los datos es tu responsabilidad (salvo cobertura especial).\nDeducible: En cada siniestro pagarás una parte inicial (ej. UF 5).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Desgaste: Si el equipo falla por viejo o por uso normal, no está cubierto.\nSoftware: Los virus informáticos o fallas de programas no se cubren.\nGarantía: Si el daño lo cubre la garantía del fabricante, debes usar esa primero.\nEstética: Rayones o abolladuras que no impidan que el equipo funcione.",
      },
    ],
  },
  {
    slug: "proteccion-financiera",
    title: "Protección Financiera",
    summary:
      "Este seguro está diseñado para apoyar a la empresa y a sus colaboradores frente a las consecuencias económicas de un accidente grave, entregando un beneficio adicional a la cobertura legal obligatoria.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección 24 Horas: Protege a los trabajadores no solo en el trabajo, sino también en su vida privada (según plan contratado).\nApoyo en Fallecimiento: Entrega un capital (UF) a la familia del trabajador en caso de muerte accidental.\nRespaldo en Invalidez: Indemniza al trabajador si un accidente le provoca una invalidez permanente que le impida seguir trabajando.\nGastos Médicos: Puede ayudar a cubrir gastos médicos de accidentes que no estén cubiertos por la Mutual o Isapre/Fonasa.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Accidente: Un trabajador sufre un accidente (laboral o no, según plan).\nAtención y Aviso: El trabajador recibe atención médica. La empresa debe ser notificada.\nDenuncia: La empresa avisa a la compañía de seguros y presenta los antecedentes (certificados, gastos).\nPago: La aseguradora paga la indemnización correspondiente a la empresa (para reembolso) o directamente a los beneficiarios.",
      },
      {
        label: "Requisitos para la Cobertura",
        content:
          "Nómina al Día: Los trabajadores deben estar incluidos en la lista asegurada.\nCausa Accidental: Debe ser un evento súbito y externo. No cubre enfermedades comunes.\nDenuncia: Avisar dentro del plazo establecido en la póliza.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes provocados intencionalmente por el trabajador o el empleador.\nAccidentes bajo influencia de alcohol o drogas.\nEnfermedades profesionales o comunes (salvo pacto específico).\nMultas o sanciones laborales.",
      },
    ],
  },
  {
    slug: "pyme-incendio",
    title: "PYME (Incendio)",
    summary:
      "Este seguro está diseñado para proteger el patrimonio de tu empresa (local, mercadería, equipos) frente a múltiples riesgos, permitiéndote recuperar la operación rápidamente tras un accidente.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección de Activos: Si hay un incendio, terremoto o inundación, el seguro paga la reparación o reconstrucción de tu local y la reposición de tus mercaderías y muebles.\nRobo: Te indemniza si entran a robar a tu negocio rompiendo accesos o asaltando al personal.\nResponsabilidad Civil: Si un cliente se accidenta en tu local o tu actividad causa daños a vecinos, el seguro cubre esas indemnizaciones.\nEquipos: Protege tus computadores y maquinaria clave contra daños accidentales o eléctricos.\nContinuidad: (Si se contrata) Cubre la pérdida de ingresos mientras tu negocio está cerrado por reparaciones tras un siniestro.\nAsistencias: Servicios de emergencia 24/7 (gasfíter, eléctrico, cerrajero) para problemas en el local.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Evento: Incendio, robo, rotura de cañería, etc.\nMitigación: Toma medidas seguras para evitar que el daño aumente (ej. cortar agua, llamar a bomberos/carabineros).\nDenuncia: Avisa a la compañía de seguros de inmediato. En caso de robo, la constancia en Carabineros es obligatoria e inmediata.\nLiquidación: Un liquidador evaluará los daños y la compañía pagará la indemnización (descontando el deducible).",
      },
      {
        label: "Requisitos Clave",
        content:
          "Medidas de Seguridad: Debes mantener operativas las alarmas, cerraduras y extintores. Si declaraste tener alarma y no funcionaba en el robo, podrían no cubrirte.\nInventario: Mantén un registro actualizado de tus bienes y mercaderías.\nMantención: El local y sus instalaciones (eléctricas, agua) deben estar en buen estado.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Hurtos simples (robos sin fuerza ni violencia, \"descuidos\").\nDaños por falta de mantención o desgaste natural.\nDineros o valores a la vista (salvo en caja fuerte o remesa si se contrató).\nActos dolosos (intencionales) del asegurado o sus socios.",
      },
    ],
  },
  {
    slug: "rc-construccion-mop",
    title: "Responsabilidad Civil Construcción/MOP",
    summary:
      "Este seguro protege el patrimonio de tu empresa constructora frente a reclamos por daños que puedan ocurrir durante la ejecución de tus proyectos.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Daños a Terceros: Si una grúa cae sobre una casa vecina, o un peatón se lesiona por caída de materiales, el seguro cubre la indemnización.\nAccidentes de Trabajadores: Protege a la empresa si un trabajador demanda por un accidente laboral (en exceso de la mutual).\nDaños a Servicios: Si rompes una cañería de agua o un cable de luz subterráneo, el seguro cubre la reparación (si tenías los planos).\nDefensa Legal: La aseguradora pone abogados y paga los gastos del juicio si te demandan por un accidente de la obra.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Accidente: Pasa algo en la obra que daña a un tercero o a un trabajador.\nNo Hagas Arreglos: No ofrezcas dinero ni aceptes la culpa en el momento.\nAvisa a la Compañía: Denuncia el hecho lo antes posible.\nDefensa y Pago: La aseguradora evaluará, te defenderá si es necesario y pagará la indemnización que corresponda.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Seguridad en Obra: Debes cumplir con todas las normas de seguridad y prevención de riesgos.\nPlanos: Para que cubra daños subterráneos, debes haber consultado los planos de servicios antes de excavar.\nSubcontratistas: Si tienes la cobertura de RC Cruzada, tus subcontratistas también están protegidos frente a reclamos entre ellos.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños a la propia obra (eso es otro seguro: Todo Riesgo Construcción).\nMultas o sanciones administrativas.\nDaños causados a propósito.\nRetrasos en la entrega de la obra.",
      },
    ],
  },
  {
    slug: "rc-directores-copropiedades",
    title: "Responsabilidad Civil Directores y Administradores de Copropiedades",
    summary:
      "Ser parte del Comité de Administración es una responsabilidad grande. Ustedes toman decisiones sobre dineros, contratos y normas de convivencia. Si alguien (un copropietario, un proveedor o la inmobiliaria) cree que una decisión fue equivocada y les causó una pérdida económica, pueden demandarlos personalmente. Este seguro está para evitar que paguen con su propio bolsillo.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Su Patrimonio Personal: Si un vecino demanda al presidente del comité alegando que una mala decisión hizo bajar el valor de su propiedad, el seguro paga la defensa y la eventual indemnización.\nGastos de Abogados: Los juicios son caros, aunque uno sea inocente. Esta póliza paga los abogados expertos para defenderlos ante demandas civiles, laborales (si se incluye) o administrativas.\nErrores de Gestión: Cubre negligencias, omisiones o errores involuntarios en la administración del edificio (ej. error en la contratación de un servicio que genera pérdidas).",
      },
      {
        label: "Ejemplo de cuándo se usa",
        content:
          "Demandas de Copropietarios: Un grupo de vecinos demanda al Comité alegando que los gastos comunes están mal calculados o que se malgastaron fondos de reserva.\nProblemas con Proveedores: Una empresa de mantención demanda por término injustificado de contrato.\nConflictos Laborales: El conserje demanda por despido injustificado y acusa al administrador de acoso laboral (si se contrata la cláusula laboral).",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Reciben un Reclamo: Llega una carta de abogado, una citación o una demanda dirigida contra un miembro del comité o el administrador.\nNo Responda Solo: No admita culpas ni ofrezca pagos.\nAviso Inmediato: Avise a la aseguradora de inmediato.\nDefensa: La compañía asignará abogados para defenderlos y cubrirá los gastos.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Robos o Desfalcos: Si un administrador se roba la plata, esto no lo cubre (eso es un delito).\nMultas: Si la Inspección del Trabajo o el Juzgado de Policía Local les pasa una multa, el seguro no la paga.\nAccidentes Físicos: Si alguien se cae en la escalera, eso lo ve el Seguro de Espacios Comunes, no este.",
      },
    ],
  },
  {
    slug: "rc-empresa-general",
    title: "Responsabilidad Civil Empresa/General",
    summary:
      "Este seguro protege el patrimonio de tu empresa frente a reclamos o demandas de terceros que hayan sufrido daños por culpa de tu actividad comercial, tus empleados o tus instalaciones.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Daños a Terceros: Si un cliente se cae en tu local, una máquina tuya daña la propiedad de un vecino, o tu carga causa un accidente, el seguro cubre la indemnización.\nAccidentes Laborales: Protege a la empresa si un trabajador demanda por un accidente laboral grave (en exceso de la mutual), alegando falta de medidas de seguridad.\nDefensa Legal: La aseguradora pone abogados expertos y paga los gastos del juicio si te demandan por responsabilidad civil.\nVehículos de la Empresa: Puede cubrir daños causados por tus vehículos de trabajo que superen los topes de tu seguro automotriz normal.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Incidente: Pasa algo en tu empresa o faena que daña a alguien (cliente, vecino, trabajador).\nNo Hagas Arreglos: No ofrezcas dinero ni aceptes la culpa en el momento. Di que tienes seguro y que la compañía evaluará.\nAvisa a la Compañía: Denuncia el hecho lo antes posible.\nDefensa y Pago: La aseguradora evaluará, te defenderá si es necesario y pagará la indemnización que corresponda al afectado.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Seguridad: Debes cumplir con todas las normas legales y de seguridad de tu rubro.\nContratos: Si usas subcontratistas, asegúrate de que también tengan sus seguros o que tu póliza los cubra (RC Cruzada).\nVeracidad: La actividad que realizas debe coincidir con lo que dice la póliza.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños a tus propios bienes (eso es seguro de Incendio/Robo).\nMultas o sanciones administrativas.\nDaños causados a propósito (dolo).\nResponsabilidad contractual (incumplimiento de contratos, plazos, calidad).",
      },
    ],
  },
  {
    slug: "rc-evento",
    title: "Responsabilidad Civil Evento",
    summary:
      "Este seguro protege el patrimonio de tu empresa u organización frente a reclamos por daños que puedan ocurrir durante la realización de tus eventos.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Daños a Asistentes: Si un asistente se lesiona (ej. caída por cable suelto, estructura que cede), el seguro cubre la indemnización.\nDaños a la Propiedad: Si durante el evento se daña el recinto arrendado o propiedades vecinas, estás cubierto.\nAccidentes de Trabajadores: Protege a la organización si un trabajador demanda por un accidente laboral (en exceso de la mutual).\nDefensa Legal: La aseguradora pone abogados y paga los gastos del juicio si te demandan por responsabilidad civil.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Ocurre el Incidente: Pasa algo en el evento que daña a un tercero (asistente, proveedor, trabajador).\nNo Hagas Arreglos: No ofrezcas dinero ni aceptes la culpa en el momento. Di que tienes seguro y que la compañía evaluará.\nAvisa a la Compañía: Denuncia el hecho lo antes posible.\nDefensa y Pago: La aseguradora evaluará, te defenderá si es necesario y pagará la indemnización que corresponda.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Seguridad: Debes cumplir con todas las normas de seguridad exigidas para eventos (aforo, vías de evacuación, instalaciones eléctricas certificadas).\nPermisos: El evento debe contar con los permisos municipales y de autoridad correspondientes.\nMontaje: Las estructuras (escenarios, carpas) deben estar correctamente instaladas y certificadas si corresponde.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Cancelación del evento (eso es otro seguro).\nMultas o sanciones administrativas.\nDaños causados a propósito.\nHurtos o robos de bienes de los asistentes (salvo custodia declarada).",
      },
    ],
  },
  {
    slug: "salud-complementario",
    title: "Salud Complementario",
    summary:
      "Este seguro es un beneficio que la empresa entrega a sus colaboradores para ayudarlos a pagar los gastos médicos que no cubre completamente su Isapre o Fonasa.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Reembolso de Gastos Médicos: El seguro devuelve una parte importante (ej. 70% u 80%) de lo que el trabajador paga de su bolsillo en consultas, exámenes y hospitalizaciones.\nCobertura Dental: Ayuda a pagar tratamientos dentales, que suelen ser costosos y tener poca cobertura previsional.\nSeguro de Vida: Entrega un monto de dinero a la familia del trabajador en caso de fallecimiento, otorgando tranquilidad financiera.\nMedicamentos: Reembolsa parte del gasto en farmacias (con receta).\nCobertura Catastrófica: Si hay una enfermedad muy grave y costosa, el seguro tiene una capa extra de protección para evitar el endeudamiento.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Atención Médica: El trabajador va al médico y paga usando su previsión (bono).\nActivación Automática (Huella): En muchas clínicas y farmacias, al poner la huella, el seguro complementario se aplica automáticamente y el trabajador paga solo el saldo final.\nReembolso Manual: Si no hay sistema automático, el trabajador guarda la boleta y el bono, y los presenta a la compañía (vía web o app) para que le depositen el reembolso.\nDeducible: Cada año, el trabajador debe cubrir un monto pequeño inicial (ej. $35.000) con sus copagos antes de recibir reembolsos.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Ser Trabajador Activo: El seguro es para empleados con contrato vigente.\nPrevisión al Día: Se debe tener Isapre o Fonasa activa. El seguro no reemplaza a la previsión, la complementa.\nIncorporar Cargas: El trabajador puede inscribir a su cónyuge e hijos (pagando la prima adicional si corresponde).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Tratamientos estéticos o cosméticos.\nCirugías para obesidad (salvo que sea por salud y cumpla requisitos estrictos).\nMedicamentos sin receta médica.\nGastos que la Isapre/Fonasa no cubra en absoluto (salvo excepciones como algunos dentales).",
      },
    ],
  },
  {
    slug: "transporte",
    title: "Transporte",
    summary:
      "Este seguro protege tus mercaderías mientras son trasladadas dentro de Chile (Cabotaje), cubriendo las pérdidas económicas si el camión sufre un accidente grave.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Accidentes del Camión: Si el vehículo que lleva tu carga choca, se vuelca, se incendia o cae a un río, el seguro paga la mercadería dañada.\nDesastres Naturales: Cubre daños a la carga por terremotos, derrumbes o inundaciones que afecten la ruta.\nRobo (Opcional): Si se contrata, te protege si asaltan el camión o roban la carga con fuerza (rompiendo sellos o cerraduras). Ojo: suele tener un tope de monto menor a la carga total.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Durante el Viaje: La cobertura comienza cuando la carga se sube al camión y termina cuando se baja en el destino final.\nOcurre un Siniestro: Si hay un accidente o robo en la ruta.\nMedidas Inmediatas: El conductor debe dejar constancia en Carabineros (obligatorio en robo o choque) y tomar fotos de la carga dañada.\nNo Recibir \"Conforme\": Si recibes carga dañada, debes anotar los daños en la guía de despacho. Si firmas \"conforme\", es difícil reclamar después.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Embalaje: La carga debe ir bien protegida y embalada para soportar el viaje. Daños por mal embalaje no se pagan.\nVehículo Apto: El camión debe estar en buen estado y con revisión técnica al día.\nAntigüedad: Los camiones no deben ser excesivamente antiguos (generalmente tope 20-30 años).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Mermas Naturales: Pérdida de peso o volumen normal por el viaje.\nDemoras: Si el camión llega tarde y pierdes una venta, eso no se cubre.\nMala Estiba: Daños porque la carga se movió dentro del camión por estar mal amarrada (salvo que el camión choque o vuelque).",
      },
    ],
  },
  {
    slug: "todo-riesgo-construccion",
    title: "Todo Riesgo Construcción",
    summary:
      "Este seguro protege la inversión en tu proyecto de construcción frente a accidentes que dañen la obra y protege tu patrimonio ante reclamos de vecinos o terceros.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección de la Obra: Si un incendio, terremoto, inundación, robo o accidente daña lo que estás construyendo (o los materiales en cancha), el seguro paga la reconstrucción.\nDaños a Terceros: Si una grúa golpea la casa del vecino, o una excavación causa grietas en la vereda pública, el seguro cubre esas indemnizaciones.\nLimpieza: Si hay un siniestro, el seguro ayuda a pagar el retiro de escombros para que puedas seguir trabajando.\nEquipos: Puede cubrir daños a la maquinaria y herramientas que usas en la obra (si se incluye).\nRC Cruzada: Si tienes varios subcontratistas y uno daña el trabajo del otro, esta cobertura permite que el seguro opere (considerándolos terceros entre sí).",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Durante la Obra: La cobertura inicia cuando llegan los materiales o empieza el trabajo, y termina cuando entregas la obra (recepción provisoria).\nOcurre un Siniestro: Un muro se cae, se roban materiales instalados, hay un incendio.\nMedidas Inmediatas: Debes tomar acciones para evitar que el daño crezca (mitigación) y avisar a la aseguradora inmediatamente.\nLiquidación: Un experto evaluará los daños y el costo de repararlos para volver al estado anterior al siniestro.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Valor Real: Debes asegurar el valor total del contrato. Si aseguras por menos para ahorrar prima, en caso de siniestro te pagarán menos proporcionalmente (prorrateo).\nPlazos: Si la obra se atrasa, debes avisar para extender el seguro. Si el seguro vence y la obra sigue, no tienes cobertura.\nSeguridad: Debes mantener cercos, vigilancia y medidas de seguridad adecuadas en la faena.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Errores de Diseño: Si el edificio se cae porque fue mal diseñado por el arquitecto o ingeniero, el seguro de construcción generalmente no lo cubre (eso es responsabilidad profesional).\nAtrasos: Multas por no terminar a tiempo, aunque sea por un incendio.\nMala Calidad: Reparar trabajos mal hechos o con materiales defectuosos.",
      },
    ],
  },
  {
    slug: "vehiculos",
    title: "Vehículos",
    summary:
      "Este seguro está diseñado para vehículos que trabajan (furgones, camionetas de reparto, camiones). Protege tu activo principal y te blinda ante demandas de terceros.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección de tu Capital: Si tu vehículo de trabajo choca, se vuelca o se incendia, el seguro paga la reparación o te indemniza si es pérdida total, permitiéndote recuperar tu herramienta de trabajo.\nResponsabilidad Civil: Si tu vehículo causa daños a otros (choque a otro auto, atropello, daños a una casa), el seguro paga esas indemnizaciones, protegiendo el patrimonio de tu empresa.\nRobo: Te cubre si roban el vehículo o sus accesorios (según plan).\nAsistencia en Ruta: Servicio de grúa y ayuda mecánica (revisa los límites de tonelaje de tu plan, las grúas para camiones son distintas a las de autos).\nDefensa Legal: Abogados para defender a tu conductor o empresa en juicios por accidentes.",
      },
      {
        label: "Guía de Uso ante un siniestro",
        content:
          "Seguridad y Denuncia: Verifica heridos. Llama a Carabineros de inmediato para dejar constancia o denuncia (obligatorio en lesiones y robo).\nAvisa a la Aseguradora: Tienes un plazo (generalmente 10 días) para avisar. Hazlo lo antes posible para activar la asistencia o el taller.\nNo Asumas Culpa: Instruye a tus choferes para que nunca negocien ni acepten responsabilidad en el lugar. Eso lo ve la aseguradora.\nDocumentación: Ten a mano el padrón, la licencia del conductor (¡debe ser la correcta profesional!) y la revisión técnica al día.",
      },
      {
        label: "Tus Obligaciones",
        content:
          "Licencias Profesionales: Tus conductores deben tener la licencia Clase A correspondiente al vehículo y carga. Si maneja alguien con licencia Clase B un camión que requiere A4, no hay cobertura.\nCarga Correcta: No sobrecargues el vehículo. Los accidentes por exceso de carga no se cubren.\nGPS: Si tu póliza lo exige, debes tener el GPS instalado y funcionando. Si te roban el camión y el GPS estaba apagado, el seguro podría no pagar o aplicar un deducible muy alto.\nMantención: El vehículo debe estar en buen estado mecánico y con revisión técnica vigente.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños por conducir bajo influencia del alcohol o drogas.\nDaños a la propia carga (necesitas un Seguro de Transporte de Carga aparte para eso).\nDesgaste natural o fallas mecánicas (ej. motor fundido por falta de aceite).\nUso distinto al declarado (ej. usar un furgón de carga para transporte escolar sin avisar).",
      },
    ],
  },
  {
    slug: "vida-guardias-os10",
    title: "Vida Guardias (OS10)",
    summary:
      "Este seguro es un requisito legal para que tus guardias, conserjes o nocheros puedan obtener o renovar su credencial OS-10. Además, entrega una protección económica importante a sus familias.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Cumplimiento OS-10: Entrega el certificado necesario para acreditar a tu personal ante Carabineros.\nCobertura de Vida: Si el trabajador fallece por cualquier causa (enfermedad o accidente), se paga un monto (ej. UF 250) a su familia.\nProtección ante Accidentes: Si sufren un accidente (en el trabajo o trayecto, y en su vida privada si es plan 24h) que cause muerte o invalidez, se paga una indemnización adicional.\nInvalidez: Si un accidente los deja incapacitados para trabajar, reciben un capital para su sustento.",
      },
      {
        label: "¿Cómo funciona?",
        content:
          "Contratación: Debes enviarnos la lista completa de tu personal (RUT, Nombre, Fecha Nacimiento).\nCertificado: Te entregamos el certificado de cobertura para presentar en la Autoridad Fiscalizadora.\nSiniestro: Si ocurre un accidente o fallecimiento, se debe avisar a la aseguradora y presentar los documentos (certificado de defunción, parte policial, dictamen de invalidez).\nPago: La compañía paga directamente a los beneficiarios legales o al trabajador.",
      },
      {
        label: "Requisitos Clave",
        content:
          "Nómina Actualizada: Si contratas un guardia nuevo, debes avisar para incluirlo en el seguro antes de que empiece a trabajar o tramitar su credencial.\nSin Armas: Este seguro estándar es para guardias sin porte de armas. Si usan armas, el riesgo es distinto y debes avisar.\nPago al Día: La póliza debe estar pagada para que el certificado sea válido.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes provocados intencionalmente por el asegurado.\nAccidentes bajo influencia del alcohol o drogas.\nSuicidio (generalmente tiene un periodo de carencia de 1 o 2 años para la cobertura de Vida).\nEnfermedades preexistentes (para la cobertura de Vida, según condiciones).",
      },
    ],
  },
];
