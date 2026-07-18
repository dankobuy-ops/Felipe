(async function(){
  if (window.__PJUD_RUNNING__){ alert('Ya hay un scraping en curso.'); return; }
  window.__PJUD_RUNNING__ = true;

  /* ── config ── The OPERATOR sets the search by hand: pestaña "Busqueda por Fecha",
     Competencia = Civil, Corte, y las Fechas. This script NEVER touches those — it only
     iterates the Tribunales of the chosen corte. */
  var VERSION = 'v10 · solo clicks + ritmo humano';  /* shown in the toast to confirm a fresh build */
  var MAX_TRIBS = 12;                     /* cap tribunals per run (test) */
  var DEEP = 8;                           /* max causas to deep-open this run */
  var BANK =['SANTANDER','ESTADO DE CHILE','BANCOESTADO','BANCO DEL ESTADO','ITAU',
    'SCOTIABANK','BANCO INTERNACIONAL','CREDITO E INVERSIONES','BCI','BANCO DE CHILE',
    'FALABELLA','COOPEUCH','BICE','CONSORCIO','RIPLEY','BTG'];

  var $ = function(s){ return document.querySelector(s); };
  var $$ = function(s){ return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r,ms); }); };
  var hpace = function(lo,hi){ return sleep(lo + Math.floor(Math.random()*(hi-lo+1))); };  // human, randomized pause
  var norm = function(s){ s=(s||'').normalize('NFD'); var out='';
    for(var i=0;i<s.length;i++){ var c=s.charCodeAt(i); if(c<768||c>879) out+=s[i]; }
    return out.toUpperCase().replace(/\s+/g,' ').trim(); };
  var isBank = function(c){ var n=norm(c); return BANK.some(function(f){ return n.indexOf(f)>=0; }); };
  var txt = function(el){ return el ? (el.innerText||'').trim() : ''; };

  var toast = document.getElementById('__pjud_toast__');
  if(!toast){ toast=document.createElement('div'); toast.id='__pjud_toast__';
    toast.style.cssText='position:fixed;z-index:2147483647;bottom:14px;right:14px;max-width:470px;background:#0d47a1;color:#fff;padding:12px 16px;border-radius:8px;font:13px/1.45 sans-serif;box-shadow:0 3px 12px rgba(0,0,0,.4);white-space:pre-line';
    document.documentElement.appendChild(toast); }
  var say = function(m){ toast.textContent = m; };

  function waitFor(pred, ms, step){ step=step||300; return new Promise(function(res){
    var w=0; var t=setInterval(function(){ var ok=false; try{ ok=pred(); }catch(e){}
      if(ok){ clearInterval(t); res(true); } else { w+=step; if(w>=ms){ clearInterval(t); res(false); } }
    }, step); }); }
  function setSelect(sel, val){ var e=$(sel); if(!e) return false;
    var idx=-1; Array.prototype.forEach.call(e.options||[], function(o,k){ if(o.value===val) idx=k; });
    if(idx>=0) e.selectedIndex=idx;      // move the real selection, not just .value
    e.value=val;
    // ALWAYS fire a NATIVE input+change — exactly what Playwright select_option does in
    // run.py. THE FIX: a jQuery-only .trigger('change') does NOT invoke handlers bound with
    // addEventListener, so OJV's corte->tribunal cascade silently didn't run and #fecTribunal
    // kept the previous corte's (Arica) list. Native dispatch fires ALL handler kinds
    // (inline onchange / addEventListener / jQuery-bound).
    e.dispatchEvent(new Event('input',{bubbles:true}));
    e.dispatchEvent(new Event('change',{bubbles:true}));
    // best-effort: repaint a styled-select plugin so the VISIBLE control matches the value
    if(window.jQuery){ try{ var $e=window.jQuery(e);
      if($e.selectpicker){ try{ $e.selectpicker('refresh'); }catch(_){} }
      try{ $e.trigger('chosen:updated'); }catch(_){}
    }catch(err){} }
    return e.value===val; }
  function opts(sel){ return $$(sel+' option').filter(function(o){ return o.value && o.value!=='0'; }); }
  function selText(sel){ var e=$(sel); if(!e || e.selectedIndex<0) return '';
    var o=e.options[e.selectedIndex]; return o?(o.textContent||'').trim():''; }  // LIVE selected label
  function lastDay(y,m){ return new Date(y,m,0).getDate(); }
  function pad(n){ return (''+n).length<2 ? '0'+n : ''+n; }
  function firstJwt(){ var a=$("#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']");
    return a ? a.getAttribute('onclick') : ''; }
  // Advance the results paginator via 'Siguiente' (#sigId). Mirrors run.py
  // _next_fecha_page: returns true only once the table actually changes; false at the
  // last page OR when a click fails to advance (so a stuck paginator breaks, not spins).
  async function nextFechaPage(){
    var sig=$('#sigId'); var li=sig?sig.closest('li'):null;
    if(!sig || (li && li.classList.contains('disabled'))) return false;
    var before=firstJwt();
    await humanClick(sig);                              // CLICK "Siguiente" like a human
    for(var k=0;k<20;k++){                              // poll up to ~10s for the AJAX swap
      await sleep(500);
      var j=firstJwt();
      if(j && j!==before) return true;
    }
    return false;                                       // no change -> treat as last page
  }

  /* ── modal detail parsers (mirror run.py) ── */
  function modalText(){ return txt($('#modalDetalleCivil')); }
  // Find the magnifier link (opens the causa detail) for a ROL in the CURRENT results page.
  function causaAnchor(rol){
    var trs=$$('#dtaTableDetalleFecha tbody tr');
    for(var k=0;k<trs.length;k++){ var td=trs[k].querySelectorAll('td');
      if(td[1] && txt(td[1])===rol) return trs[k].querySelector("a[onclick*='detalleCausaCivil']"); }
    return null;
  }
  async function openDetail(rol){
    // HUMAN ORDER: never open a modal while another is open. Close whatever's left and wait
    // until the screen is clear before opening this causa.
    if(modalOpen('#modalReceptorCivil')) await closeOverlay('#modalReceptorCivil');
    if(modalOpen('#modalDetalleCivil')) await closeOverlay('#modalDetalleCivil');
    await waitFor(function(){ return !modalOpen('#modalReceptorCivil') && !modalOpen('#modalDetalleCivil'); }, 6000);
    var a=causaAnchor(rol);
    if(!a) throw new Error('no anchor for '+rol);
    var before=modalText();
    await humanClick(a);                                 // OPEN by CLICKING the magnifier — no JWT command
    await waitFor(function(){ var t=modalText(); return t && t!==before && t.indexOf('ROL')>=0 && t.indexOf(rol)>=0; }, 15000);
    await sleep(700);
  }
  function grab(b, re){ var m=b.match(re); return m ? m[1].trim() : ''; }
  function parseHeader(){
    var b=modalText();
    return { header_raw: b.slice(0,500).replace(/\s+/g,' '),
      f_ingreso:    grab(b,/F\.\s*Ing\.?:\s*([^\n\t]+)/i),
      estado_adm:   grab(b,/Est\.\s*Adm\.?:\s*([^\n\t]+)/i),
      procedimiento:grab(b,/(?<!Estado )Proc\.?:\s*([^\n\t]+)/i),
      ubicacion:    grab(b,/Ubicaci[oó]n:\s*([^\n\t]+)/i),
      estado_proc:  grab(b,/Estado\s*Proc\.?:\s*([^\n\t]+)/i),
      etapa:        grab(b,/Etapa:\s*([^\n\t]+)/i) };
  }
  function parseLitigantes(){ return $$('#litigantesCiv table tbody tr').map(function(tr){
    var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
    return {participante:txt(td[0]), rut:txt(td[1]), persona:txt(td[2]), nombre:txt(td[3])};
  }).filter(function(r){ return r.rut||r.nombre; }); }
  function cuadOpts(){ return $$('#selCuaderno option').map(function(o){ return {txt:(o.textContent||'').trim(), val:o.value}; }); }
  async function selectCuaderno(i){ var s=$('#selCuaderno'); if(!s) return; s.selectedIndex=i;
    s.dispatchEvent(new Event('change',{bubbles:true})); await sleep(2200); }
  function formInfo(td){ if(!td) return null; var f=td.querySelector('form'); if(!f) return null;
    var inp=f.querySelector("input[name='dtaDoc'], input");
    return {action:f.getAttribute('action')||'', name:inp?inp.getAttribute('name'):'', val:inp?inp.value:''}; }
  function parseHistoria(){ return $$('#historiaCiv table tbody tr').map(function(tr){
    var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
    return {folio:txt(td[0]), doc:formInfo(td[1]), anexo:formInfo(td[2]), etapa:txt(td[3]),
            tramite:txt(td[4]), desc:txt(td[5]), fecha:txt(td[6]), foja:txt(td[7]), georref:txt(td[8])};
  }); }
  function parseEscritos(){ return $$('#escritosCiv table tbody tr').map(function(tr){
    var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
    return {fecha_ingreso:txt(td[2]), tipo_escrito:txt(td[3]), solicitante:txt(td[4])};
  }).filter(function(r){ return r.tipo_escrito||r.solicitante; }); }
  // Click an element the way a human does: real mouse event sequence over its center.
  async function humanClick(el){
    if(!el) return false;
    try{ el.scrollIntoView({block:'center'}); }catch(e){}
    await sleep(120);
    var cx=10, cy=10; try{ var r=el.getBoundingClientRect(); cx=r.left+r.width/2; cy=r.top+r.height/2; }catch(e){}
    var o={bubbles:true, cancelable:true, view:window, clientX:cx, clientY:cy, button:0};
    try{ el.dispatchEvent(new MouseEvent('mouseover', o)); el.dispatchEvent(new MouseEvent('mousedown', o));
         el.dispatchEvent(new MouseEvent('mouseup', o)); el.dispatchEvent(new MouseEvent('click', o)); return true; }
    catch(e){ try{ el.click(); return true; }catch(e2){ return false; } }
  }
  // True if a modal is currently visible.
  function modalOpen(sel){ try{ var e=$(sel); return !!e && (e.classList.contains('show')||e.classList.contains('in')||getComputedStyle(e).display!=='none'); }catch(err){ return false; } }
  // Close a modal the HUMAN way: click its own close control (the X, a data-dismiss button,
  // or a footer "Cerrar/Salir" button) and, failing that, click the backdrop (outside the
  // dialog) as a person would. Verify it faded out; retry. NO .modal('hide'), synthetic keys
  // or backdrop/force-hide surgery — those are non-human tells that trip the WAF and corrupt
  // stacked modals.
  async function closeOverlay(sel){
    function footerClose(){ var bs=$$(sel+' .modal-footer button, '+sel+' .modal-footer .btn, '+sel+' .modal-footer a');
      for(var i=0;i<bs.length;i++){ var t=((bs[i].innerText||bs[i].value||'')+'').toLowerCase();
        if(/cerrar|salir|cancelar|volver|aceptar|\bok\b/.test(t)) return bs[i]; } return null; }
    for(var attempt=0; attempt<6 && modalOpen(sel); attempt++){
      var b = $(sel+' .modal-header .close') || $(sel+' button.close') || $(sel+" [data-dismiss='modal']") || footerClose();
      if(b){ await humanClick(b); await sleep(700); if(!modalOpen(sel)) return true; }
      else { var bd=$('.modal-backdrop'); if(bd){ await humanClick(bd); await sleep(700); if(!modalOpen(sel)) return true; } else break; }
      await sleep(400);                  // let the fade finish, then try again
    }
    return !modalOpen(sel);
  }
  async function parseReceptor(){
    var a=$("#modalDetalleCivil a[onclick*='receptorCivil']");
    if(!a) return [];                                        // this causa has no receptor link
    try{
      await humanClick(a);                                   // OPEN like a human: click the link
      await waitFor(function(){ var m=$('#modalReceptorCivil'); return m && (m.querySelector('table tbody tr')|| /Receptor/i.test(m.innerText)); }, 10000);
      await sleep(400);
      var rows=$$('#modalReceptorCivil table tbody tr').map(function(tr){
        var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
        return {cuaderno:txt(td[0]), nombre:txt(td[1]), fecha:txt(td[2]), estado:txt(td[3])};
      }).filter(function(r){ return r.nombre||r.cuaderno; });
      await closeOverlay('#modalReceptorCivil');             // CLOSE it (human) before anything else
      await waitFor(function(){ return !modalOpen('#modalReceptorCivil'); }, 6000); // don't proceed until it's gone
      return rows;
    }catch(e){ try{ await closeOverlay('#modalReceptorCivil'); }catch(e2){} return []; }
  }
  // (No background PDF fetch — a fetch() is a non-human network command. The doc form info
  //  (action + dtaDoc) is captured in the historia rows for later download by run.py.)
  async function closeDetail(){
    if(modalOpen('#modalReceptorCivil')) await closeOverlay('#modalReceptorCivil');  // sub-modal first
    await closeOverlay('#modalDetalleCivil');
    await waitFor(function(){ return !modalOpen('#modalDetalleCivil'); }, 5000);
    await sleep(300);
  }

  async function scrapeCausa(meta){
    await openDetail(meta.rol);                          // opens by CLICKING the magnifier
    var header=parseHeader();
    var lits=parseLitigantes();
    var cuads=cuadOpts(); if(cuads.length===0) cuads=[{txt:'1 - Principal', val:''}];
    var cuadernos=[];
    for(var ci=0; ci<cuads.length; ci++){ if(ci>0) await selectCuaderno(ci);
      cuadernos.push({cuaderno:cuads[ci].txt, historia:parseHistoria()}); }
    var escritos=parseEscritos();
    var receptor=await parseReceptor();
    var allHist=cuadernos.reduce(function(a,c){ return a.concat(c.historia); },[]);
    await closeDetail();
    return {rol:meta.rol, caratulado:meta.caratulado, fecha:meta.fecha, tribunal:meta.tribunal,
      corte:meta.corte, tribunalSel:meta.tribunalSel, rango:meta.rango, header:header,
      litigantes:lits, cuadernos:cuadernos, escritos:escritos, receptor:receptor,
      n_historia:allHist.length};
  }

  /* ── 1) VALIDATE the operator's setup — we do NOT touch competencia / corte / dates ──
     The operator has already: opened "Busqueda por Fecha", set Competencia = Civil, chosen
     the Corte, and typed the Fechas. We only READ that and iterate the Tribunales. */
  say(VERSION+'\nLeyendo tu configuracion...');
  await sleep(300);
  if((($('#fecCompetencia')||{}).value)!=='3'){
    say('La Competencia debe ser CIVIL (y estar aplicada).\nAjustala y reintenta.');
    window.__PJUD_RUNNING__=false; return; }
  var tribAll=opts('#fecTribunal');
  if(tribAll.length===0){
    say('No veo Tribunales.\nElige Competencia (Civil) y Corte para que cargue\nla lista de Tribunales, y reintenta.');
    window.__PJUD_RUNNING__=false; return; }
  var desde=(($('#fecDesde')||{}).value||''), hasta=(($('#fecHasta')||{}).value||'');
  if(!desde || !hasta){
    say('Faltan las FECHAS (Desde / Hasta).\nIngresalas y reintenta.');
    window.__PJUD_RUNNING__=false; return; }
  var tribs=tribAll.map(function(o){ return {v:o.value, t:(o.textContent||'').trim()}; }).slice(0, MAX_TRIBS);
  say(VERSION+'\nCorte: '+selText('#corteFec')+'\nFechas: '+desde+' a '+hasta+'\nTribunales a recorrer: '+tribs.length);
  await sleep(1500);

  // Select ONE tribunal from the operator's current list (native change) and verify.
  // We NEVER touch the corte — if the value isn't present we just skip that tribunal.
  async function selectTribunal(tv){
    setSelect('#fecTribunal', tv);
    return await waitFor(function(){ return (($('#fecTribunal')||{}).value)===tv; }, 5000);
  }

  // Fire the search for the currently-selected tribunal (operator's competencia/corte/dates)
  // by CLICKING "Buscar", then WAIT for real result rows. Returns true if any rendered.
  async function fireSearch(){
    var realRows=function(){ return $$('#dtaTableDetalleFecha tbody tr')
      .filter(function(tr){ return tr.querySelector("a[onclick*='detalleCausaCivil']"); }); };
    var emptyMsg=function(){ var t=(($('#dtaTableDetalleFecha')||{}).innerText)||'';
      return /no se (han )?encontrad|sin resultados|no matching|no data/i.test(t); };
    for(var attempt=0; attempt<3; attempt++){
      var tb=$('#dtaTableDetalleFecha tbody'); if(tb) tb.innerHTML='';   // clear our view to detect fresh results
      var btn=$('#btnConConsultaFec'); if(btn) await humanClick(btn);    // CLICK Buscar
      await waitFor(function(){ return realRows().length>0 || emptyMsg(); }, 20000);
      if(realRows().length>0){ await sleep(700); return true; }
      if(emptyMsg() && attempt>0) return false;            // confirmed: no causas here
      await sleep(1500);                                   // quirk / still loading -> re-fire
    }
    return realRows().length>0;
  }
  // Bank C-causas visible on the CURRENT results page (metadata only; we open by clicking).
  function pageBankCausas(){
    return $$('#dtaTableDetalleFecha tbody tr').map(function(tr){
      var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
      var a=tr.querySelector("a[onclick*='detalleCausaCivil']");
      return {rol:txt(td[1]), fecha:txt(td[2]), caratulado:txt(td[3]), tribunal:txt(td[4]), has:!!a};
    }).filter(function(r){ return r.has && r.rol.toUpperCase().indexOf('C')===0 && isBank(r.caratulado); });
  }

  /* ── 3) sweep: iterate the operator's tribunales. Per tribunal: CLICK Buscar, then walk the
     result pages CLICKING each bank causa's magnifier to open it, scrape, close, move on —
     exactly what a person does. Human, randomized pacing throughout. ── */
  var details=[]; var total=tribs.length; var done=0;
  var corteTxt=selText('#corteFec'), rango=desde+' a '+hasta;
  for(var i=0; i<tribs.length && details.length<DEEP; i++){
    done++;
    var tv=tribs[i].v, tribLbl=tribs[i].t;
    var okT=await selectTribunal(tv);
    say(VERSION+'  ('+done+'/'+total+')\n'+corteTxt+'\n'+selText('#fecTribunal').slice(0,40)+(okT?'':'  [SEL FALLO]')+'\ndet: '+details.length);
    if(!okT) continue;
    var got=false; try{ got=await fireSearch(); }catch(e){}
    if(!got){ await hpace(1500,3500); continue; }          // no causas for this tribunal
    var seen={}, pages=0;
    while(pages<60 && details.length<DEEP){
      var causas=pageBankCausas();
      for(var j=0; j<causas.length && details.length<DEEP; j++){
        var c=causas[j]; if(seen[c.rol]) continue; seen[c.rol]=1;
        await hpace(2000,5000);                            // human pause before opening a causa
        say('Detallando '+(details.length+1)+' · '+c.rol+'\n'+c.caratulado.slice(0,40));
        try{ details.push(await scrapeCausa({rol:c.rol, caratulado:c.caratulado, fecha:c.fecha,
              tribunal:c.tribunal, corte:corteTxt, tribunalSel:tribLbl, rango:rango})); }
        catch(e){ details.push({rol:c.rol, caratulado:c.caratulado, error:String(e)}); try{ await closeDetail(); }catch(e2){} }
      }
      pages++;
      if(details.length>=DEEP) break;
      if(!await nextFechaPage()) break;                     // CLICK "Siguiente"
      await hpace(1500,3500);                               // human pause between result pages
    }
    await hpace(2500,6000);                                 // human pause between tribunales
  }

  say('Descargando '+details.length+' causas detalladas (JSON)...');
  var blob=new Blob([JSON.stringify(details,null,2)],{type:'application/json'});
  var url=URL.createObjectURL(blob); var a=document.createElement('a');
  a.href=url; a.download='pjud_detalle_'+Date.now()+'.json'; document.documentElement.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(url); }, 5000);
  say('Listo: '+details.length+' causas detalladas.\n(pjud_detalle_*.json en Descargas)');
  window.__PJUD_RUNNING__=false;
})();
