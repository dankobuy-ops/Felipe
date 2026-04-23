const PdfHandler = (() => {
  function init() {
    if (typeof pdfjsLib !== 'undefined') {
      pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }
  }

  async function extractText(file) {
    if (typeof pdfjsLib === 'undefined') {
      throw new Error('PDF_LIB_NOT_LOADED');
    }

    const nameOk = file.name.toLowerCase().endsWith('.pdf');
    const typeOk = file.type === 'application/pdf' || file.type === '';
    if (!nameOk && !typeOk) {
      throw new Error('INVALID_FILE_TYPE');
    }

    if (file.size > CONFIG.PDF_MAX_SIZE_MB * 1024 * 1024) {
      throw new Error('FILE_TOO_LARGE');
    }

    const arrayBuffer = await file.arrayBuffer();
    let pdf;

    try {
      pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    } catch (e) {
      if (e.name === 'PasswordException' || (e.message && e.message.toLowerCase().includes('password'))) {
        throw new Error('PDF_ENCRYPTED');
      }
      throw new Error('PDF_LOAD_ERROR');
    }

    let fullText = '';
    let pagesWithText = 0;

    for (let i = 1; i <= pdf.numPages; i++) {
      try {
        const page = await pdf.getPage(i);
        const textContent = await page.getTextContent();
        const pageText = textContent.items.map(item => item.str).join(' ');

        if (pageText.trim().length > 20) pagesWithText++;
        fullText += `\n--- Página ${i} ---\n${pageText}`;
      } catch (pageErr) {
        fullText += `\n--- Página ${i} --- [Error al extraer]\n`;
      }
    }

    const textDensity = pdf.numPages > 0 ? pagesWithText / pdf.numPages : 0;
    const isScanned = textDensity < CONFIG.PDF_MIN_TEXT_DENSITY;

    const cleanedText = fullText
      .replace(/\s{3,}/g, '  ')
      .replace(/[^\S\n]{2,}/g, ' ')
      .trim()
      .substring(0, CONFIG.PDF_TEXT_LIMIT_CHARS);

    return {
      text: cleanedText,
      pageCount: pdf.numPages,
      extractionMethod: isScanned ? 'fallback' : 'text',
      warning: isScanned
        ? 'PDF con bajo contenido de texto detectado. Posiblemente es un PDF escaneado (imagen). El análisis puede ser limitado.'
        : null
    };
  }

  return { init, extractText };
})();
