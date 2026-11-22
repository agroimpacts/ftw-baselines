// macOS JavaScriptCore smoke test; does not require a browser or load map tiles.
// osascript -l JavaScript tests/research/geometry/triage_review_smoke.js INDEX_HTML
ObjC.import('Foundation');

function run(argv) {
    const html = ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError(
        argv[0], $.NSUTF8StringEncoding, null));
    const script = html.split('<script>')[1].split('</script>')[0];
    const elements = new Map();
    function element(tag) {
        return {
            tag, value: '', checked: true, textContent: '', style: {}, children: [],
            appendChild(child) { this.children.push(child); return child; },
            replaceChildren() { this.children = []; },
            click() { if (this.onclick) this.onclick(); },
        };
    }
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, element('div'));
            return elements.get(id);
        },
        createElement: element,
        createTextNode: text => ({textContent: text}),
        querySelector() {
            for (const label of elements.get('cuts').children) {
                for (const child of label.children || []) {
                    if (child.tag === 'input' && child.checked) return child;
                }
            }
            return null;
        },
    };
    const el = document.getElementById;
    el('filter').value = 'all';
    const map = {fitBounds() {}, removeLayer() {}};
    const layer = data => ({
        addTo() { return this; }, getBounds() { return {}; },
        eachLayer(fn) {
            for (const f of data.features || []) {
                fn({feature: f, setStyle() {}});
            }
        },
    });
    const L = {map: () => map, tileLayer: () => layer({}), geoJSON: layer};
    let exported = null;
    const URL = {createObjectURL(blob) { exported = JSON.parse(blob.parts[0]); return 'blob:test'; }, revokeObjectURL() {}};
    function Blob(parts) { this.parts = parts; }
    const api = new Function('document', 'L', 'window', 'Blob', 'URL', script +
        '\nreturn {data, records, reviews, focus};')(
        document, L, {addEventListener() {}}, Blob, URL);
    function assert(condition, message) { if (!condition) throw new Error(message); }
    assert(el('candidate').children.length === api.data.candidates.length, 'Initial population');
    for (const outcome of ['exclude', 'repair', 'retain', 'abstain']) {
        el('filter').value = outcome; el('filter').onchange();
        const expected = api.data.candidates.filter(c => c.proposed_outcome === outcome);
        assert(el('candidate').children.length === expected.length, 'Filter: ' + outcome);
        assert(expected.length > 0, 'Real demo must have all four outcome routes');
    }
    el('record').onclick();
    assert(api.reviews.size === 0, 'Anonymous review must not be recorded');
    el('reviewer').value = 'smoke-test';
    el('decision').value = 'retain'; el('notes').value = 'test'; el('record').onclick();
    assert(api.reviews.size === 1, 'Record label');
    const withCut = api.data.candidates.find(c => c.cut_proposal_ids.length > 0);
    api.focus(withCut.field_key);
    el('cuts').children[0].children[0].checked = true;
    el('decision').value = 'repair'; el('record').onclick();
    const review = api.reviews.get(withCut.field_key);
    assert(withCut.cut_proposal_ids.includes(review.selected_proposal_id), 'Exact proposal identity');
    el('download').onclick();
    assert(exported.run_id === api.data.run_id, 'Export run identity');
    assert(exported.application_authorized === false, 'Export cannot authorize application');
    assert(exported.reviews.every(r => r.application_authorized === false), 'Labels cannot authorize application');
    assert(exported.reviews.every(r => r.source_geometry_sha256.length === 64), 'Parent geometry hashes');
    return 'PASS: four filters, reviewer gate, exact cut selection, export provenance and no-application guard';
}
