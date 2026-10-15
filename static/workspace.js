/* Frontend-only studio. Existing Flask endpoints and response fields are unchanged. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const studio = $('textLab');
  const workerURL = new URL('search-worker.js', document.currentScript.src);
  const state = {documents: [], busy: false, tab: 'input', search: {}, compression: {}, parallel: null, optimization: null, timings: {}, urls: new Map()};
  const algorithmInfo = {
    kmp: ['KMP', 'O(n + m)', 'O(m + z)', 'Server · compute'],
    brute: ['Brute Force', 'O(n × m)', 'O(n + m + z)', 'Browser worker · compute'],
    huffman: ['Huffman compression', 'O(n + k log k + B)', 'O(kL + B)', 'Server · compute'],
    rle: ['RLE compression', 'O(n)', 'O(c)', 'Server · compute'],
    knapsack: ['0/1 knapsack', 'O(F × C)', 'O(F × C)', 'Server · selection only'],
    parallel: ['Parallel KMP', 'Ideal O((N + Fm) / p) + overhead', 'O(N + pm + Z) + process overhead', 'Server · wall time'],
    restore: ['Decompression', 'Huffman: O(k log k + B + n); RLE: O(c + n)', 'Huffman: O(k + n); RLE: O(n)', 'Browser · request round trip']
  };
  const fmt = n => new Intl.NumberFormat(undefined, {maximumFractionDigits: 3}).format(n);
  const bytes = n => `${fmt(n)} B`;
  const ms = n => `${fmt(n)} ms`;
  const totalBytes = () => state.documents.reduce((sum, doc) => sum + new TextEncoder().encode(doc.text).length, 0);
  function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
  function help(node, message) { node.dataset.help = message; return node; }
  function button(text, message, action, className = 'studio-button secondary') { const node = help(el('button', text, className), message); node.type = 'button'; node.addEventListener('click', action); return node; }
  function setStatus(message, type = '') { $('statusText').textContent = message; $('status').className = `studio-status ${type}`; }
  function metric(label, value, message, note = '', style = '') {
    const node = el('dl', undefined, `metric ${style}`);
    node.append(help(el('dt', label), message), el('dd', value)); if (note) node.append(el('small', note)); return node;
  }
  function empty(title, detail, goToInput = false) {
    const node = el('div', undefined, 'empty-state'); node.append(el('b', title), el('span', detail));
    if (goToInput) node.append(button('Load text first', 'Go to Text Input to add files or load a sample.', () => selectTab('input', true)));
    return node;
  }
  function card(title, guide) { const node = el('div', undefined, 'studio-card'); node.append(help(el('h3', title), guide)); return node; }
  function clearContainer(id) {
    const node = $(id); for (const a of node.querySelectorAll('a[data-download]')) { URL.revokeObjectURL(a.href); state.urls.delete(a.href); }
    node.replaceChildren();
  }
  function download(name, blob) {
    const a = help(el('a', 'Download', 'studio-download'), `Saves ${name} to your device.`);
    a.href = URL.createObjectURL(blob); a.download = name; a.dataset.download = 'true'; state.urls.set(a.href, true); return a;
  }
  function packedBlob(payload) { return new Blob([Uint8Array.from(atob(payload), c => c.charCodeAt(0))], {type: 'application/octet-stream'}); }
  function table(parent, headers, rows) {
    const t = el('table'), head = el('thead'), tr = el('tr'), body = el('tbody');
    for (const [label, guide] of headers) tr.append(help(el('th', label), guide)); head.append(tr); t.append(head);
    for (const row of rows) { const r = el('tr'); for (const value of row) { const td = el('td'); td.append(value instanceof Node ? value : document.createTextNode(String(value))); r.append(td); } body.append(r); }
    t.append(body);
    if (parent.classList.contains('table-scroll')) parent.append(t);
    else { const scroll = el('div', undefined, 'table-scroll'); scroll.append(t); parent.append(scroll); }
  }
  function record(key, elapsed, note = '') { state.timings[key] = {elapsed, note, files: state.documents.length, bytes: totalBytes()}; renderPerformance(); }
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
  function selectTab(name, focus = false) {
    if (!$(`panel-${name}`)) return;
    state.tab = name;
    for (const tab of document.querySelectorAll('[data-tab]')) { const active = tab.dataset.tab === name; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; $(`panel-${tab.dataset.tab}`).hidden = !active; }
    hideTooltip(); updateFlow(); if (focus) $(`panel-${name}`).focus({preventScroll: false});
  }
  function updateFlow() {
    const loaded = state.documents.length > 0, measured = Object.keys(state.timings).length > 0;
    const step = !loaded ? 0 : state.tab === 'performance' && measured ? 2 : 1;
    ['flowLoad', 'flowRun', 'flowCompare'].forEach((id, i) => { $(id).className = i < step ? 'done' : i === step ? 'current' : ''; if (i === step) $(id).setAttribute('aria-current', 'step'); else $(id).removeAttribute('aria-current'); });
  }
  function updateControls() {
    const docs = state.documents.length > 0, pattern = $('pattern').value.length > 0;
    const priorityValid = state.documents.every(doc => Number.isInteger(doc.priority) && doc.priority >= 1 && doc.priority <= 1000);
    const budget = Number($('capacity').value), budgetValid = $('capacity').value !== '' && Number.isInteger(budget) && budget >= 0 && budget <= 100000;
    const disabled = {
      add: !$('text').value.length || !$('name').value.trim().length,
      sample: state.documents.length > 27, clear: !docs, clearDraft: !$('text').value.length,
      search: !docs || !pattern, brute: !docs || !pattern, compareSearch: !docs || !pattern,
      huffman: !docs, rle: !docs, compareCompression: !docs,
      optimize: !docs || !budgetValid || !priorityValid,
      parallel: state.documents.length < 2 || !pattern, compareParallel: state.documents.length < 2 || !pattern,
      clearSearch: !Object.keys(state.search).length, clearCompression: !Object.keys(state.compression).length,
      clearOptimization: !state.optimization, clearParallel: !state.parallel,
      clearTimings: !Object.keys(state.timings).length
    };
    for (const [id, invalid] of Object.entries(disabled)) $(id).setAttribute('aria-disabled', String(state.busy || invalid));
    document.querySelectorAll('[data-needs-documents]').forEach(node => node.setAttribute('aria-disabled', String(state.busy || !docs)));
    studio.querySelectorAll('input,textarea,select').forEach(node => { node.disabled = state.busy; });
    studio.querySelectorAll('[data-mutates-dataset]').forEach(node => node.setAttribute('aria-disabled', String(state.busy)));
    updateFlow();
  }
  function clearSearch() { state.search = {}; delete state.timings.kmp; delete state.timings.brute; clearContainer('searchResults'); clearContainer('searchComparison'); }
  function clearParallel() { state.parallel = null; delete state.timings.parallel; clearContainer('parallelResults'); }
  function clearOptimization() { state.optimization = null; delete state.timings.knapsack; clearContainer('optimizationResults'); }
  function datasetChanged() {
    clearSearch(); clearParallel(); clearOptimization(); state.compression = {}; state.timings = {};
    clearContainer('compressionResults'); clearContainer('restored'); renderDataset(); renderPerformance(); updateControls(); decorate();
  }
  function priorityInput(doc, index, label) {
    const input = help(el('input', undefined, 'file-priority'), 'A whole number from 1 to 1,000. Higher-priority files contribute more value to storage optimization.');
    input.type = 'number'; input.min = '1'; input.max = '1000'; input.step = '1'; input.value = doc.priority; input.setAttribute('aria-label', `${label} priority for ${doc.name}`); input.dataset.priorityIndex = index;
    input.addEventListener('input', () => {
      doc.priority = input.value === '' ? NaN : Number(input.value);
      studio.querySelectorAll(`[data-priority-index="${index}"]`).forEach(other => { if (other !== input) other.value = input.value; });
      clearOptimization(); renderPerformance(); updateControls();
    }); return input;
  }
  function renderDataset() {
    const count = state.documents.length; $('docCount').textContent = count; $('datasetBadge').firstChild.textContent = count ? `${count} document${count === 1 ? '' : 's'} · ${bytes(totalBytes())}` : 'No documents loaded';
    $('inputHint').textContent = count ? 'Your dataset is ready. Pick an algorithm to continue.' : 'Add a document to unlock the algorithms.';
    $('dataset').replaceChildren(); $('priorities').replaceChildren();
    if (!count) { $('dataset').append(empty('A fresh page, ready for your words.', 'Type a document, upload a file, or try the sample dataset.')); $('priorities').append(el('p', 'Add documents in Text Input to assign their priorities.')); }
    else {
      table($('dataset'), [['Document', 'The name you assigned or uploaded.'], ['Original size', 'UTF-8 byte size before compression.'], ['Priority', 'Importance for optimization: higher numbers contribute more value.'], ['Manage', 'Remove individual documents from the dataset.']], state.documents.map((doc, i) => {
        const remove = button('Remove', `Removes ${doc.name} and clears results for this dataset.`, () => { if (state.busy) return; state.documents.splice(i, 1); datasetChanged(); setStatus('Document removed.'); }, 'studio-button ghost'); remove.dataset.mutatesDataset = 'true';
        const row = el('div', undefined, 'priority-row'); row.append(help(el('span', doc.name), 'The document whose importance you are setting.'), priorityInput(doc, i, 'Optimizer')); $('priorities').append(row);
        return [doc.name, bytes(new TextEncoder().encode(doc.text).length), priorityInput(doc, i, 'Dataset'), remove];
      }));
    }
    studio.querySelectorAll('[data-empty-gate]').forEach(node => { node.replaceChildren(); if (!count) node.append(empty('Your text comes first.', 'Load a sample or add a document to use this tool.', true)); });
  }
  function addDocuments(incoming) {
    const combined = [...state.documents, ...incoming];
    if (combined.length > 30) throw new Error('You can load up to 30 documents. Remove one before adding more.');
    if (combined.some(doc => !doc.name.trim() || doc.name.length > 255)) throw new Error('Use document names with 1 to 255 characters.');
    if (combined.reduce((sum, doc) => sum + new TextEncoder().encode(doc.text).length, 0) > 2000000) throw new Error('Your dataset exceeds 2 MB. Try fewer files or shorter text.');
    state.documents = combined; datasetChanged();
  }
  async function api(action, extra = {}) {
    let response;
    try { response = await fetch(`/api/text/${action}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(action === 'decompress' ? extra : {documents: state.documents, ...extra})}); }
    catch { throw new Error('We could not reach the server. Check that Wayglyph is running, then try again.'); }
    let result; try { result = await response.json(); } catch { throw new Error('The server could not read this request. Try a smaller file or dataset.'); }
    if (!response.ok) throw new Error(result.error || 'That operation could not finish. Please try again.'); return result;
  }
  async function run(id, message, action) {
    const node = $(id); if (state.busy) return;
    if (node.getAttribute('aria-disabled') === 'true') {
      setStatus(!state.documents.length ? 'Load a sample or add a document in Text Input first.' : id.includes('arallel') || id === 'parallel' ? 'Parallel search needs at least two files and a search phrase.' : id === 'optimize' ? 'Use a whole-number budget from 0 to 100,000 and priorities from 1 to 1,000.' : 'Fill in the required input before continuing.', 'error'); return;
    }
    state.busy = true; studio.setAttribute('aria-busy', 'true'); node.classList.add('is-loading'); updateControls(); setStatus(message, 'busy');
    try { const success = await action(); setStatus(success || 'Done. Your results are ready below.'); }
    catch (error) { setStatus(error.message || 'Something went wrong. Please try again.', 'error'); }
    finally { state.busy = false; studio.setAttribute('aria-busy', 'false'); node.classList.remove('is-loading'); updateControls(); decorate(); }
  }
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
  async function bruteForce() {
    return new Promise((resolve, reject) => {
      let worker;
      try { worker = new Worker(workerURL); } catch { reject(new Error('Browser workers are unavailable. KMP search still works.')); return; }
      const timeout = setTimeout(() => { worker.terminate(); reject(new Error('Brute Force took too long. Try less text or a shorter phrase.')); }, 15000);
      const finish = () => { clearTimeout(timeout); worker.terminate(); };
      worker.onmessage = ({data}) => { finish(); data.error ? reject(new Error(data.error)) : resolve(data); };
      worker.onerror = () => { finish(); reject(new Error('The browser worker could not start. Try KMP search instead.')); };
      worker.postMessage({documents: state.documents.map(({name, text}) => ({name, text})), pattern: $('pattern').value});
    });
  }
  async function searchAlgorithm(key) {
    const result = key === 'kmp' ? await api('search', {pattern: $('pattern').value}) : await bruteForce();
    state.search[key] = result; record(key, result.results.reduce((sum, r) => sum + r.elapsed_ms, 0), 'Total compute time across documents');
    renderSearch(key); return result.results.reduce((sum, r) => sum + r.count, 0);
  }
  function renderSearch(latest) {
    clearContainer('searchComparison'); clearContainer('searchResults');
    const keys = ['kmp', 'brute'].filter(k => state.search[k]);
    if (keys.length) chart($('searchComparison'), keys.map(k => [algorithmInfo[k][0], state.search[k].results.reduce((sum, r) => sum + r.elapsed_ms, 0)]), 'Search runtime', 'KMP: server compute. Brute Force: browser worker compute. Different environments; these timings do not isolate algorithm speed.');
    renderMatches($('searchResults'), state.search[latest], algorithmInfo[latest][0], $('pattern').value); decorate();
  }
  async function compress(method) {
    const result = await api('compress', {method}); state.compression[method] = result;
    record(method, result.results.reduce((sum, r) => sum + r.elapsed_ms, 0), 'Total compression time across documents'); renderCompression();
  }
  function renderCompression() {
    clearContainer('compressionResults'); const out = $('compressionResults');
    const methods = ['huffman', 'rle'].filter(method => state.compression[method]);
    if (methods.length) chart(out, methods.map(method => [method === 'huffman' ? 'Huffman' : 'RLE', state.compression[method].results.reduce((sum, r) => sum + r.elapsed_ms, 0)]), 'Compression runtime', 'Both methods use the same server and dataset. Timings include headers and binary encoding.');
    for (let i = 0; i < state.documents.length; i++) {
      const c = card(state.documents[i].name, 'Compression results for this document. Sizes include the decoding header and checksum.');
      const cards = el('div', undefined, 'comparison-grid');
      for (const method of methods) {
        const r = state.compression[method].results[i], choice = el('div'); choice.append(help(el('h3', method === 'huffman' ? 'Huffman' : 'RLE'), method === 'huffman' ? 'Shorter codes represent more frequent bytes.' : 'Repeated bytes become count-value pairs.'));
        const metrics = el('div', undefined, 'metrics-grid'); metrics.append(
          metric('Original size', bytes(r.original_bytes), 'Original UTF-8 text size in bytes.'),
          metric('Compressed size', bytes(r.compressed_bytes), 'Complete downloadable file size, including header and checksum.'),
          metric('Compression ratio', r.ratio === null ? 'N/A' : fmt(r.ratio), 'Compressed size divided by original size. Lower means better compression.', r.ratio === null ? 'Empty text has no ratio.' : ''),
          metric('Space saved', r.savings_percent === null ? 'N/A' : `${fmt(r.savings_percent)}%`, 'Percent reduction from the original size. A negative value means the compressed file grew.', r.savings_percent < 0 ? 'This file grew.' : '', r.savings_percent > 0 ? 'good' : r.savings_percent < 0 ? 'bad' : '')
        ); choice.append(metrics, help(el('p', `Server runtime: ${ms(r.elapsed_ms)}`), 'Measured compression computation time for this document.'), download(`${r.name}.${method}.wgc`, packedBlob(r.payload))); cards.append(choice);
      }
      c.append(cards); out.append(c);
    } decorate();
  }
  function renderOptimization(result) {
    clearContainer('optimizationResults'); const out = $('optimizationResults'), c = card('Your best selection', 'The exact maximum-total-priority subset that fits the specified byte budget.');
    const metrics = el('div', undefined, 'metrics-grid'); metrics.append(
      metric('Selected files', `${result.selected_indices.length} / ${result.items.length}`, 'Number of files chosen from your dataset.'),
      metric('Space used', bytes(result.used_bytes), 'Sum of compressed sizes of the selected files.', `Budget: ${bytes(result.capacity_bytes)}`),
      metric('Total priority', fmt(result.total_priority), 'Sum of priorities for selected files. The optimizer maximizes this value.', '', 'good'),
      metric('Selection time', ms(result.elapsed_ms), 'Knapsack computation time, excluding compression preparation.')
    ); c.append(metrics);
    if (!result.selected_indices.length) c.append(el('p', 'No file fits this budget. Increase the budget or try a smaller document.'));
    table(c, [['File', 'Your original document name.'], ['Method', 'The smaller of Huffman and RLE for this file.'], ['Size', 'Complete compressed size in bytes.'], ['Priority', 'Value contributed if selected.'], ['Selection', 'Selected files fit together within the budget.'], ['Download', 'Download selected compressed files.']], result.items.map((item, i) => {
      const selected = result.selected_indices.includes(i); return [item.name, item.method === 'huffman' ? 'Huffman' : 'RLE', bytes(item.compressed_bytes), item.priority, el('span', selected ? '✓ Selected' : 'Excluded', selected ? 'selection-yes' : 'selection-no'), selected ? download(`${item.name}.${item.method}.wgc`, packedBlob(item.payload)) : '—'];
    })); out.append(c); decorate();
  }
  function renderParallel(result, sequential) {
    clearContainer('parallelResults'); const out = $('parallelResults');
    const summary = el('div', undefined, 'metrics-grid'); summary.append(metric('Worker processes', String(result.workers), 'Independent Python processes used for this search; at most four.'), metric('Parallel wall time', ms(result.elapsed_ms), 'Includes worker startup, data transfer, and searching.')); out.append(summary);
    if (sequential) chart(out, [['Sequential KMP', sequential.results.reduce((sum, r) => sum + r.elapsed_ms, 0)], ['Parallel KMP', result.elapsed_ms]], 'Execution comparison', 'Sequential: summed server search compute time. Parallel: total wall time including startup and transfer. These measure different scopes; small datasets often favor sequential execution.');
    renderMatches(out, result, 'Parallel KMP', $('pattern').value); decorate();
  }
  function renderPerformance() {
    $('performanceSummary').replaceChildren(metric('Documents', String(state.documents.length), 'Number of documents in the current dataset.'), metric('Dataset size', bytes(totalBytes()), 'Combined UTF-8 size of loaded documents.'), metric('Algorithms measured', String(Object.keys(state.timings).length), 'Algorithms with a recorded runtime for this dataset. Each row shows its latest run.'));
    $('runtimeChart').replaceChildren();
    const entries = Object.entries(state.timings);
    if (!entries.length) $('runtimeChart').append(empty('Your comparisons will appear here.', 'Run an algorithm, then come back to see its time and complexity.'));
    else {
      $('runtimeChart').append(el('h3', 'Latest measured runtimes'));
      for (const [keys, title] of [[['kmp', 'brute'], 'Pattern matching'], [['huffman', 'rle'], 'Compression'], [['knapsack'], 'Storage selection'], [['parallel'], 'Parallel execution'], [['restore'], 'Restoration round trip']]) {
        const present = keys.filter(k => state.timings[k]); if (present.length) chart($('runtimeChart'), present.map(k => [algorithmInfo[k][0], state.timings[k].elapsed]), title, present.includes('brute') ? 'Server KMP and browser Brute Force run in different environments.' : 'Latest run for each algorithm. Lower measured milliseconds means less elapsed time for that run.');
      }
    }
    $('performanceTable').replaceChildren();
    table($('performanceTable'), [['Algorithm', 'The implemented method used for this operation.'], ['Time · Big-O', 'Shows how time grows as the input gets larger. Constants and actual hardware are not included.'], ['Space · Big-O', 'Shows how memory grows, including output and implementation buffers.'], ['Measured time', 'Latest elapsed time for this dataset. Not run means no measurement is recorded.'], ['Timing scope', 'Where and what the timer measures; compare like-for-like scopes.']], Object.entries(algorithmInfo).map(([key, info]) => [info[0], info[1], info[2], state.timings[key] ? ms(state.timings[key].elapsed) : 'Not run', info[3]]));
    decorate(); updateFlow();
  }

  // One shared tooltip portal: no clipping inside tables or containers.
  const tooltip = el('div', undefined, 'guide-tooltip'); tooltip.id = 'wayglyphGuide'; tooltip.setAttribute('role', 'tooltip'); tooltip.hidden = true; document.body.append(tooltip);
  let tipTarget = null, tipTimer = null, tipHovered = false;
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
  function hideTooltip() {
    clearTimeout(tipTimer); if (tipTarget) { const ids = (tipTarget.getAttribute('aria-describedby') || '').split(' ').filter(id => id && id !== tooltip.id); if (ids.length) tipTarget.setAttribute('aria-describedby', ids.join(' ')); else tipTarget.removeAttribute('aria-describedby'); }
    tipTarget = null; tooltip.hidden = true;
  }
  function showTooltip(target) {
    if (!target || !target.dataset.help) return; hideTooltip(); tipTarget = target; tooltip.textContent = target.dataset.help; tooltip.hidden = false;
    const ids = target.getAttribute('aria-describedby'); target.setAttribute('aria-describedby', `${ids ? ids + ' ' : ''}${tooltip.id}`); positionTooltip();
  }
  function scheduleHide() { clearTimeout(tipTimer); tipTimer = setTimeout(() => { if (!tipHovered && document.activeElement !== tipTarget) hideTooltip(); }, 160); }
  function decorate(root = document) {
    for (const node of root.querySelectorAll('[data-help]')) {
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
  studio.addEventListener('click', event => { const node = event.target.closest('[aria-disabled="true"]'); if (node) { event.preventDefault(); event.stopImmediatePropagation(); showTooltip(node); } }, true);

  $('text').addEventListener('input', updateControls); $('name').addEventListener('input', updateControls);
  $('add').addEventListener('click', () => { if (state.busy) return; try { addDocuments([{name: $('name').value.trim() || 'Untitled.txt', text: $('text').value, priority: 1}]); $('text').value = ''; updateControls(); setStatus('Document added. Next, open Pattern Search or Compression.'); } catch (error) { setStatus(error.message, 'error'); } });
  $('sample').addEventListener('click', () => { if (state.busy) return; try { addDocuments([{name: 'search-demo.txt', text: 'Intelligent text search finds text patterns. Search text with KMP.\n'.repeat(12), priority: 5}, {name: 'repeated.txt', text: 'A'.repeat(1500) + 'B'.repeat(600) + '\n', priority: 3}, {name: 'notes.txt', text: 'Wayglyph combines pattern matching, compression, and storage optimization. 🌏', priority: 2}]); setStatus('Three sample documents loaded. Next: search for “text” or compare compression.'); } catch (error) { setStatus(error.message, 'error'); } });
  $('clearDraft').addEventListener('click', () => { if (state.busy) return; $('text').value = ''; updateControls(); setStatus('Editor cleared. Your loaded documents are kept.'); });
  $('clear').addEventListener('click', () => { if (state.busy) return; state.documents = []; datasetChanged(); setStatus('Dataset cleared. Add text or try a sample to begin again.'); });
  $('files').addEventListener('change', () => run('files', 'Reading your text files…', async () => {
    try { const files = [...$('files').files]; if (!files.length) return 'No files selected. Your dataset is unchanged.'; if (files.length > 30 || files.reduce((sum, file) => sum + file.size, 0) > 2000000) throw new Error('Choose up to 30 files with 2 MB combined.');
      const incoming = []; for (const file of files) { let text; try { text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()); } catch { throw new Error(`${file.name} is not readable UTF-8 text. Save it as UTF-8 and try again.`); } incoming.push({name: file.name, text, priority: 1}); }
      addDocuments(incoming); return `${incoming.length} file(s) added. Your dataset is ready.`;
    } finally { $('files').value = ''; }
  }));
  function patternChanged(source, other) { other.value = source.value; clearSearch(); clearParallel(); renderPerformance(); updateControls(); }
  $('pattern').addEventListener('input', () => patternChanged($('pattern'), $('parallelPattern'))); $('parallelPattern').addEventListener('input', () => patternChanged($('parallelPattern'), $('pattern')));
  $('capacity').addEventListener('input', () => { clearOptimization(); renderPerformance(); updateControls(); });
  $('search').addEventListener('click', () => run('search', 'Finding matches with KMP…', async () => `${await searchAlgorithm('kmp')} KMP match(es) found. See positions and highlights below.`));
  $('brute').addEventListener('click', () => run('brute', 'Checking positions in your browser…', async () => `${await searchAlgorithm('brute')} Brute Force match(es) found.`));
  $('compareSearch').addEventListener('click', () => run('compareSearch', 'Comparing KMP and Brute Force…', async () => { await searchAlgorithm('kmp'); await searchAlgorithm('brute'); return 'Both searches finished. Runtime scopes are labeled in the comparison.'; }));
  for (const method of ['huffman', 'rle']) $(method).addEventListener('click', () => run(method, `Compressing with ${method === 'huffman' ? 'Huffman' : 'RLE'}…`, () => compress(method)));
  $('compareCompression').addEventListener('click', () => run('compareCompression', 'Comparing both compression methods…', async () => { await compress('huffman'); await compress('rle'); return 'Comparison ready. Look at size, savings, and runtime for each file.'; }));
  $('packed').addEventListener('change', () => run('packed', 'Restoring your original text…', async () => {
    try { const file = $('packed').files[0]; if (!file) return; if (file.size > 4000008) throw new Error('This compressed file exceeds the supported size. Choose a smaller Wayglyph file.');
      const packed = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let i = 0; i < packed.length; i += 8192) binary += String.fromCharCode(...packed.subarray(i, i + 8192));
      const start = performance.now(), result = await api('decompress', {payload: btoa(binary)}); record('restore', performance.now() - start, 'Full request round trip, not server-only computation');
      clearContainer('restored'); $('restored').append(metric('Restored text', bytes(result.original_bytes), 'The recovered UTF-8 text size.'));
      const chars = Array.from(result.text); $('restored').append(el('div', chars.slice(0, 2000).join(''), 'text-preview'), el('p', 'Preview shows up to 2,000 characters. The download contains the full restored text.', 'field-hint'), download(`${file.name}.restored.txt`, new Blob([result.text], {type: 'text/plain;charset=utf-8'}))); return 'File restored. Download the complete original text below.';
    } finally { $('packed').value = ''; }
  }));
  $('optimize').addEventListener('click', () => run('optimize', 'Finding the highest-priority set that fits…', async () => { const result = await api('optimize', {capacity: Number($('capacity').value)}); state.optimization = result; record('knapsack', result.elapsed_ms); renderOptimization(result); return 'Best selection ready. Increase the budget or adjust priorities to explore alternatives.'; }));
  async function parallel(compare) {
    let sequential = null; if (compare) { sequential = await api('search', {pattern: $('pattern').value}); state.search.kmp = sequential; record('kmp', sequential.results.reduce((sum, r) => sum + r.elapsed_ms, 0)); renderSearch('kmp'); }
    const result = await api('parallel-search', {pattern: $('pattern').value}); state.parallel = result; record('parallel', result.elapsed_ms); renderParallel(result, sequential); return `Search finished using ${result.workers} worker process(es).`;
  }
  $('parallel').addEventListener('click', () => run('parallel', 'Starting worker processes and searching files…', () => parallel(false)));
  $('compareParallel').addEventListener('click', () => run('compareParallel', 'Comparing sequential and parallel execution…', () => parallel(true)));
  for (const [id, action] of [['clearSearch', clearSearch], ['clearParallel', clearParallel], ['clearOptimization', clearOptimization], ['clearCompression', () => { state.compression = {}; delete state.timings.huffman; delete state.timings.rle; clearContainer('compressionResults'); }], ['clearTimings', () => { state.timings = {}; }]]) $(id).addEventListener('click', () => { if (state.busy) return; action(); renderPerformance(); updateControls(); setStatus('Results cleared. Your documents are kept.'); });

  // Context guides for the retained map and cipher controls.
  const mapGuides = {startSelect: 'Choose where the shortest-path search begins.', goalSelect: 'Choose the destination for the shortest-path search.', cipherKey: 'Shift letters and digits by this key. Use the same key to decrypt.', executeBtn: 'Finds a shortest path with A* and demonstrates Caesar encryption.', resetEmptyBtn: 'Clears all map nodes and edges after confirmation.', resetSampleBtn: 'Replaces the current map with the built-in sample graph.', saveGraphBtn: 'Downloads your current graph as a text file.', loadGraphInput: 'Loads a saved graph text file and replaces the current map.', msgPlainInput: 'Enter a message for the educational Caesar cipher.', msgCipherKey: 'Choose the shift for message encryption. Use this same key to decrypt.', decryptCipherKey: 'Use the original encryption key to restore the message.', msgEncryptBtn: 'Shifts ASCII letters and digits using your selected key.', decryptBtn: 'Reverses Caesar shifts to recover the original message or path.', msgDownloadBtn: 'Downloads this encrypted message with its cipher key.', msgCopyBtn: 'Copies the encrypted message to the clipboard.', decryptCopyBtn: 'Copies the restored text to your clipboard.', copyBtn: 'Copies the displayed path export, including key and plaintext.', menuToggleBtn: 'Shows or hides the map editing controls.', closeRailBtn: 'Closes the map editing menu.', cipherLabToggleBtn: 'Shows or hides the path cipher, message encryptor, and decryptor.', decryptInput: 'Paste an encrypted message or a Wayglyph path export.', decryptFileInput: 'Load an exported text file for decryption.', exportBtn: 'Downloads the path result currently displayed in this browser tab.', modalCancelBtn: 'Cancels this action and keeps the current map.', modalConfirmBtn: 'Applies the action described in this confirmation dialog.'};
  const resultGuides = {'g(n)': 'Cost of the best known route from the start to this node.', 'h(n)': 'Estimated remaining cost to the goal. A* scales this estimate to fit the graph weights.', 'f(n)': 'A* priority: distance traveled plus estimated remaining cost, g(n) + h(n).', 'weight': 'Cost of this graph edge.', 'step': 'The order in which this search event occurred.', 'edge': 'The node or connection evaluated in this step.', 'evaluation status': 'Describes whether a node was reached, a route improved, or the goal was found.', 'plain': 'The original unencrypted edge weight.', 'encrypted': 'The weight after Caesar digit shifting.'};
  for (const node of document.querySelectorAll('#mapWorkspace button,#mapWorkspace input,#mapWorkspace textarea,#mapWorkspace select,#mapWorkspace label,#mapWorkspace th,[data-text-lab-toggle],#modalCancelBtn,#modalConfirmBtn')) {
    if (node.dataset.help) continue;
    const name = node.getAttribute('aria-label') || node.textContent.trim().replace(/\s+/g, ' ') || node.id;
    const forControl = node.getAttribute('for');
    node.dataset.help = mapGuides[node.id] || mapGuides[forControl] || resultGuides[name.toLowerCase()] || (node.matches('label,th') ? `The ${name.toLowerCase()} setting or result for this operation.` : `Use ${name.toLowerCase()} in the map and cipher lab.`);
  }
  studio.querySelectorAll('.algorithm-pill,.count-pill').forEach(node => { if (!node.dataset.help) node.dataset.help = node.classList.contains('count-pill') ? 'Number of documents currently loaded.' : `This section uses ${node.textContent.toLowerCase()}.`; });
  document.querySelectorAll('button:not([type])').forEach(node => { node.type = 'button'; });
  renderDataset(); renderPerformance(); updateControls(); decorate();
  window.wayglyphWorkspace(location.pathname === '/pathfinder' ? 'map' : 'text');
})();
