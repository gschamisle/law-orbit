// PDF offsets are Python Unicode code-point offsets, just like citation evidence.
export function pdfPage(document,page){
 const record=document.pdf_analysis?.pages.find(p=>p.page===Number(page));
 if(!record)throw Error('수집한 PDF에 해당 쪽이 없습니다.');
 return {...record,text:Array.from(document.unstructured_text).slice(record.start,record.end).join('')};
}
export function renderProcurementPdf(container,document,evidence,{text,link,markBody,onPage=()=>{}}){
 const pdf=document.pdf_analysis;if(!pdf)return false;
 const choice=window.document.createElement('select');choice.setAttribute('aria-label','PDF 본문 쪽');
 for(const p of pdf.pages){const option=text('option',`PDF ${p.page}쪽${p.printed_page?' (인쇄 '+p.printed_page+'쪽)':''} · ${p.label||'목차·표·서식 등'}${p.analyzed_units?'':' · 연결 미분석'}`);option.value=p.page;choice.append(option);}
 const sourceRows=evidence.filter(r=>r.direction==='reverse'&&r.source_id===document.meta.id&&r.source_layer==='procurement-pdf-prose');
 choice.value=sourceRows[0]?.source_page||pdf.pages.find(p=>p.analyzed_units)?.page||1;
 const label=text('label','본문 위치');label.append(choice);const meta=text('p','','muted small'),body=text('div','','reading-text');
 const scope=text('details');scope.append(text('summary','PDF 분석 범위'),text('p',pdf.limitation,'muted small'));
 const stage=text('div');stage.append(body);container.replaceChildren(scope,label,meta,stage);
 const render=()=>{const page=pdfPage(document,choice.value);stage.replaceChildren(body);body.textContent=page.text;
  meta.replaceChildren(text('span',`PDF ${page.page}쪽 · ${page.analyzed_units?'일반 문단 인용 분석':'이 쪽은 연결 미분석'} `),link(pdf.pdf_url+'#page='+page.page,'공식 PDF에서 확인 ↗'));
  const rows=sourceRows.filter(r=>r.source_page===page.page).map(r=>({...r,source_start:r.source_start-page.start,source_end:r.source_end-page.start}));
  if(rows.length&&markBody)markBody(body,page.text,rows,stage);onPage(page);
 };choice.onchange=render;render();return true;
}
