(() => {
  'use strict';
  const root = document.documentElement;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let finished = false;
  let watchdog;
  // Return a timer promise used to pace the startup screen.
  const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  // Remove the splash screen and unlock the main page once startup finishes.
  function finish() {
    if (finished) return;
    finished = true;
    clearTimeout(watchdog);
    const splash = document.getElementById('startupSplash');
    const shell = document.getElementById('appShell');
    if (shell) {
      shell.inert = false;
      shell.removeAttribute('aria-busy');
      shell.classList.add('app-entering');
      setTimeout(() => shell.classList.remove('app-entering'), 850);
    }
    if (splash) {
      document.getElementById('startupStatus').textContent = 'Opening Map & cipher';
      splash.classList.add('is-leaving');
    }
    // The timeout also handles browsers that suppress transitionend in background tabs.
    setTimeout(() => {
      root.classList.remove('is-booting');
      if (splash) splash.remove();
    }, reducedMotion.matches ? 0 : 650);
  }

  // Wait for the graph request and splash timer, then reveal the main page.
  document.addEventListener('DOMContentLoaded', async () => {
    if (finished) return;
    watchdog = setTimeout(finish, 6000);
    const shell = document.getElementById('appShell');
    shell.inert = true;
    shell.setAttribute('aria-busy', 'true');
    // Start the short brand sequence while the real graph request is in flight.
    // A slow or failed request must never leave the application behind the splash.
    await Promise.all([
      wait(reducedMotion.matches ? 0 : 2200),
      Promise.race([Promise.resolve(window.wayglyphGraphReady).catch(() => {}), wait(4500)]),
    ]);
    finish();
  }, { once: true });

  root.classList.add('is-booting');
})();
