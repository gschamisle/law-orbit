// Annex membership is distinct from a direct citation and from legal applicability.
export const deadlineLabels={elapsed:'별표상 기한 경과',within_date:'별표상 기한 이내',not_stated:'별표상 기한 미기재'};
export const statusLabels={matched:'법령명·조 번호 대조', 'historical-supplement':'개정법 부칙 별도 확인', 'not-collected':'근거 법령 미수집', 'article-unavailable':'근거 조문 일부 미확인','needs-review':'원문 대조 필요'};
export function dateLabel(value){return /^\d{8}$/.test(value||'')?`${value.slice(0,4)}.${value.slice(4,6)}.${value.slice(6)}`:'기한 미기재';}
const compact=value=>String(value||'').replace(/[\sㆍ·]/g,'').toLowerCase();
export function selectCases(rows,{query='',type='',deadline='',law='',jo='',status=''}={}){
 return rows.filter(r=>(!query||compact([r.number,r.legal_text,r.type_text,r.deadline_text,r.deadline].join(' ')).includes(compact(query)))
  &&(!type||r.types.includes(type))&&(!deadline||r.deadline_status===deadline)&&(!status||r.status===status)
  &&(!law||compact(r.law)===compact(law))&&(!jo||(r.article_numbers||[]).includes(jo)));
}
