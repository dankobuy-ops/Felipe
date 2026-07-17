(async function(){
  if (window.__PJUD_RUNNING__){ alert('Ya hay un scraping en curso.'); return; }
  window.__PJUD_RUNNING__ = true;

  /* ── config (demo scope) ── */
  var CORTE = '90';                       /* C.A. de Santiago */
  var MONTHS = [[2026,7],[2026,6]];       /* try July, then June */
  var MAX_TRIBS = 12;
  var DEEP = 8;                           /* max causas to deep-open this run */
  var PACE = 400;
  var BANK = ['SANTANDER','ESTADO DE CHILE','BANCOESTADO','BANCO DEL ESTADO','ITAU',
    'SCOTIABANK','BANCO INTERNACIONAL','CREDITO E INVERSIONES','BCI','BANCO DE CHILE',
    'FALABELLA','COOPEUCH','BICE','CONSORCIO','RIPLEY','BTG'];

  var $ = function(s){ return document.querySelector(s); };
  var $$ = function(s){ return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r,ms); }); };
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
  function setSelect(sel, val){ var e=$(sel); if(!e) return false; e.value=val;
    e.dispatchEvent(new Event('change',{bubbles:true})); return e.value===val; }
  function opts(sel){ return $$(sel+' option').filter(function(o){ return o.value && o.value!=='0'; }); }
  function lastDay(y,m){ return new Date(y,m,0).getDate(); }
  function pad(n){ return (''+n).length<2 ? '0'+n : ''+n; }
  function firstJwt(){ var a=$("#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']");
    return a ? a.getAttribute('onclick') : ''; }

  /* ── modal detail parsers (mirror run.py) ── */
  function modalText(){ return txt($('#modalDetalleCivil')); }
  async function openDetail(jwt, rol){
    var before=modalText();
    window.detalleCausaCivil(jwt);
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
  function receptorJwt(){ var a=$("#modalDetalleCivil a[onclick*='receptorCivil']"); if(!a) return '';
    var m=(a.getAttribute('onclick')||'').match(/receptorCivil\(['"]([^'"]+)['"]\)/); return m?m[1]:''; }
  async function parseReceptor(jwt){ if(!jwt) return []; try{
    window.receptorCivil(jwt);
    await waitFor(function(){ var m=$('#modalReceptorCivil'); return m && (m.querySelector('table tbody tr')|| /Receptor/i.test(m.innerText)); }, 10000);
    await sleep(400);
    var rows=$$('#modalReceptorCivil table tbody tr').map(function(tr){
      var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
      return {cuaderno:txt(td[0]), nombre:txt(td[1]), fecha:txt(td[2]), estado:txt(td[3])};
    }).filter(function(r){ return r.nombre||r.cuaderno; });
    if(window.jQuery){ try{ window.jQuery('#modalReceptorCivil').modal('hide'); }catch(e){} }
    await sleep(300); return rows;
  }catch(e){ return []; } }
  async function verifyPdf(historia){
    for(var i=0;i<historia.length;i++){ var d=historia[i].doc;
      if(d && d.action && d.val){ try{
        var url=location.origin+'/'+d.action.replace(/^\//,''); var p=(d.name||'dtaDoc');
        var resp=await fetch(url+'?'+p+'='+encodeURIComponent(d.val), {credentials:'include'});
        var buf=await resp.arrayBuffer(); var u=new Uint8Array(buf.slice(0,4));
        var isPdf=(u[0]===0x25&&u[1]===0x50&&u[2]===0x44&&u[3]===0x46);
        return {url:url, ok:isPdf, bytes:buf.byteLength, contentType:resp.headers.get('content-type')||''};
      }catch(e){ return {ok:false, error:String(e)}; } } }
    return null; }
  async function closeDetail(){ if(window.jQuery){ try{ window.jQuery('#modalDetalleCivil').modal('hide'); }catch(e){} }
    else { var b=$('#modalDetalleCivil button.close'); if(b) b.click(); } await sleep(600); }

  async function scrapeCausa(h){
    await openDetail(h.jwt, h.rol);
    var header=parseHeader();
    var lits=parseLitigantes();
    var cuads=cuadOpts(); if(cuads.length===0) cuads=[{txt:'1 - Principal', val:''}];
    var cuadernos=[];
    for(var ci=0; ci<cuads.length; ci++){ if(ci>0) await selectCuaderno(ci);
      cuadernos.push({cuaderno:cuads[ci].txt, historia:parseHistoria()}); }
    var escritos=parseEscritos();
    var receptor=await parseReceptor(receptorJwt());
    var allHist=cuadernos.reduce(function(a,c){ return a.concat(c.historia); },[]);
    var pdf=await verifyPdf(allHist);
    await closeDetail();
    return {rol:h.rol, caratulado:h.caratulado, fecha:h.fecha, tribunal:h.tribunal, month:h.month,
      header:header, litigantes:lits, cuadernos:cuadernos, escritos:escritos, receptor:receptor,
      n_historia:allHist.length, pdf_check:pdf};
  }

  /* ── 1) date tab + Civil competencia ── */
  say('Preparando formulario...');
  var tab=$("a[href='#BusFecha']"); if(tab) tab.click(); await sleep(700);
  setSelect('#fecCompetencia','3');
  var okCorte=await waitFor(function(){ return opts('#corteFec').length>0; }, 9000);
  if(!okCorte){ say('No se pudieron cargar las cortes (competencia no aplicada).'); window.__PJUD_RUNNING__=false; return; }

  /* ── 2) corte -> tribunals ── */
  setSelect('#corteFec', CORTE); await sleep(300);
  await waitFor(function(){ return opts('#fecTribunal').length>0; }, 12000);
  var tribs=opts('#fecTribunal').map(function(o){ return {v:o.value, t:(o.textContent||'').trim()}; }).slice(0, MAX_TRIBS);

  async function searchTrib(tv,y,m){
    setSelect('#fecTribunal', tv);
    if(($('#fecTribunal')||{}).value!==tv) return [];
    var dd=lastDay(y,m);
    var setDate=function(id,v){ var e=$(id); if(e){ e.removeAttribute('readonly'); e.value=v; e.dispatchEvent(new Event('change',{bubbles:true})); } };
    setDate('#fecDesde','01/'+pad(m)+'/'+y); setDate('#fecHasta',pad(dd)+'/'+pad(m)+'/'+y);
    var tb=$('#dtaTableDetalleFecha tbody'); if(tb) tb.innerHTML='';
    var btn=$('#btnConConsultaFec'); if(btn) btn.click();
    var got=await waitFor(function(){ return $$('#dtaTableDetalleFecha tbody tr').length>0; }, 8000);
    if(!got) return [];
    await sleep(500);
    var rows=[]; var seen={}; var pages=0;
    while(pages<20){
      $$('#dtaTableDetalleFecha tbody tr').forEach(function(tr){
        var td=Array.prototype.slice.call(tr.querySelectorAll('td'));
        var a=tr.querySelector("a[onclick*='detalleCausaCivil']");
        var oc=a?a.getAttribute('onclick'):''; var mm=oc.match(/detalleCausaCivil\(['"]([^'"]+)['"]\)/);
        var rol=txt(td[1]);
        if(rol && !seen[rol]){ seen[rol]=1;
          rows.push({rol:rol, fecha:txt(td[2]), caratulado:txt(td[3]), tribunal:txt(td[4]), jwt:mm?mm[1]:''}); }
      });
      pages++;
      var sig=$('#sigId'); var li=sig?sig.closest('li'):null;
      if(!sig || (li && li.classList.contains('disabled'))) break;
      var before=firstJwt(); sig.click();
      await waitFor(function(){ var j=firstJwt(); return j && j!==before; }, 6000);
    }
    return rows;
  }

  /* ── 3) sweep: per tribunal, list bank causas, then deep-scrape each right away ── */
  var details=[]; var total=tribs.length*MONTHS.length; var done=0;
  for(var mi=0; mi<MONTHS.length && details.length<DEEP; mi++){
    var y=MONTHS[mi][0], m=MONTHS[mi][1], monthHits=0;
    for(var i=0; i<tribs.length && details.length<DEEP; i++){
      done++;
      say('Buscando '+y+'-'+pad(m)+'\n'+tribs[i].t.slice(0,42)+'\n('+done+'/'+total+')  detalladas: '+details.length);
      var rows=[]; try{ rows=await searchTrib(tribs[i].v,y,m); }catch(e){}
      var keep=rows.filter(function(r){ return r.rol.toUpperCase().indexOf('C')===0 && r.jwt && isBank(r.caratulado); });
      for(var j=0; j<keep.length && details.length<DEEP; j++){
        var h=keep[j]; h.corte=CORTE; h.month=y+'-'+pad(m);
        say('Detallando '+(details.length+1)+'/'+DEEP+'\n'+h.rol+'  '+h.caratulado.slice(0,38));
        try{ details.push(await scrapeCausa(h)); }
        catch(e){ details.push({rol:h.rol, caratulado:h.caratulado, error:String(e)}); try{ await closeDetail(); }catch(e2){} }
        monthHits++; await sleep(PACE);
      }
    }
    if(monthHits>0) break;
  }

  var okPdf=details.filter(function(d){ return d.pdf_check && d.pdf_check.ok; }).length;
  say('Descargando '+details.length+' causas detalladas (JSON)...');
  var blob=new Blob([JSON.stringify(details,null,2)],{type:'application/json'});
  var url=URL.createObjectURL(blob); var a=document.createElement('a');
  a.href=url; a.download='pjud_detalle_'+Date.now()+'.json'; document.documentElement.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(url); }, 5000);
  say('Listo: '+details.length+' causas detalladas.\nPDFs verificados OK: '+okPdf+'\n(pjud_detalle_*.json en Descargas)');
  window.__PJUD_RUNNING__=false;
})();
