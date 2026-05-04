export interface InsuranceTab {
  label: string;
  content: string;
}

export interface PersonaInsurance {
  slug: string;
  title: string;
  summary: string;
  tabs: InsuranceTab[];
}

export const personasInsurances: PersonaInsurance[] = [
  {
    slug: "asistencia-en-viajes",
    title: "Asistencia en Viajes",
    summary:
      "Este seguro actúa como un sistema de respaldo ante imprevistos. Su función no se limita al pago de cuentas médicas, sino que abarca la resolución de problemas logísticos complejos.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Salud 24/7: La cobertura abarca desde patologías simples hasta cirugías complejas, incluyendo atención por COVID-19 y acceso a telemedicina para consultas remotas.\nVuelo y Equipaje: Se otorgan compensaciones económicas en situaciones de demora prolongada de vuelos, imposibilidad de embarque por causas cubiertas, o no llegada del equipaje.\nProtección Legal: En caso de problemas legales derivados de un accidente, se facilita acceso a abogados y, en situaciones calificadas, anticipos para fianzas.\nRegreso Inesperado: Se cubre la logística de retorno anticipado si ocurre un evento grave en el domicilio del asegurado.",
      },
      {
        label: "Guía de Uso",
        content:
          "Prestación Directa (Aviso Previo): Antes de acudir a un centro médico o adquirir medicamentos, es necesario contactar a la Central de Asistencia (vía WhatsApp o Teléfono). La central coordina el pago directo e indica el lugar de atención.\nUrgencia Vital: Si existe riesgo de vida y no es posible la comunicación previa, se debe acudir al centro médico más cercano. Es obligatorio dar aviso dentro de las 24 horas siguientes para activar la cobertura.\nReembolsos: Si se realiza un pago directo (previa autorización), es indispensable conservar toda la documentación original (recetas, boletas, informes médicos, tickets de equipaje) para gestionar la devolución posterior.",
      },
      {
        label: "Exclusiones",
        content:
          "Enfermedades crónicas o preexistentes (salvo la primera atención de urgencia vital).\nAccidentes ocurridos bajo la influencia del alcohol, drogas, o derivados de riñas.\nPráctica de deportes extremos o profesionales (salvo especificación contraria en el plan).\nChequeos médicos de rutina, tratamientos estéticos o lentes.",
      },
      {
        label: "Deberes del Asegurado",
        content:
          "Aviso Oportuno: La falta de comunicación con la Central de Asistencia puede derivar en la pérdida de cobertura o la asunción de costos por parte del usuario.\nVeracidad: Es obligatorio declarar información veraz sobre el estado de salud (enfermedades preexistentes) y las circunstancias de cualquier siniestro.\nGestión Inmediata: En caso de pérdida o daño de equipaje, el reclamo debe efectuarse ante la aerolínea (formulario PIR) antes de abandonar el aeropuerto. Este documento es requisito para la activación del seguro.",
      },
    ],
  },
  {
    slug: "bicicleta",
    title: "Bicicleta",
    summary:
      "Este seguro está diseñado para proteger la inversión en la bicicleta y brindar respaldo ante situaciones imprevistas como robos violentos o accidentes graves. Tope monto asegurado: UF 100.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Protección ante Robo: Se indemniza la bicicleta si es robada mediante fuerza (rompiendo el candado/puerta) o intimidación (asalto).\nPérdida Total por Accidente: Si la bicicleta sufre daños graves en un accidente y la reparación es muy costosa (más del 75% del valor), se considera pérdida total.\nResponsabilidad Civil: Cobertura ante reclamos de terceros si se causa un accidente, daño a otro vehículo o lesión a un peatón.\nDefensa Legal: Apoyo con gastos de abogados si el accidente deriva en un proceso legal.",
      },
      {
        label: "Requisitos Obligatorios",
        content:
          "En la Calle: La bicicleta debe estar siempre sujeta por el marco a un objeto fijo (poste, bicicletero anclado) mediante un candado de seguridad homologado (Nivel de seguridad 8 o superior).\nEn Bodega o Casa: El lugar debe estar cerrado y, aun dentro de la bodega, la bicicleta debe estar asegurada a un objeto fijo.",
      },
      {
        label: "Protocolo ante Siniestro",
        content:
          "Robo — Acción Inmediata: Acudir a la unidad policial (Carabineros/PDI) más cercana de inmediato (idealmente dentro de las 2 horas). Dejar constancia detallando la fuerza ejercida (candado roto, chapa forzada) o la violencia sufrida. Avisar a la compañía de seguros (plazo máximo habitual: 5 días).\nAccidente — Documentación: Tomar fotografías de los daños en el lugar del hecho. Guardar la bicicleta (o sus restos); no deshacerse de ella ni repararla sin autorización.\nDocumentos a Presentar: Parte Policial (obligatorio en robo). Boleta o Factura de compra (para acreditar propiedad y valor). Fotos de los daños o del candado vulnerado.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Hurto Simple: Si la bicicleta se deja sin candado o desaparece por descuido sin que haya violencia o fuerza.\nUso Comercial: Si la bicicleta se usa para delivery o reparto.\nUso Competitivo: Carreras, descenso (downhill) o acrobacias.\nDaños Menores: Si solo se pincha una rueda o se daña un componente menor y el costo de reparación es bajo.",
      },
    ],
  },
  {
    slug: "catastrofico",
    title: "Catastrófico: Protección para Enfermedades Graves",
    summary:
      "Este seguro funciona como un \"paracaídas financiero\". Su objetivo es proteger el patrimonio familiar ante enfermedades o accidentes de muy alto costo que podrían desestabilizar la economía del hogar.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Cobertura Millonaria: Acceso a montos de cobertura muy altos (ej. hasta UF 20.000) para financiar tratamientos largos y costosos.\n100% de Cobertura Post-Deducible: Una vez superado el monto del deducible (UF 100), el seguro se hace cargo de la totalidad de los gastos médicos cubiertos.\nEnfermedades sin Deducible: Para diagnósticos críticos específicos (como Cáncer, Infartos o Trasplantes), la cobertura se activa de inmediato sin necesidad de pagar el deducible.\nLibre Elección: Permite atenderse en la clínica o centro médico de preferencia.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Primera Capa: Primero opera su sistema de salud (Isapre o Fonasa) y seguros complementarios si los tuviera.\nAcumulación de Copagos: La parte de la cuenta que no cubre la previsión (el copago) es de cargo del asegurado. Estos montos se van sumando o acumulando.\nSuperación del Deducible: El asegurado es responsable de pagar estos copagos acumulados hasta completar el monto del deducible.\nCobertura Total: En el momento en que los copagos acumulados por un mismo evento superan el deducible, el seguro cubre el 100% de los gastos restantes hasta el tope anual del plan.\nExcepción — Deducible Cero: Si el diagnóstico corresponde a una de las 8 enfermedades catastróficas definidas en la póliza (Cáncer, ACV, Infarto, etc.), se elimina el requisito del deducible.",
      },
      {
        label: "Requisitos para Cobertura",
        content:
          "Declaración de Salud Honesta: Al contratar, es obligatorio declarar cualquier enfermedad preexistente. Las enfermedades que ya tenía antes de contratar no estarán cubiertas.\nUso del Sistema Previsional: Para obtener la cobertura máxima (100%), es necesario hacer uso primero de su Isapre o Fonasa. Si no se usan, la cobertura del seguro disminuye (generalmente al 50%).\nNotificación: Ante un diagnóstico grave o accidente, se recomienda activar el seguro lo antes posible para coordinar beneficios y acumulaciones.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Enfermedades preexistentes (diagnosticadas antes de la contratación).\nCirugías estéticas o con fines de embellecimiento.\nTratamientos de fertilidad, obesidad o adicciones.\nGastos no médicos o suntuarios durante la hospitalización.",
      },
    ],
  },
  {
    slug: "deporte",
    title: "Deporte",
    summary:
      "Este seguro está diseñado para protegerte económicamente si sufres un accidente mientras practicas tu deporte favorito o en tu vida diaria. Su objetivo es apoyarte con indemnizaciones ante lesiones graves.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Respaldo en Caso Grave: Si un accidente te causa invalidez permanente o fallecimiento, tú o tu familia reciben un capital importante (ej. UF 1.000).\nApoyo por Fracturas: Si te fracturas un hueso en un accidente, recibes una indemnización para ayudar con los gastos o la recuperación.\nAyuda en Hospitalización: Si el accidente es serio y debes quedar hospitalizado, el seguro te paga un monto diario (después del primer día) para compensar gastos o ingresos perdidos.\nAsistencia 24/7: Acceso a orientación médica telefónica e información de salud útil.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Ocurre el Accidente: Sufres una lesión traumática e involuntaria (caída, golpe, choque).\nAtención Médica: Acudes a un centro médico para tu tratamiento. Debes solicitar todos los informes y certificados que acrediten el diagnóstico (ej. fractura, días de hospitalización).\nDenuncia: Avisas a la compañía de seguros y presentas los documentos.\nPago: La compañía evalúa el caso y te paga la indemnización correspondiente a tu cobertura.",
      },
      {
        label: "Requisitos para Cobertura",
        content:
          "Que sea un Accidente Real: Debe ser un evento súbito y externo. No cubre dolores de espalda por mala postura, tirones musculares espontáneos o enfermedades.\nPráctica Amateur: Generalmente cubre deportes practicados por recreación. Si compites profesionalmente o por dinero, podrías no tener cobertura.\nDenuncia Oportuna: Debes avisar del accidente dentro del plazo establecido (usualmente 30 días).",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes bajo influencia del alcohol o drogas.\nDeportes de alto riesgo (paracaidismo, automovilismo, boxeo, etc.) a menos que se especifique lo contrario.\nLesiones preexistentes (que ya tenías antes de contratar).\nSuicidio o autolesiones.\nHernias, lumbagos o tirones musculares no causados por un golpe directo.",
      },
    ],
  },
  {
    slug: "hogar",
    title: "Hogar",
    summary:
      "Este seguro está diseñado para que, si ocurre un desastre, no pierdas la inversión de tu vida. Cubre tanto la estructura de tu casa (Edificio) como las cosas que tienes dentro (Contenido).",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Incendio: Si el fuego daña tu casa, el seguro paga la reparación o reconstrucción. También cubre los daños por humo o el agua usada para apagarlo.\nSismo (Si se contrata): Cubre las grietas o derrumbes causados por un terremoto. Ten en cuenta que tiene un deducible alto (tú pagas una parte inicial).\nRobo: Te indemniza si entran a robar a tu casa rompiendo cosas (fuerza) o amenazando a las personas (violencia).\nCañerías: Si se rompe una cañería interna y el agua daña tus pisos o muros, el seguro cubre los daños.\nResponsabilidad Civil: Si tu perro muerde a un vecino o se cae una maceta sobre un auto, el seguro cubre esos gastos.\nAsistencias: Tienes maestros de urgencia gratis (gasfiter, electricista, cerrajero) para emergencias en el hogar.",
      },
      {
        label: "Guía de Uso",
        content:
          "En caso de Incendio: Llama a Bomberos y salva lo que puedas sin arriesgar tu vida.\nEn caso de Robo: Llama a Carabineros de inmediato. Debes hacer la denuncia policial detallando lo robado y los daños (puertas forzadas, vidrios rotos). Sin este papel, el seguro no paga.\nLlama a la Compañía: Tienes un plazo (generalmente 5 a 10 días) para avisar a la aseguradora.\nNo repares sin permiso: Saca fotos de todo, pero no botes cosas ni repares daños definitivos hasta que el liquidador lo autorice (salvo reparaciones de urgencia para evitar más daños).",
      },
      {
        label: "Obligaciones para tener Cobertura",
        content:
          "Casa Habitada: Si vas a dejar la casa sola por más de 30 días, debes avisar a la compañía. Si no avisas, se suspende la cobertura (especialmente robo).\nMedidas de Seguridad: Para que cubra el robo, debes tener chapas de seguridad y, si es casa o primer piso, rejas en las ventanas. Si tienes alarma declarada, debe estar conectada.\nMantención: Debes mantener tu casa en buen estado. El seguro no cubre goteras por techos viejos o falta de limpieza de canaletas.\nVerdad en los Datos: Debes declarar el material real de tu casa (sólido, madera, mixto) y si la usas para vivir o para negocio.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Desgaste natural por uso o el paso del tiempo.\nJoyas, dinero en efectivo o documentos de valor.\nDaños si la casa lleva mucho tiempo deshabitada.\nHurtos simples (si te roban porque dejaste la puerta abierta sin llave).",
      },
    ],
  },
  {
    slug: "movilidad",
    title: "Movilidad",
    summary:
      "Este seguro está diseñado para proteger tu integridad física mientras te mueves por la ciudad o realizas tus actividades diarias. Su objetivo es entregarte un respaldo económico inmediato si sufres lesiones por un accidente.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Respaldo ante lo Imprevisto: Si un accidente te causa invalidez permanente o fallecimiento, se paga un capital (ej. UF 500) para ti o tu familia.\nIndemnización por Fracturas: Si te caes o chocas y te fracturas un hueso, recibes un monto de libre disposición (ej. UF 30) para cubrir gastos o lo que necesites.\nApoyo si quedas Hospitalizado: Si el accidente requiere que te quedes hospitalizado, el seguro te paga una indemnización diaria (a partir del segundo día) para compensar los días que no puedas trabajar o los gastos extra.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Ocurre el Accidente: Sufres una lesión (caída en bicicleta, choque, atropello, etc.).\nAtención Médica: Vas a urgencias. Es fundamental que el médico certifique las lesiones y, si quedas hospitalizado, el certificado de ingreso y alta.\nDenuncia: Avisas a la compañía y entregas los documentos médicos.\nPago: Recibes el dinero correspondiente a la cobertura afectada directamente en tu cuenta.",
      },
      {
        label: "Requisitos para Cobertura",
        content:
          "Que sea un Accidente: Debe ser un evento externo y súbito. No cubre enfermedades, desmayos por salud o lesiones por sobreesfuerzo sin golpe.\nDenuncia a Tiempo: Avisar a la aseguradora dentro del plazo estipulado.\nDocumentación: Guardar radiografías, informes médicos y comprobantes de hospitalización.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Accidentes si estabas bajo los efectos del alcohol o drogas.\nLesiones o condiciones que ya tenías antes de contratar (preexistencias).\nAccidentes participando en carreras o competencias.\nSuicidio o lesiones autoinferidas.\nDaños materiales a tu vehículo o daños a otras personas (solo te cubre a ti).",
      },
    ],
  },
  {
    slug: "rci-mercosur",
    title: "RCI: Tu Pasaporte para Viajar en Auto por el Mercosur",
    summary:
      "Este seguro es obligatorio para ingresar con tu vehículo a países del MERCOSUR. Su objetivo es cubrir los daños que puedas causar a otras personas o sus bienes mientras conduces en el extranjero.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Cumplimiento Legal: Te permite cruzar las fronteras cumpliendo con la normativa internacional exigida.\nCobertura de Daños a Terceros: Si chocas a otro auto o causas daños a una propiedad, el seguro cubre hasta US$ 20.000 por tercero.\nCobertura de Lesiones a Personas: Si causas lesiones o muerte a personas (no transportadas en tu auto), el seguro cubre hasta US$ 40.000 por persona.\nDefensa Legal: Cubre parte de los gastos de abogados y juicios civiles en el extranjero.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Ocurre el Siniestro: Tienes un accidente en el extranjero.\nNo Asumas Culpa: No firmes acuerdos ni reconozcas responsabilidad sin hablar con la aseguradora.\nContacta al Representante: Debes llamar a la aseguradora representante en el país donde estás (los datos están en tu póliza).\nDenuncia Policial: Realiza la denuncia ante la autoridad local competente de inmediato.\nAviso: Informa a tu compañía en Chile dentro de los 5 días hábiles.",
      },
      {
        label: "Requisitos y Deberes",
        content:
          "Portar el Certificado: Es obligatorio llevar el documento del seguro en el auto durante todo el viaje.\nConductor Habilitado: Quien maneje debe tener licencia válida y competente.\nVehículo Particular: El seguro es para autos de paseo o alquiler, no para transporte comercial de carga o pasajeros.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños a tu propio auto: Este seguro NO cubre el robo ni los daños de tu propio vehículo.\nDaños a familiares: No cubre daños a tu cónyuge o parientes cercanos.\nConducción bajo efectos: Accidentes si el conductor está ebrio o drogado (la aseguradora paga al tercero pero luego te cobra a ti).\nMultas: No cubre multas de tránsito ni fianzas penales.",
      },
    ],
  },
  {
    slug: "rc-medica",
    title: "Responsabilidad Civil Médica",
    summary:
      "Este seguro está diseñado para proteger el patrimonio y la reputación de los profesionales de la salud frente a reclamos o demandas por presuntos errores u omisiones en la atención de pacientes.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Defensa Especializada: Si recibe una demanda o citación a mediación, la aseguradora provee abogados expertos en responsabilidad médica para su defensa.\nRespaldo Patrimonial: Si es condenado a pagar una indemnización, el seguro cubre el monto (hasta el tope contratado), evitando que deba responder con sus bienes personales.\nTranquilidad: Permite ejercer la profesión sabiendo que cuenta con respaldo ante la creciente judicialización de la medicina.\nApoyo en Juicios Penales: (Si se contrata) Cubre los gastos de defensa si se le imputa un delito por su actuar profesional.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Ocurre el Evento o Reclamo: Usted recibe una carta de reclamo, una citación a mediación, una notificación judicial o se entera de una investigación en su contra.\nNotificación Inmediata: Debe avisar a la compañía de seguros de inmediato. No espere a \"ver qué pasa\".\nAsignación de Defensa: La compañía evaluará el caso y designará un equipo legal para representarlo.\nProceso: El equipo legal llevará su defensa. Usted debe colaborar entregando la ficha clínica e informes requeridos.",
      },
      {
        label: "Requisitos para Cobertura",
        content:
          "Habilitación Profesional: Debe tener título válido y estar habilitado legalmente para ejercer la especialidad declarada.\nConsentimiento Informado: Mantener registros clínicos completos y obtener los consentimientos informados adecuados es clave para la defensa.\nNo Transigir: Nunca ofrezca dinero, arreglos ni admita culpabilidad ante el paciente o sus abogados sin la autorización escrita de la aseguradora.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Actos dolosos (intencionales) o cometidos bajo influencia de alcohol/drogas.\nGarantía de resultados (ej. prometer éxito en una cirugía estética).\nCirugía estética con fines de embellecimiento puro (salvo reconstructiva, según póliza).\nActos fuera de la especialidad declarada.\nHechos conocidos antes de contratar el seguro.\nDevolución de honorarios médicos.",
      },
    ],
  },
  {
    slug: "rc-personal",
    title: "Responsabilidad Civil Personal",
    summary:
      "Este seguro protege tu patrimonio y el de tu familia si, por accidente o descuido en tu vida privada, causas daños a otras personas o a sus cosas.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Respaldo Económico: Si eres responsable de un accidente (ej. tu perro muerde a un vecino, tu hijo rompe un vidrio jugando, se inunda el departamento de abajo por una fuga tuya), el seguro paga la indemnización.\nDefensa Legal: Si te demandan, la aseguradora pone abogados y cubre los gastos del juicio.\nProtección Familiar: Te cubre a ti, a tu pareja, a tus hijos y hasta a tu empleada de casa (en horario laboral).\nMascotas: Cubre los líos en que se metan tus perros o gatos (mientras no sean de raza peligrosa).",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Ocurre el Accidente: Pasa algo que daña a un tercero (un peatón, un vecino, una visita).\nNo Hagas Arreglos: No ofrezcas dinero ni aceptes la culpa en el momento. Di que tienes seguro y que la compañía se encargará.\nAvisa a la Compañía: Denuncia el hecho lo antes posible.\nDefensa y Pago: La aseguradora evaluará, te defenderá si es necesario y pagará la indemnización que corresponda.",
      },
      {
        label: "Requisitos para Cobertura",
        content:
          "Hechos Accidentales: Debe ser sin intención. Los daños causados a propósito (dolo) no se cubren.\nVida Privada: Solo cubre actos de tu vida personal y familiar. No cubre errores en tu trabajo o negocio.\nMascotas en Regla: Tus mascotas deben tener sus vacunas al día y cumplir la normativa de tenencia responsable.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños a tus propias cosas o a tu familia directa (cónyuge, hijos, padres).\nActos intencionales o delitos.\nActividades profesionales o comerciales.\nMultas o fianzas.\nUso de vehículos (salvo que se contrate el adicional específico).",
      },
    ],
  },
  {
    slug: "rc-profesional",
    title: "Responsabilidad Civil Profesional",
    summary:
      "Este seguro está diseñado para proteger tu patrimonio y el de tu empresa frente a reclamos de clientes que aleguen haber sufrido un perjuicio económico por un error, omisión o negligencia en el servicio profesional que les prestaste.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Defensa Legal: Si un cliente te demanda alegando que te equivocaste en tu trabajo, la aseguradora cubre los gastos de abogados para defenderte, incluso si el reclamo no tiene razón.\nPago de Indemnizaciones: Si se determina que cometiste un error profesional y debes compensar al cliente, el seguro paga la indemnización (hasta el tope contratado).\nProtección Patrimonial: Evita que debas usar tus propios recursos o los de tu empresa para pagar juicios costosos.",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Cometes un Error (o te acusan de uno): Por ejemplo, un error en la planificación, un consejo equivocado o un olvido en un procedimiento.\nRecibes un Reclamo: El cliente te envía una carta o te demanda exigiendo compensación.\nAvisas a la Compañía: Debes notificar a la aseguradora de inmediato.\nDefensa: La compañía asigna abogados (o aprueba los tuyos) para manejar el caso.",
      },
      {
        label: "Requisitos Clave",
        content:
          "No Asumir Culpa: Nunca admitas responsabilidad ni ofrezcas pagos sin hablar primero con la aseguradora. Podrías perder la cobertura.\nAviso Oportuno: Debes avisar apenas sepas de un problema que podría convertirse en demanda.\nActividad Declarada: El seguro solo cubre la profesión o giro descrito en la póliza. Si haces otra cosa, no está cubierto.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Actos Intencionales: Daños causados a propósito o delitos.\nGarantía de Éxito: No cubre si el cliente reclama solo porque no le gustó el resultado, sin que haya un error negligente de tu parte.\nMultas: No paga multas que te impongan las autoridades.\nOtros Seguros: Generalmente no cubre accidentes de tránsito ni defectos de productos, salvo que se especifique lo contrario.",
      },
    ],
  },
  {
    slug: "salud",
    title: "Salud",
    summary:
      "Este seguro está diseñado para pagar la parte de la cuenta médica que tu Isapre o Fonasa no cubre (el copago), ayudándote a cuidar tu presupuesto familiar en atenciones frecuentes.",
    tabs: [
      {
        label: "¿Qué cubre este seguro?",
        content:
          "Consultas y Exámenes: Desde una visita al médico general hasta exámenes de sangre o rayos X. El seguro te devuelve el 60%, 70% u 80% (según tu plan) de lo que pagaste.\nRemedios: Te ayuda a pagar los medicamentos recetados, con mayor cobertura si eliges genéricos.\nHospitalización: Si debes operarte o quedarte hospitalizado, el seguro cubre una parte importante de la cuenta de la clínica y los honorarios médicos.\nMaternidad: Aporta cobertura para parto o cesárea (para titulares o parejas).\nSalud Mental: Cobertura para consultas psicológicas y psiquiátricas (con tope anual).",
      },
      {
        label: "¿Cómo Funciona?",
        content:
          "Primero tu Previsión: Cuando vas al médico, primero bonifica tu Isapre o Fonasa.\nLuego el Deducible: Tienes un deducible anual pequeño (aprox. $28.000). Los primeros gastos del año sirven para llenar este deducible.\nActiva el Seguro: Una vez cubierto el deducible, el seguro comienza a reembolsar sus porcentajes en cada atención, hasta que se agote el monto máximo anual (UF 300 por persona).\nTip: En muchas farmacias y centros médicos en convenio, el descuento se hace automático con tu huella (I-Med).",
      },
      {
        label: "Dato de Ahorro",
        content:
          "Si te preocupa también tener cobertura para enfermedades muy graves y costosas (como un cáncer), al contratar este seguro junto con un Seguro Catastrófico en BCI, puedes acceder a un descuento especial en el precio del segundo seguro. ¡Pregunta por el pack!",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Enfermedades que ya tenías antes de contratar (preexistencias).\nCirugías estéticas.\nTratamientos para adelgazar (salvo cirugía bariátrica si cumples requisitos estrictos).\nMedicamentos sin receta o cosméticos.",
      },
    ],
  },
  {
    slug: "vehiculo",
    title: "Vehículo",
    summary:
      "Este seguro protege tu auto contra daños y robos, y también te protege a ti si le causas daños a otros.",
    tabs: [
      {
        label: "Principales Beneficios",
        content:
          "Reparación de tu Auto: Si chocas, te chocan o tienes un accidente, el seguro paga la reparación de tu vehículo (descontando el deducible).\nRobo: Si te roban el auto o sus accesorios (según plan), la aseguradora te indemniza.\nResponsabilidad Civil: Si chocas a otro auto, atropellas a alguien o destruyes propiedad ajena, el seguro paga esas indemnizaciones, protegiendo tu patrimonio.\nAsistencia: Incluye servicios como grúa, cambio de neumáticos, batería y auto de reemplazo (según condiciones).\nDefensa Legal: Abogados para defenderte si vas a juicio por un accidente.",
      },
      {
        label: "Guía de Uso",
        content:
          "Mantén la Calma: Verifica si hay heridos.\nDenuncia Policial: Si hay robo o lesionados, llama a Carabineros de inmediato y haz la denuncia. Es obligatorio.\nAvisa a la Compañía: Tienes un plazo (generalmente 10 días corridos, inmediato en robo) para denunciar el siniestro a la aseguradora.\nNo Asumas Culpa: No firmes acuerdos ni aceptes responsabilidad en el lugar sin hablar con tu aseguradora.\nConstancia: Si es un choque leve sin heridos, deja constancia en la comisaría más cercana según exija tu póliza.",
      },
      {
        label: "Tus Obligaciones",
        content:
          "Licencia al Día: El conductor debe tener licencia válida y competente para el vehículo.\nAlcohol y Drogas: Nunca conduzcas bajo la influencia del alcohol o drogas. Si lo haces, el seguro no paga nada.\nGPS: Si tu póliza exige GPS (por la Ley Antiportonazo), debes instalarlo y mantenerlo activo. Si te roban el auto y no lo tenías, podrías tener un deducible mucho mayor o perder la cobertura.\nPago de Prima: Mantén tus cuotas al día. Si no pagas, la póliza se puede cancelar.",
      },
      {
        label: "Lo que NO Cubre",
        content:
          "Daños causados a propósito (dolo).\nAccidentes si el conductor huye del lugar.\nUso del auto para fines no declarados (ej. usar auto particular para Uber/taxi sin declararlo).\nDaños preexistentes (rayones o abolladuras que ya tenía el auto antes de contratar).",
      },
    ],
  },
];
