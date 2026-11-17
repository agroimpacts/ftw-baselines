// osascript -l JavaScript tests/research/geometry/repair_review_smoke.js INDEX_HTML
ObjC.import('Foundation');
function run(argv) {
    const html=ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError(argv[0],$.NSUTF8StringEncoding,null));
    const script=html.split('<script>')[1].split('</script>')[0],elements=new Map();
    function element(tag){return {tag,value:'',checked:true,textContent:'',style:{},children:[],appendChild(c){this.children.push(c);return c},replaceChildren(){this.children=[]},click(){if(this.onclick)this.onclick()}}}
    const document={getElementById(id){if(!elements.has(id))elements.set(id,element('div'));return elements.get(id)},createElement:element};
    const el=document.getElementById,map={fitBounds(){},removeLayer(){}};
    const layer=()=>({addTo(){return this},getBounds(){return {}}});
    const L={map:()=>map,tileLayer:layer,geoJSON:layer};let exported=null;
    const URL={createObjectURL(blob){exported=JSON.parse(blob.parts[0]);return 'blob:test'},revokeObjectURL(){}};
    function Blob(parts){this.parts=parts}
    const api=new Function('document','L','window','Blob','URL',script+'\nreturn {data,reviews,selectCase};')(document,L,{addEventListener(){}},Blob,URL);
    function assert(value,message){if(!value)throw new Error(message)}
    assert(el('case').children.length===4,'Four targeted cases');
    for(const c of api.data.cases){api.selectCase(c.case_id);assert(el('title').textContent.includes(c.status),'Case status');assert(el('proposal').children.length>=1,'Alternative or abstention');el('whole').onclick();el('cutsZoom').onclick()}
    el('record').onclick();assert(api.reviews.size===0,'Reviewer required');
    el('reviewer').value='smoke';el('decision').value='changes_needed';el('record').onclick();
    const split=api.data.cases.find(c=>c.repair_subtype==='split'&&c.proposal_ids.length);
    api.selectCase(split.case_id);el('decision').value='prefer';el('record').onclick();
    const unresolved=api.data.cases.find(c=>!c.proposal_ids.length);api.selectCase(unresolved.case_id);el('decision').value='changes_needed';el('record').onclick();
    el('export').onclick();assert(exported.run_id===api.data.run_id,'Run identity');assert(!exported.application_authorized,'No application authorization');
    assert(exported.reviews.length===3,'Three assessments');assert(exported.reviews.every(r=>!r.application_authorized),'Per-review no-application guard');
    assert(exported.reviews.find(r=>r.assessment==='prefer').proposal_id===split.proposal_ids[0],'Exact proposal preference');
    return 'PASS: four cases, split/union/abstention rendering, reviewer gate, exact proposal identity, no-application export';
}
