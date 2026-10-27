/* Text stays in browser state; algorithm requests send it to the local Flask API. */
(() => {
  'use strict';
  // Find workspace controls and result containers by their HTML IDs.
  const $ = id => document.getElementById(id);
  const studio = $('textLab');
  const workerURL = new URL('search-worker.js', document.currentScript.src);
  const state = {documents: [], editorIndex: null, busy: false, tab: 'search', search: {}, compression: {}, parallel: null, optimization: null, timings: {}, urls: new Map()};
  const algorithmInfo = {
    kmp: ['KMP', 'O(n + m)', 'O(m + z)', 'Server · compute'],
    brute: ['Brute Force', 'O(n × m)', 'O(n + m + z)', 'Browser worker · compute'],
    huffman: ['Huffman compression', 'O(n + k log k + B)', 'O(kL + B)', 'Server · compute'],
    rle: ['RLE compression', 'O(n)', 'O(c)', 'Server · compute'],
    auto: ['Smallest file', 'O(n + k log k + B)', 'O(n + kL + B)', 'Server · both compressors and selection'],
    quicksort: ['Quick Sort', 'O(N + F log F) expected; O(N + F²) worst', 'O(nmax + F²) worst case', 'Server · sizing and sorting'],
    knapsack: ['0/1 knapsack', 'O(F × C)', 'O(F × C)', 'Server · selection only'],
    parallel: ['Parallel KMP', 'Ideal O((N + Fm) / p) + overhead', 'O(N + pm + Z) + process overhead', 'Server · wall time'],
    restore: ['Decompression', 'Huffman: O(k log k + B + n); RLE: O(c + n)', 'Huffman: O(k + n); RLE: O(n)', 'Browser · request round trip']
  };
  // Format result values for display as numbers, bytes, or milliseconds.
  const fmt = n => new Intl.NumberFormat(undefined, {maximumFractionDigits: 3}).format(n);
  const bytes = n => `${fmt(n)} B`;
  const ms = n => `${fmt(n)} ms`;
  const methodName = method => ({huffman: 'Huffman', rle: 'RLE', original: 'Original text', auto: 'Smallest file'})[method];
  const fileDownload = item => download(item.method === 'original' ? item.name : `${item.name}.${item.method}.wgc`, packedBlob(item.payload));
  // Count UTF-8 bytes in browser documents for size limits and summaries.
  const totalBytes = () => state.documents.reduce((sum, doc) => sum + new TextEncoder().encode(doc.text).length, 0);
  // Build a DOM element for workspace results and controls.
  function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
  // Store help text on an element for the shared tooltip.
  function help(node, message) { node.dataset.help = message; return node; }
  // Build a button and connect clicks to its supplied action.
  function button(text, message, action, className = 'studio-button secondary') { const node = help(el('button', text, className), message); node.type = 'button'; node.addEventListener('click', action); return node; }
  // Show progress or errors in the workspace status bar.
  function setStatus(message, type = '') {
    $('statusText').textContent = message; $('status').className = `studio-status ${type}`;
    $('analysisState').textContent = type === 'busy' ? 'Running' : type === 'error' ? 'Check input' : Object.keys(state.timings).length ? 'Completed' : 'Ready';
  }
  // Return a labeled value card for result summaries.
  function metric(label, value, message, note = '', style = '') {
    const node = el('dl', undefined, `metric ${style}`);
    node.append(help(el('dt', label), message), el('dd', value)); if (note) node.append(el('small', note)); return node;
  }
  // Return a placeholder card, optionally linking back to text input.
  function empty(title, detail, goToInput = false) {
    const node = el('div', undefined, 'empty-state'); node.append(el('b', title), el('span', detail));
    if (goToInput) node.append(button('Add text', 'Use the dataset editor on the left.', () => selectTab('input', true)));
    return node;
  }
  // Return a titled result container with help text.
  function card(title, guide) { const node = el('div', undefined, 'studio-card'); node.append(help(el('h3', title), guide)); return node; }
  // Remove displayed results and release their browser download URLs.
  function clearContainer(id) {
    const node = $(id); for (const a of node.querySelectorAll('a[data-download]')) { URL.revokeObjectURL(a.href); state.urls.delete(a.href); }
    node.replaceChildren();
  }
  // Create a browser download link from a Blob; files save when clicked.
  function download(name, blob) {
    const a = help(el('a', 'Download', 'studio-download'), `Saves ${name} to your device.`);
    a.href = URL.createObjectURL(blob); a.download = name; a.dataset.download = 'true'; state.urls.set(a.href, true); return a;
  }
  // Decode an API base64 payload into binary bytes for a browser download.
  function packedBlob(payload) { return new Blob([Uint8Array.from(atob(payload), c => c.charCodeAt(0))], {type: 'application/octet-stream'}); }
  // Render supplied headers and rows into a scrollable DOM table.
  function table(parent, headers, rows) {
    const t = el('table'), head = el('thead'), tr = el('tr'), body = el('tbody');
    for (const [label, guide] of headers) tr.append(help(el('th', label), guide)); head.append(tr); t.append(head);
    for (const row of rows) { const r = el('tr'); for (const value of row) { const td = el('td'); td.append(value instanceof Node ? value : document.createTextNode(String(value))); r.append(td); } body.append(r); }
    t.append(body);
    if (parent.classList.contains('table-scroll')) parent.append(t);
    else { const scroll = el('div', undefined, 'table-scroll'); scroll.append(t); parent.append(scroll); }
  }
  // Store the latest algorithm timing in browser state and refresh the comparison.
  function record(key, elapsed, note = '') { state.timings[key] = {elapsed, note, files: state.documents.length, bytes: totalBytes()}; renderPerformance(); }
  // Draw runtime bars from measured values in the supplied result container.
  function chart(parent, values, title, explanation) {
    const c = card(title, 'Bars show measured milliseconds for the latest run. A shorter bar means less measured time.');
    const max = Math.max(...values.map(v => v[1]), 0.001);
    for (const [name, elapsed] of values) {
      const row = el('div', undefined, 'runtime-row'), track = el('div', undefined, 'runtime-track'), fill = el('div', undefined, 'runtime-fill');
      fill.style.width = `${Math.max(0, elapsed / max * 100)}%`; track.append(fill); track.setAttribute('aria-hidden', 'true');
      row.append(help(el('span', name), `Latest measured runtime for ${name}.`), track, help(el('span', ms(elapsed), 'runtime-value'), 'Measured elapsed time in milliseconds. Very short runs may round to zero.')); c.append(row);
    }
    if (explanation) c.append(el('p', explanation, 'field-hint')); parent.append(c);
  }
  // Switch the active Text Lab panel and update keyboard focus if requested.
  function selectTab(name, focus = false) {
    if (name === 'input') { hideTooltip(); $('text').focus(); return; }
    if (!$(`panel-${name}`)) return;
    state.tab = name;
    for (const tab of document.querySelectorAll('[data-tab]')) { const active = tab.dataset.tab === name; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; $(`panel-${tab.dataset.tab}`).hidden = !active; }
    hideTooltip(); if (focus) $(`panel-${name}`).focus({preventScroll: false});
  }
  // Keep the visible editor attached to a loaded document without clearing its text.
  function editorDirty() {
    const doc = state.documents[state.editorIndex];
    return doc ? doc.name !== $('name').value.trim() || doc.text !== $('text').value : $('text').value.length > 0;
  }
  function loadEditor(index) {
    state.editorIndex = index;
    const doc = state.documents[index];
    $('name').value = doc ? doc.name : 'My document.txt'; $('text').value = doc ? doc.text : '';
    updateControls();
  }
  function saveEditor() {
    if (!editorDirty()) return;
    const index = state.editorIndex, doc = state.documents[index];
    const incoming = {name: $('name').value.trim(), text: $('text').value, priority: doc ? doc.priority : 1};
    if (!incoming.name) throw new Error('Enter a dataset name.');
    if (!doc && !incoming.text.length) throw new Error('Enter some text first.');
    const combined = doc ? state.documents.map((item, i) => i === index ? incoming : item) : [...state.documents, incoming];
    validateDocuments(combined);
    state.documents = combined; state.editorIndex = doc ? index : combined.length - 1;
    datasetChanged();
  }
  // Enable or disable inputs and actions using dataset validity and busy state.
  function updateControls() {
    const dirty = editorDirty();
    const characters = Array.from($('text').value).length;
    $('editorMeta').textContent = `${fmt(characters)} character${characters === 1 ? '' : 's'} · ${bytes(new TextEncoder().encode($('text').value).length)}`;
    $('editorState').hidden = !dirty;
    $('add').textContent = state.editorIndex === null ? 'Add dataset' : 'Save changes';
    $('inputHint').textContent = dirty ? 'Save your text to use it in analysis.' : state.documents.length ? 'Analysis uses all loaded datasets.' : 'Add text or load a sample.';
    const docs = state.documents.length > 0, pattern = $('pattern').value.length > 0;
    const priorityValid = state.documents.every(doc => Number.isInteger(doc.priority) && doc.priority >= 1 && doc.priority <= 1000);
    const budget = Number($('capacity').value), budgetValid = $('capacity').value !== '' && Number.isInteger(budget) && budget >= 0 && budget <= 100000;
    const disabled = {
      add: !dirty || !$('name').value.trim().length || (state.editorIndex === null && !$('text').value.length),
      sample: state.documents.length > 27, clear: !docs, clearDraft: state.editorIndex === null && !$('text').value.length,
      search: !docs || !pattern, brute: !docs || !pattern, compareSearch: !docs || !pattern,
      auto: !docs, huffman: !docs, rle: !docs, compareCompression: !docs, quicksort: !docs,
      runAll: !docs || !budgetValid || !priorityValid,
      optimize: !docs || !budgetValid || !priorityValid,
      parallel: state.documents.length < 2 || !pattern, compareParallel: state.documents.length < 2 || !pattern,
      clearSearch: !Object.keys(state.search).length, clearCompression: !Object.keys(state.compression).length,
      clearOptimization: !state.optimization, clearParallel: !state.parallel,
      clearTimings: !Object.keys(state.timings).length
    };
    for (const [id, invalid] of Object.entries(disabled)) $(id).setAttribute('aria-disabled', String(state.busy || invalid || (dirty && $(id).hasAttribute('data-analysis-action'))));
    document.querySelectorAll('[data-needs-documents]').forEach(node => node.setAttribute('aria-disabled', String(state.busy || !docs)));
    studio.querySelectorAll('input,textarea,select').forEach(node => { node.disabled = state.busy; });
    studio.querySelectorAll('[data-mutates-dataset]').forEach(node => node.setAttribute('aria-disabled', String(state.busy)));
  }
  // Clear cached search results, timings, and displayed matches.
  function clearSearch() { state.search = {}; delete state.timings.kmp; delete state.timings.brute; clearContainer('searchResults'); clearContainer('searchComparison'); }
  // Clear cached parallel results, timing, and their display.
  function clearParallel() { state.parallel = null; delete state.timings.parallel; clearContainer('parallelResults'); }
  // Clear cached file selections, knapsack timing, and their display.
  function clearOptimization() { state.optimization = null; delete state.timings.knapsack; clearContainer('optimizationResults'); $('batchSummary').replaceChildren(); }
  // Discard stale results and refresh the UI after browser documents change.
  function datasetChanged() {
    clearSearch(); clearParallel(); clearOptimization(); state.compression = {}; state.timings = {};
    clearContainer('compressionResults'); clearContainer('restored'); renderDataset(); renderPerformance(); updateControls(); decorate();
    clearContainer('sortResults'); $('batchSummary').replaceChildren();
  }
  // Build a priority input that updates the document and invalidates file selections.
  function priorityInput(doc, index, label) {
    const input = help(el('input', undefined, 'file-priority'), 'A whole number from 1 to 1,000. Higher-priority files contribute more value to storage optimization.');
    input.type = 'number'; input.min = '1'; input.max = '1000'; input.step = '1'; input.value = doc.priority; input.setAttribute('aria-label', `${label} priority for ${doc.name}`); input.dataset.priorityIndex = index;
    input.addEventListener('input', () => {
      doc.priority = input.value === '' ? NaN : Number(input.value);
      studio.querySelectorAll(`[data-priority-index="${index}"]`).forEach(other => { if (other !== input) other.value = input.value; });
      clearOptimization(); renderPerformance(); updateControls();
    }); return input;
  }
  // Show browser-held document names, sizes, priorities, and removal controls.
  function renderDataset() {
    const count = state.documents.length; $('docCount').textContent = `${count} file${count === 1 ? '' : 's'}`;
    $('datasetBadge').textContent = count ? `${count} dataset${count === 1 ? '' : 's'} · ${bytes(totalBytes())}` : 'No datasets loaded';
    $('dataset').replaceChildren(); $('priorities').replaceChildren();
    if (!count) { $('dataset').append(el('p', 'No datasets loaded.', 'dataset-empty')); $('priorities').append(el('p', 'Load datasets to set priorities.')); }
    else {
      state.documents.forEach((doc, i) => {
        const item = el('div', undefined, 'dataset-item');
        const select = button('', 'View and edit this dataset.', () => {
          if (state.busy || state.editorIndex === i) return;
          try { saveEditor(); loadEditor(i); renderDataset(); decorate(); setStatus(`Viewing ${state.documents[i].name}.`); }
          catch (error) { setStatus(error.message, 'error'); }
        }, 'dataset-select');
        select.setAttribute('aria-pressed', String(state.editorIndex === i)); select.dataset.mutatesDataset = 'true';
        const heading = el('span', undefined, 'dataset-item-heading'); heading.append(el('strong', doc.name), el('span', bytes(new TextEncoder().encode(doc.text).length)));
        select.append(heading, el('span', doc.text.slice(0, 90) || 'Empty text', 'dataset-snippet'));
        const remove = button('×', `Remove ${doc.name}.`, () => {
          if (state.busy) return;
          state.documents.splice(i, 1);
          if (state.editorIndex === i) loadEditor(state.documents.length ? Math.min(i, state.documents.length - 1) : null);
          else if (state.editorIndex !== null && state.editorIndex > i) state.editorIndex--;
          datasetChanged(); setStatus('Dataset removed.');
        }, 'dataset-remove');
        remove.setAttribute('aria-label', `Remove ${doc.name}`); remove.dataset.mutatesDataset = 'true';
        item.append(select, remove); $('dataset').append(item);
        const row = el('div', undefined, 'priority-row'); row.append(help(el('span', doc.name), 'The document whose importance you are setting.'), priorityInput(doc, i, 'Optimizer')); $('priorities').append(row);
      });
    }
    studio.querySelectorAll('[data-empty-gate]').forEach(node => { node.replaceChildren(); if (!count) node.append(empty('No dataset loaded', 'Add text or files on the left.', true)); });
  }
  // Validate the complete collection before changing browser-held documents.
  function validateDocuments(combined) {
    if (combined.length > 30) throw new Error('You can load up to 30 documents. Remove one before adding more.');
    if (combined.some(doc => !doc.name.trim() || doc.name.length > 255)) throw new Error('Use document names with 1 to 255 characters.');
    if (combined.reduce((sum, doc) => sum + new TextEncoder().encode(doc.text).length, 0) > 2000000) throw new Error('Your dataset exceeds 2 MB. Try fewer files or shorter text.');
  }
  function addDocuments(incoming) {
    const combined = [...state.documents, ...incoming]; validateDocuments(combined);
    const first = state.documents.length;
    state.documents = combined; loadEditor(first); datasetChanged();
  }
  // POST documents or a restore payload to /api/text/<action> and return parsed JSON.
  async function api(action, extra = {}) {
    let response;
    try { response = await fetch(`/api/text/${action}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(action === 'decompress' ? extra : {documents: state.documents, ...extra})}); }
    catch { throw new Error('We could not reach the server. Check that Wayglyph is running, then try again.'); }
    let result; try { result = await response.json(); } catch { throw new Error('The server could not read this request. Try a smaller file or dataset.'); }
    if (!response.ok) throw new Error(result.error || 'That operation could not finish. Please try again.'); return result;
  }
  // Run one UI action while showing progress, blocking repeat clicks, and reporting errors.
  async function run(id, message, action) {
    const node = $(id); if (state.busy) return;
    if (node.getAttribute('aria-disabled') === 'true') {
      setStatus(editorDirty() ? 'Save your text before running analysis.' : !state.documents.length ? 'Load a dataset on the left.' : id.includes('arallel') || id === 'parallel' ? 'Parallel search needs at least two datasets and a search pattern.' : ['optimize', 'runAll'].includes(id) ? 'Use a budget from 0 to 100,000 and priorities from 1 to 1,000.' : 'Fill in the required input.', 'error'); return;
    }
    state.busy = true; studio.setAttribute('aria-busy', 'true'); node.classList.add('is-loading'); updateControls(); setStatus(message, 'busy');
    try { const success = await action(); setStatus(success || 'Done. Your results are ready below.'); }
    catch (error) { setStatus(error.message || 'Something went wrong. Please try again.', 'error'); }
    finally { state.busy = false; studio.setAttribute('aria-busy', 'false'); node.classList.remove('is-loading'); updateControls(); decorate(); }
  }
  // Return a text preview with matched character positions highlighted.
  function highlighted(text, positions, pattern) {
    const chars = Array.from(text), length = Array.from(pattern).length;
    const start = positions.length ? Math.max(0, positions[0] - 80) : 0, end = Math.min(chars.length, start + 2000);
    const preview = el('div', undefined, 'text-preview'); let cursor = start;
    for (const match of positions) {
      if (match >= end) break; if (match + length <= start) continue;
      if (match > cursor) preview.append(document.createTextNode(chars.slice(cursor, match).join('')));
      const to = Math.min(end, match + length);
      if (to > cursor) preview.append(el('mark', chars.slice(Math.max(cursor, match), to).join('')));
      cursor = Math.max(cursor, to);
    }
    preview.append(document.createTextNode(chars.slice(cursor, end).join('')));
    return [preview, el('div', `Preview: characters ${fmt(start)}–${fmt(end)} of ${fmt(chars.length)}.`, 'preview-caption')];
  }
  // Render API or worker match counts, positions, and document previews.
  function renderMatches(parent, result, title, pattern) {
    const total = result.results.reduce((sum, r) => sum + r.count, 0);
    if (!total) parent.append(empty('No matches this time.', 'Try a shorter phrase or check capitalization. Your text is still loaded.'));
    result.results.forEach((r, i) => {
      const c = el('div', undefined, 'studio-card'), heading = el('div', undefined, 'result-heading');
      heading.append(help(el('h3', r.name), 'The document searched in this run.'), help(el('span', `${title} · ${fmt(r.count)} match${r.count === 1 ? '' : 'es'}`, 'result-chip'), 'Number of exact occurrences, including overlapping matches.')); c.append(heading);
      c.append(help(el('div', `Positions: ${r.positions.slice(0, 100).map(fmt).join(', ') || 'none'}${r.positions.length > 100 ? ' … (first 100 shown)' : ''}`, 'positions'), 'Zero-based Unicode character positions where each match starts.'));
      c.append(...highlighted(state.documents[i].text, r.positions, pattern)); parent.append(c);
    });
  }
  // Send documents and the pattern to search-worker.js and return its search results.
  async function bruteForce() {
    return new Promise((resolve, reject) => {
      let worker;
      try { worker = new Worker(workerURL); } catch { reject(new Error('Browser workers are unavailable. KMP search still works.')); return; }
      const timeout = setTimeout(() => { worker.terminate(); reject(new Error('Brute Force took too long. Try less text or a shorter phrase.')); }, 15000);
      // Stop the browser worker and its timer after a result or failure.
      const finish = () => { clearTimeout(timeout); worker.terminate(); };
      worker.onmessage = ({data}) => { finish(); data.error ? reject(new Error(data.error)) : resolve(data); };
      worker.onerror = () => { finish(); reject(new Error('The browser worker could not start. Try KMP search instead.')); };
      worker.postMessage({documents: state.documents.map(({name, text}) => ({name, text})), pattern: $('pattern').value});
    });
  }
  // Run server KMP or browser Brute Force, cache results, and show matches.
  async function searchAlgorithm(key) {
    const result = key === 'kmp' ? await api('search', {pattern: $('pattern').value}) : await bruteForce();
    state.search[key] = result; record(key, result.results.reduce((sum, r) => sum + r.elapsed_ms, 0), 'Total compute time across documents');
    renderSearch(key); return result.results.reduce((sum, r) => sum + r.count, 0);
  }
  // Display cached search results and the latest runtime comparison.
  function renderSearch(latest) {
    clearContainer('searchComparison'); clearContainer('searchResults');
    const keys = ['kmp', 'brute'].filter(k => state.search[k]);
    if (keys.length) chart($('searchComparison'), keys.map(k => [algorithmInfo[k][0], state.search[k].results.reduce((sum, r) => sum + r.elapsed_ms, 0)]), 'Search runtime', 'KMP: server compute ? Brute Force: browser worker.');
    renderMatches($('searchResults'), state.search[latest], algorithmInfo[latest][0], $('pattern').value); decorate();
  }
  // POST documents to /api/text/compress, cache returned payloads, and show results.
  async function compress(method) {
    const result = await api('compress', {method}); state.compression[method] = result;
    record(method, result.results.reduce((sum, r) => sum + r.elapsed_ms, 0), 'Total compression time across documents'); renderCompression();
  }
  // Show compression statistics and create downloads from cached API payloads.
  function renderCompression() {
    clearContainer('compressionResults'); const out = $('compressionResults');
    const methods = ['auto', 'huffman', 'rle'].filter(method => state.compression[method]);
    if (methods.length) chart(out, methods.map(method => [methodName(method), state.compression[method].results.reduce((sum, r) => sum + r.elapsed_ms, 0)]), 'Compression runtime', 'Server compute, including headers and binary encoding. Smallest file runs both compressors before choosing.');
    for (let i = 0; i < state.documents.length; i++) {
      const c = card(state.documents[i].name, 'Compression results for this document. Sizes include the decoding header and checksum.');
      const cards = el('div', undefined, 'comparison-grid');
      for (const method of methods) {
        const r = state.compression[method].results[i], choice = el('div'); choice.append(help(el('h3', method === 'auto' ? `Smallest file · ${methodName(r.method)}` : methodName(method)), method === 'auto' ? 'The smallest of both compressed formats and the original text.' : method === 'huffman' ? 'Shorter codes represent more frequent bytes.' : 'Repeated runs and literal blocks.'));
        const metrics = el('div', undefined, 'metrics-grid'); metrics.append(
          metric('Original size', bytes(r.original_bytes), 'Original UTF-8 text size in bytes.'),
          metric('Download size', bytes(r.compressed_bytes), 'Actual downloadable size. Compressed files include a header and checksum; original text stays unchanged.'),
          metric('Compression ratio', r.ratio === null ? 'N/A' : fmt(r.ratio), 'Compressed size divided by original size. Lower means better compression.', r.ratio === null ? 'Empty text has no ratio.' : ''),
          metric('Space saved', r.savings_percent === null ? 'N/A' : `${fmt(r.savings_percent)}%`, 'Percent reduction from the original size. A negative value means the compressed file grew.', r.method === 'original' ? 'Original kept: compression would not save space.' : r.savings_percent < 0 ? 'Encoding overhead exceeds savings. Try Get smallest file.' : '', r.savings_percent > 0 ? 'good' : r.savings_percent < 0 ? 'bad' : '')
        ); choice.append(metrics, help(el('p', `Server runtime: ${ms(r.elapsed_ms)}`), 'Measured compression computation time for this document.'), fileDownload(r)); cards.append(choice);
      }
      c.append(cards); out.append(c);
    } decorate();
  }
  // Show API file selections and download links for the chosen compressed files.
  function renderOptimization(result) {
    clearContainer('optimizationResults'); const out = $('optimizationResults'), c = card('Your best selection', 'The exact maximum-total-priority subset that fits the specified byte budget.');
    const metrics = el('div', undefined, 'metrics-grid'); metrics.append(
      metric('Selected files', `${result.selected_indices.length} / ${result.items.length}`, 'Number of files chosen from your dataset.'),
      metric('Space used', bytes(result.used_bytes), 'Sum of actual download sizes of the selected files.', `Budget: ${bytes(result.capacity_bytes)}`),
      metric('Total priority', fmt(result.total_priority), 'Sum of priorities for selected files. The optimizer maximizes this value.', '', 'good'),
      metric('Selection time', ms(result.elapsed_ms), 'Knapsack computation time, excluding compression preparation.')
    ); c.append(metrics);
    if (!result.selected_indices.length) c.append(el('p', 'No file fits this budget. Increase the budget or try a smaller document.'));
    table(c, [['File', 'Your original document name.'], ['Method', 'The smallest of Huffman, RLE and original text.'], ['Size', 'Actual download size in bytes.'], ['Priority', 'Value contributed if selected.'], ['Selection', 'Selected files fit together within the budget.'], ['Download', 'Download selected files.']], result.items.map((item, i) => {
      const selected = result.selected_indices.includes(i); return [item.name, methodName(item.method), bytes(item.compressed_bytes), item.priority, el('span', selected ? '✓ Selected' : 'Excluded', selected ? 'selection-yes' : 'selection-no'), selected ? fileDownload(item) : '—'];
    })); out.append(c); decorate();
  }
  function renderSort(result) {
    clearContainer('sortResults');
    const c = card('Files by size · Quick Sort', 'Files ordered by original UTF-8 size, smallest first.');
    c.append(el('p', `Server runtime: ${ms(result.elapsed_ms)}`, 'field-hint'));
    table(c, [['File', 'Document name.'], ['Original size', 'UTF-8 byte size.']], result.results.map(item => [item.name, bytes(item.original_bytes)]));
    $('sortResults').append(c); decorate();
  }
  // Show process search results and optional sequential timing comparisons.
  function renderParallel(result, sequential) {
    clearContainer('parallelResults'); const out = $('parallelResults');
    const summary = el('div', undefined, 'metrics-grid'); summary.append(metric('Worker processes', String(result.workers), 'Independent Python processes used for this search; at most four.'), metric('Parallel wall time', ms(result.elapsed_ms), 'Includes worker startup, data transfer, and searching.')); out.append(summary);
    if (sequential) chart(out, [['Sequential KMP', sequential.results.reduce((sum, r) => sum + r.elapsed_ms, 0)], ['Parallel KMP', result.elapsed_ms]], 'Execution comparison', 'Sequential: compute ? Parallel: wall time, including worker startup and transfer.');
    renderMatches(out, result, 'Parallel KMP', $('pattern').value); decorate();
  }
  // Refresh runtime charts and complexity details from cached browser timings.
  function renderPerformance() {
    $('performanceSummary').replaceChildren(metric('Documents', String(state.documents.length), 'Number of documents in the current dataset.'), metric('Dataset size', bytes(totalBytes()), 'Combined UTF-8 size of loaded documents.'), metric('Algorithms measured', String(Object.keys(state.timings).length), 'Algorithms with a recorded runtime for this dataset. Each row shows its latest run.'));
    $('runtimeChart').replaceChildren();
    const entries = Object.entries(state.timings);
    if (!entries.length) $('runtimeChart').append(empty('No measurements yet', 'Run an analysis to compare its runtime.'));
    else {
      $('runtimeChart').append(el('h3', 'Latest measured runtimes'));
      for (const [keys, title] of [[['kmp', 'brute'], 'Pattern matching'], [['auto', 'huffman', 'rle'], 'Compression'], [['knapsack', 'quicksort'], 'Storage selection and sorting'], [['parallel'], 'Parallel execution'], [['restore'], 'Restoration round trip']]) {
        const present = keys.filter(k => state.timings[k]); if (present.length) chart($('runtimeChart'), present.map(k => [algorithmInfo[k][0], state.timings[k].elapsed]), title, present.includes('brute') ? 'Server KMP and browser Brute Force run in different environments.' : '');
      }
    }
    $('performanceTable').replaceChildren();
    table($('performanceTable'), [['Algorithm', 'The implemented method used for this operation.'], ['Time · Big-O', 'Shows how time grows as the input gets larger. Constants and actual hardware are not included.'], ['Space · Big-O', 'Shows how memory grows, including output and implementation buffers.'], ['Measured time', 'Latest elapsed time for this dataset. Not run means no measurement is recorded.'], ['Timing scope', 'Where and what the timer measures; compare like-for-like scopes.']], Object.entries(algorithmInfo).map(([key, info]) => [info[0], info[1], info[2], state.timings[key] ? ms(state.timings[key].elapsed) : 'Not run', info[3]]));
    decorate();
  }

  // One shared tooltip portal: no clipping inside tables or containers.
  const tooltip = el('div', undefined, 'guide-tooltip'); tooltip.id = 'wayglyphGuide'; tooltip.setAttribute('role', 'tooltip'); tooltip.hidden = true; document.body.append(tooltip);
  let tipTarget = null, tipTimer = null, tipHovered = false;
  // Position the shared help tooltip inside the visible browser viewport.
  function positionTooltip() {
    if (!tipTarget || !tipTarget.isConnected) { hideTooltip(); return; }
    const viewport = window.visualViewport, width = viewport ? viewport.width : window.innerWidth, height = viewport ? viewport.height : window.innerHeight;
    const offsetX = viewport ? viewport.offsetLeft : 0, offsetY = viewport ? viewport.offsetTop : 0;
    tooltip.style.maxWidth = `${Math.max(24, Math.min(310, width - 24))}px`;
    tooltip.style.maxHeight = `${Math.max(24, height - 24)}px`;
    const rect = tipTarget.getBoundingClientRect(), bounds = tooltip.getBoundingClientRect();
    const left = Math.max(offsetX + 12, Math.min(rect.left + rect.width / 2 - bounds.width / 2, offsetX + width - bounds.width - 12));
    let top = rect.bottom + 10; if (top + bounds.height > offsetY + height - 12) top = rect.top - bounds.height - 10;
    tooltip.style.left = `${left}px`; tooltip.style.top = `${Math.max(offsetY + 12, Math.min(top, offsetY + height - bounds.height - 12))}px`;
  }
  // Hide the shared tooltip and remove its accessibility reference.
  function hideTooltip() {
    clearTimeout(tipTimer); if (tipTarget) { const ids = (tipTarget.getAttribute('aria-describedby') || '').split(' ').filter(id => id && id !== tooltip.id); if (ids.length) tipTarget.setAttribute('aria-describedby', ids.join(' ')); else tipTarget.removeAttribute('aria-describedby'); }
    tipTarget = null; tooltip.hidden = true;
  }
  // Read an element help message and display it in the shared tooltip.
  function showTooltip(target) {
    if (!target || !target.dataset.help) return; hideTooltip(); tipTarget = target; tooltip.textContent = target.dataset.help; tooltip.hidden = false;
    const ids = target.getAttribute('aria-describedby'); target.setAttribute('aria-describedby', `${ids ? ids + ' ' : ''}${tooltip.id}`); positionTooltip();
  }
  // Delay tooltip dismissal so the pointer can move onto its content.
  function scheduleHide() { clearTimeout(tipTimer); tipTimer = setTimeout(() => { if (!tipHovered && document.activeElement !== tipTarget) hideTooltip(); }, 160); }
  // Add help indicators to elements that have data-help messages.
  function decorate(root = document) {
    for (const node of root.querySelectorAll('[data-help]')) {
      // Keep routine studio controls clean; their help remains on hover/focus.
      if (studio.contains(node) && !node.matches('th,dt,.guide-info')) continue;
      if (node.dataset.guided && (!node.matches('button,a') || node.classList.contains('guide-info') || node.querySelector('.guide-dot'))) continue;
      node.dataset.guided = 'true';
      if (node.matches('button,a') && !node.classList.contains('guide-info')) { const dot = el('span', '?', 'guide-dot'); dot.setAttribute('aria-hidden', 'true'); node.append(dot); }
      else if (node.matches('label,th,dt,h3,.dataset-badge,.result-chip,.runtime-value,.positions')) {
        const info = help(el('button', undefined, 'guide-info'), node.dataset.help); info.type = 'button'; info.dataset.guided = 'true'; info.setAttribute('aria-label', `About ${node.textContent.trim()}`);
        const dot = el('span', '?', 'guide-dot'); dot.setAttribute('aria-hidden', 'true'); info.append(dot); node.append(info);
      }
    }
  }
  document.addEventListener('pointerover', event => { const target = event.target.closest('[data-help]'); if (target && target !== tipTarget) showTooltip(target); });
  document.addEventListener('pointerout', event => { const target = event.target.closest('[data-help]'); if (target && !target.contains(event.relatedTarget)) scheduleHide(); });
  document.addEventListener('focusin', event => { const target = event.target.closest('[data-help]'); if (target) showTooltip(target); else hideTooltip(); });
  document.addEventListener('focusout', scheduleHide);
  document.addEventListener('pointerdown', event => { if (!event.target.closest('[data-help],#wayglyphGuide')) hideTooltip(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hideTooltip(); });
  tooltip.addEventListener('pointerenter', () => { tipHovered = true; clearTimeout(tipTimer); }); tooltip.addEventListener('pointerleave', () => { tipHovered = false; scheduleHide(); });
  document.addEventListener('click', event => { const info = event.target.closest('.guide-info'); if (info) { event.preventDefault(); showTooltip(info); } }, true);
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-help]');
    if (target && !target.closest('[hidden]')) showTooltip(target);
  });
  window.addEventListener('resize', positionTooltip); document.addEventListener('scroll', hideTooltip, true);
  if (window.visualViewport) { window.visualViewport.addEventListener('resize', positionTooltip); window.visualViewport.addEventListener('scroll', hideTooltip); }

  // Tabs and workspace navigation remain available while a calculation runs.
  window.wayglyphRefreshGuides = decorate;
  // Switch between the map and Text Lab panels without moving document data.
  window.wayglyphWorkspace = name => {
    const text = name !== 'map'; studio.hidden = !text; $('mapWorkspace').hidden = text;
    document.querySelectorAll('[data-workspace]').forEach(node => node.setAttribute('aria-pressed', String((node.dataset.workspace === 'text') === text)));
    document.querySelectorAll('[data-text-lab-toggle]').forEach(node => node.setAttribute('aria-expanded', String(text))); hideTooltip();
  };
  document.querySelectorAll('[data-workspace]').forEach(node => node.addEventListener('click', () => window.wayglyphWorkspace(node.dataset.workspace)));
  studio.querySelectorAll('[data-tab]').forEach(node => node.addEventListener('click', () => selectTab(node.dataset.tab)));
  studio.querySelector('.studio-tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    const tabs = [...studio.querySelectorAll('[data-tab]')], index = tabs.indexOf(document.activeElement); if (index < 0) return;
    event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1) + tabs.length) % tabs.length;
    selectTab(tabs[next].dataset.tab); tabs[next].focus();
  });
  studio.querySelectorAll('[data-go]').forEach(node => node.addEventListener('click', () => { if (node.getAttribute('aria-disabled') === 'true') return; selectTab(node.dataset.go, true); }));
  studio.addEventListener('click', event => {
    const node = event.target.closest('[aria-disabled="true"]');
    if (node) {
      event.preventDefault(); event.stopImmediatePropagation();
      if (node.hasAttribute('data-analysis-action') && editorDirty()) setStatus('Save your text before running analysis.', 'error');
      else showTooltip(node);
    }
  }, true);

  $('text').addEventListener('input', updateControls); $('name').addEventListener('input', updateControls);
  $('add').addEventListener('click', () => { if (state.busy) return; try { saveEditor(); setStatus('Dataset saved.'); } catch (error) { setStatus(error.message, 'error'); } });
  $('sample').addEventListener('click', () => { if (state.busy) return; try { saveEditor(); addDocuments([{name: 'search-demo.txt', text: 'Intelligent text search finds text patterns. Search text with KMP.\n'.repeat(12), priority: 5}, {name: 'repeated.txt', text: 'A'.repeat(1500) + 'B'.repeat(600) + '\n', priority: 3}, {name: 'notes.txt', text: 'Wayglyph combines pattern matching, compression, and storage optimization. 🌏', priority: 2}]); setStatus('Three sample datasets loaded.'); } catch (error) { setStatus(error.message, 'error'); } });
  $('clearDraft').addEventListener('click', () => { if (state.busy) return; try { saveEditor(); loadEditor(null); renderDataset(); decorate(); $('text').focus(); setStatus('Ready for a new dataset.'); } catch (error) { setStatus(error.message, 'error'); } });
  $('clear').addEventListener('click', () => { if (state.busy) return; state.documents = []; loadEditor(null); datasetChanged(); setStatus('Datasets cleared.'); });
  // Read uploaded UTF-8 files into browser state; API calls send them when an algorithm runs.
  $('files').addEventListener('change', () => run('files', 'Reading your text files…', async () => {
    try { const files = [...$('files').files]; if (!files.length) return 'No files selected.'; if (files.length > 30 || files.reduce((sum, file) => sum + file.size, 0) > 2000000) throw new Error('Choose up to 30 files with 2 MB combined.');
      saveEditor();
      const incoming = []; for (const file of files) { let text; try { text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()); } catch { throw new Error(`${file.name} is not readable UTF-8 text. Save it as UTF-8 and try again.`); } incoming.push({name: file.name, text, priority: 1}); }
      addDocuments(incoming); return `${incoming.length} dataset(s) loaded.`;
    } finally { $('files').value = ''; }
  }));
  // Sync both pattern inputs and discard search results for the old pattern.
  function patternChanged(source, other) { other.value = source.value; clearSearch(); clearParallel(); renderPerformance(); updateControls(); }
  $('pattern').addEventListener('input', () => patternChanged($('pattern'), $('parallelPattern'))); $('parallelPattern').addEventListener('input', () => patternChanged($('parallelPattern'), $('pattern')));
  $('capacity').addEventListener('input', () => { clearOptimization(); renderPerformance(); updateControls(); });
  $('search').addEventListener('click', () => run('search', 'Finding matches with KMP…', async () => `${await searchAlgorithm('kmp')} KMP match(es) found. See positions and highlights below.`));
  $('brute').addEventListener('click', () => run('brute', 'Checking positions in your browser…', async () => `${await searchAlgorithm('brute')} Brute Force match(es) found.`));
  $('compareSearch').addEventListener('click', () => run('compareSearch', 'Comparing KMP and Brute Force…', async () => { await searchAlgorithm('kmp'); await searchAlgorithm('brute'); return 'Both searches finished. Runtime scopes are labeled in the comparison.'; }));
  for (const method of ['auto', 'huffman', 'rle']) $(method).addEventListener('click', () => run(method, method === 'auto' ? 'Choosing the smallest download…' : `Compressing with ${methodName(method)}…`, async () => { await compress(method); return method === 'auto' ? 'Smallest downloads ready. Originals are kept whenever compression would not save space.' : 'Encoding complete. Use Get smallest file if the encoded file grew.'; }));
  $('compareCompression').addEventListener('click', () => run('compareCompression', 'Comparing both compression methods…', async () => { const results = await Promise.allSettled([compress('huffman'), compress('rle')]); const failure = results.find(result => result.status === 'rejected'); if (failure) throw failure.reason; return 'Comparison ready. Look at size, savings, and runtime for each file.'; }));
  $('quicksort').addEventListener('click', () => run('quicksort', 'Sorting files by size…', async () => { const result = await api('sort'); record('quicksort', result.elapsed_ms); renderSort(result); return 'Quick Sort finished. Files are ordered by original size.'; }));
  $('runAll').addEventListener('click', () => run('runAll', 'Running Huffman, RLE, Quick Sort and knapsack in four processes…', async () => {
    $('batchSummary').replaceChildren();
    const result = await api('run-all', {capacity: Number($('capacity').value)});
    state.compression = {huffman: result.huffman, rle: result.rle, auto: {results: result.optimization.items}};
    state.optimization = result.optimization;
    for (const method of ['huffman', 'rle', 'auto']) record(method, state.compression[method].results.reduce((sum, item) => sum + item.elapsed_ms, 0));
    record('knapsack', result.optimization.elapsed_ms); record('quicksort', result.quicksort.elapsed_ms);
    renderCompression(); renderOptimization(result.optimization); renderSort(result.quicksort);
    $('batchSummary').append(el('p', `Four algorithms completed · ${result.workers} worker processes · ${ms(result.elapsed_ms)} wall time, including process startup. Compression results are in Compression; knapsack and Quick Sort results are in Optimization.`, 'field-hint'));
    selectTab('compression');
    return 'All four algorithms finished. Smallest downloads, knapsack selection and sorted files are ready.';
  }));
  // Send compressed bytes to /api/text/decompress and offer the restored text as a download.
  $('packed').addEventListener('change', () => run('packed', 'Restoring your original text…', async () => {
    try { const file = $('packed').files[0]; if (!file) return; if (file.size > 4000008) throw new Error('This compressed file exceeds the supported size. Choose a smaller Wayglyph file.');
      const packed = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let i = 0; i < packed.length; i += 8192) binary += String.fromCharCode(...packed.subarray(i, i + 8192));
      const start = performance.now(), result = await api('decompress', {payload: btoa(binary)}); record('restore', performance.now() - start, 'Full request round trip, not server-only computation');
      clearContainer('restored'); $('restored').append(metric('Restored text', bytes(result.original_bytes), 'The recovered UTF-8 text size.'));
      const chars = Array.from(result.text); $('restored').append(el('div', chars.slice(0, 2000).join(''), 'text-preview'), el('p', 'Preview: first 2,000 characters.', 'field-hint'), download(`${file.name}.restored.txt`, new Blob([result.text], {type: 'text/plain;charset=utf-8'}))); return 'File restored. Download the complete original text below.';
    } finally { $('packed').value = ''; }
  }));
  $('optimize').addEventListener('click', () => run('optimize', 'Finding the highest-priority set that fits…', async () => { const result = await api('optimize', {capacity: Number($('capacity').value)}); state.optimization = result; record('knapsack', result.elapsed_ms); renderOptimization(result); return 'Best selection ready. Increase the budget or adjust priorities to explore alternatives.'; }));
  // POST documents to parallel-search, optionally run sequential search, and show results.
  async function parallel(compare) {
    let sequential = null; if (compare) { sequential = await api('search', {pattern: $('pattern').value}); state.search.kmp = sequential; record('kmp', sequential.results.reduce((sum, r) => sum + r.elapsed_ms, 0)); renderSearch('kmp'); }
    const result = await api('parallel-search', {pattern: $('pattern').value}); state.parallel = result; record('parallel', result.elapsed_ms); renderParallel(result, sequential); return `Search finished using ${result.workers} worker process(es).`;
  }
  $('parallel').addEventListener('click', () => run('parallel', 'Starting worker processes and searching files…', () => parallel(false)));
  $('compareParallel').addEventListener('click', () => run('compareParallel', 'Comparing sequential and parallel execution…', () => parallel(true)));
  for (const [id, action] of [['clearSearch', clearSearch], ['clearParallel', clearParallel], ['clearOptimization', clearOptimization], ['clearCompression', () => { state.compression = {}; delete state.timings.huffman; delete state.timings.rle; delete state.timings.auto; clearContainer('compressionResults'); }], ['clearTimings', () => { state.timings = {}; }]]) $(id).addEventListener('click', () => { if (state.busy) return; action(); renderPerformance(); updateControls(); setStatus('Results cleared. Your documents are kept.'); });

  // Context guides for the retained map and cipher controls.
  const mapGuides = {startSelect: 'Choose where the shortest-path search begins.', goalSelect: 'Choose the destination for the shortest-path search.', cipherKey: 'Shift letters and digits by this key. Use the same key to decrypt.', executeBtn: 'Finds a shortest path with A* and demonstrates Caesar encryption.', resetEmptyBtn: 'Clears all map nodes and edges after confirmation.', resetSampleBtn: 'Replaces the current map with the built-in sample graph.', saveGraphBtn: 'Downloads your current graph as a text file.', loadGraphInput: 'Loads a saved graph text file and replaces the current map.', msgPlainInput: 'Enter a message for the educational Caesar cipher.', msgCipherKey: 'Choose the shift for message encryption. Use this same key to decrypt.', decryptCipherKey: 'Use the original encryption key to restore the message.', msgEncryptBtn: 'Shifts ASCII letters and digits using your selected key.', decryptBtn: 'Reverses Caesar shifts to recover the original message or path.', msgDownloadBtn: 'Downloads this encrypted message with its cipher key.', msgCopyBtn: 'Copies the encrypted message to the clipboard.', decryptCopyBtn: 'Copies the restored text to your clipboard.', copyBtn: 'Copies the displayed path export, including key and plaintext.', menuToggleBtn: 'Shows or hides the map editing controls.', closeRailBtn: 'Closes the map editing menu.', cipherLabToggleBtn: 'Shows or hides the path cipher, message encryptor, and decryptor.', decryptInput: 'Paste an encrypted message or a Wayglyph path export.', decryptFileInput: 'Load an exported text file for decryption.', exportBtn: 'Downloads the path result currently displayed in this browser tab.', modalCancelBtn: 'Cancels this action and keeps the current map.', modalConfirmBtn: 'Applies the action described in this confirmation dialog.'};
  const resultGuides = {'g(n)': 'Cost of the best known route from the start to this node.', 'h(n)': 'Estimated remaining cost to the goal. A* scales this estimate to fit the graph weights.', 'f(n)': 'A* priority: distance traveled plus estimated remaining cost, g(n) + h(n).', 'weight': 'Cost of this graph edge.', 'step': 'The order in which this search event occurred.', 'edge': 'The node or connection evaluated in this step.', 'evaluation status': 'Describes whether a node was reached, a route improved, or the goal was found.', 'plain': 'The original unencrypted edge weight.', 'encrypted': 'The weight after Caesar digit shifting.'};
  for (const node of document.querySelectorAll('#mapWorkspace button,#mapWorkspace input,#mapWorkspace textarea,#mapWorkspace select,#mapWorkspace label,#mapWorkspace th,[data-text-lab-toggle],#modalCancelBtn,#modalConfirmBtn')) {
    if (node.dataset.help) continue;
    const name = node.getAttribute('aria-label') || node.textContent.trim().replace(/\s+/g, ' ') || node.id;
    const forControl = node.getAttribute('for');
    node.dataset.help = mapGuides[node.id] || mapGuides[forControl] || resultGuides[name.toLowerCase()] || (node.matches('label,th') ? `The ${name.toLowerCase()} setting or result for this operation.` : `Use ${name.toLowerCase()} in the map and cipher lab.`);
  }
  document.querySelectorAll('button:not([type])').forEach(node => { node.type = 'button'; });
  renderDataset(); renderPerformance(); updateControls(); decorate();
  window.wayglyphWorkspace('map');
})();
