import test from 'node:test';
import assert from 'node:assert/strict';
import {reportContext,makeReport} from '../web/feedback.mjs';
import {pdfPage,pdfConnections,pdfAnchor} from '../web/procurement-pdf.mjs';
test('only public law context is automatically shared',()=>{
 const context=reportContext({domain:'국세',law:'법인세법',reference:'제16조',version:'v1',query:'비공개 검색',location:'file:///secret',token:'private',relatedLaw:'지방계약법',relatedReference:'PDF 4쪽'});
 const report=makeReport('잘못된 연결','연결된 조문이 다릅니다.',context),url=new URL(report.url);
 assert.equal(url.host,'github.com');assert.match(url.searchParams.get('body'),/법인세법/);
 assert.match(report.body,/PDF 4쪽/);assert.doesNotMatch(report.body,/비공개 검색|secret|private/);
 assert.equal(url.searchParams.get('title'),report.title);
});
test('invalid and long reports are safely bounded, encoded and user submitted',()=>{
 assert.throws(()=>makeReport('임의 유형','충분한 설명입니다',{}));
 assert.throws(()=>makeReport('기타','짧음',{}));
 assert.throws(()=>makeReport('기타','가'.repeat(1201),{}));
 const report=makeReport('기타','가'.repeat(1200),{});assert.equal(report.copyRequired,true);
 assert.equal(report.body.includes('가'.repeat(1200)),true);assert.equal(report.url,'https://github.com/gschamisle/law-orbit/issues/new');
 const encoded=makeReport('기타','<script>&? # 오류 내용',{'법령':'법률'});assert.equal(new URL(encoded.url).searchParams.get('body'),encoded.body);
});
test('PDF page slices preserve code-point offsets and reject missing pages',()=>{
 const document={unstructured_text:'표지🌟본문\n다음',pdf_analysis:{pages:[{page:1,start:0,end:2},{page:2,start:2,end:6},{page:3,start:6,end:8}]}};
 assert.equal(pdfPage(document,2).text,'🌟본문\n');assert.throws(()=>pdfPage(document,9));
});
test('internal PDF links keep forward and reverse locations distinct',()=>{
 const document={unstructured_text:'🌟제5장 본문',pdf_analysis:{anchors:[{id:'one',start:1,end:7,label:'제5장'}],internal_connections:[{source_page:4,target_page:165,target_id:'one'}]}};
 assert.equal(pdfConnections(document,4).forward.length,1);assert.equal(pdfConnections(document,4).reverse.length,0);
 assert.equal(pdfConnections(document,165).reverse.length,1);assert.equal(pdfAnchor(document,'one').label,'제5장');
 assert.throws(()=>pdfAnchor(document,'missing'));document.pdf_analysis.anchors[0].label='다른 제목';assert.throws(()=>pdfAnchor(document,'one'));
});
