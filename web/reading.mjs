// Read a related provision without replacing the active galaxy/catalog.
export async function loadReading({id,jo='',region=''}, {catalog,lookup,currentDoc,read}) {
 let entry=lookup.get(id);
 if(!entry&&region){
  const place=catalog.regions?.find(r=>r.id===region);
  if(place?.catalog){const local=await read(place.catalog);entry=local.laws.find(d=>d.id===id&&d.region===region);}
 }
 if(!entry)throw Error('이 연결 대상의 본문은 현재 수집 범위에 없습니다. 인용 근거의 공식 원문 링크를 확인해 주세요.');
 const document=currentDoc?.meta.id===id?currentDoc:await read(entry.file);
 if(document.meta.id!==entry.id||document.meta.domain!==entry.domain)throw Error('본문 자료의 법령 정보가 일치하지 않습니다.');
 if(entry.effective&&document.meta.effective!==entry.effective)throw Error('연결 자료와 본문의 시행 판본이 다릅니다. 새 판본을 확인해 주세요.');
 return {entry,document,article:jo?document.articles.find(a=>a.jo===jo):null,requestedJo:jo};
}
