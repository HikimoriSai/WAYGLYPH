/* Plain browser Brute Force: kept off the UI thread so typing stays responsive. */
self.onmessage = ({data}) => {
  try {
    const pattern = Array.from(data.pattern);
    if (!pattern.length) throw new Error('Enter a search phrase first.');
    const documents = data.documents.map(doc => ({name: doc.name, text: Array.from(doc.text)}));
    const work = documents.reduce((sum, doc) => sum + Math.max(0, doc.text.length - pattern.length + 1) * pattern.length, 0);
    if (work > 50_000_000) throw new Error('This Brute Force demo is limited to 50 million character checks. Try less text or a shorter search phrase.');
    const results = documents.map(doc => {
      const start = performance.now(), positions = [];
      for (let i = 0; i <= doc.text.length - pattern.length; i++) {
        let j = 0;
        while (j < pattern.length && doc.text[i + j] === pattern[j]) j++;
        if (j === pattern.length) positions.push(i);
      }
      return {name: doc.name, positions, count: positions.length, elapsed_ms: performance.now() - start};
    });
    self.postMessage({results});
  } catch (error) { self.postMessage({error: error.message}); }
};
