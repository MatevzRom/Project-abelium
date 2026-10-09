(() => {
  const config = JSON.parse(document.getElementById('tracking-config').textContent);
  const pages = ['home', 'content', 'statistics'];
  const status = document.getElementById('tracking-status');
  let totals = {home: 0, content: 0, statistics: 0};
  let viewKey, sequence = 0, active = false, busy = false;
  let retryStart = false;
  let confirmedAt = performance.now();
  let queue = Promise.resolve();

  function newKey() {
    // getRandomValues also works during HTTP testing on a local network.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function format(value) {
    const seconds = Math.floor(value);
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
  }

  function displayedTotals() {
    const result = {...totals};
    if (active && document.visibilityState === 'visible') {
      // Tentative animation is reconciled with saved server totals every heartbeat.
      result[config.page] += Math.min(config.interval, (performance.now() - confirmedAt) / 1000);
    }
    return result;
  }

  function render() {
    const current = displayedTotals();
    for (const page of pages) document.getElementById(`timer-${page}`).textContent = format(current[page]);
    const ownRow = document.querySelector(`[data-user-id="${config.userId}"]`);
    if (ownRow) pages.forEach((page, i) => ownRow.children[i + 1].textContent = format(current[page]));
  }

  async function loadStatistics() {
    const body = document.getElementById('statistics-body');
    if (!body || document.visibilityState !== 'visible') return;
    try {
      const response = await fetch('/api/statistics', {cache: 'no-store'});
      if (!response.ok) return;
      const data = await response.json();
      body.replaceChildren();
      for (const user of data.users) {
        const row = document.createElement('tr');
        row.dataset.userId = user.id;
        for (const value of [user.username, ...pages.map(page => format(user.totals[page]))]) {
          const cell = document.createElement('td');
          cell.textContent = value;
          row.appendChild(cell);
        }
        body.appendChild(row);
      }
      render();
    } catch { /* The tracking status already reports connection failures. */ }
  }

  function payload(action) {
    return {action, page: config.page, view_key: viewKey, sequence: ++sequence};
  }

  function send(action) {
    const data = payload(action);
    queue = queue.then(async () => {
      try {
        const response = await fetch('/api/tracking', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(data), signal: AbortSignal.timeout(config.interval * 1000),
        });
        if (response.status === 401) {
          window.location.assign('/login');
          return;
        }
        if (!response.ok) throw new Error('Tracking failed');
        const result = await response.json();
        if (data.view_key !== viewKey) return;
        if (action === 'start') retryStart = false;
        totals = result.totals;
        confirmedAt = performance.now();
        active = result.active && document.visibilityState === 'visible' && !busy;
        status.textContent = active ? 'Tracking this page · saved automatically' : 'Tracking paused';
        render();
        await loadStatistics();
      } catch {
        if (action === 'start') retryStart = true;
        active = false;
        status.textContent = 'Connection interrupted · retrying';
      }
    });
    return queue;
  }

  function start() {
    viewKey = newKey();
    sequence = 0;
    active = false;
    send('start');
  }

  function stopBeacon() {
    if (!viewKey || busy) return;
    active = false;
    status.textContent = 'Tracking paused';
    const blob = new Blob([JSON.stringify(payload('stop'))], {type: 'application/json'});
    navigator.sendBeacon('/api/tracking', blob);
  }

  document.addEventListener('visibilitychange', () => {
    if (busy) return;
    if (document.visibilityState === 'hidden') stopBeacon();
    else start(); // A fresh view never counts time spent hidden, even if stop was lost.
  });
  window.addEventListener('pagehide', stopBeacon);
  window.addEventListener('pageshow', event => {
    if (event.persisted && document.visibilityState === 'visible') {
      busy = false;
      start();
    }
  });

  document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', async event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (busy) return;
    busy = true;
    active = false;
    await send('stop');
    window.location.assign(link.href);
  }));

  document.getElementById('logout').addEventListener('click', async event => {
    if (busy) return;
    const button = event.currentTarget;
    button.disabled = true;
    busy = true;
    active = false;
    await queue;
    try {
      const response = await fetch('/logout', {method: 'POST'});
      if (!response.ok) throw new Error('Logout failed');
      window.location.assign('/login');
    } catch {
      document.getElementById('error').textContent = 'Could not log out. Please try again.';
      busy = false;
      button.disabled = false;
      if (document.visibilityState === 'visible') start();
    }
  });

  if (document.visibilityState === 'visible') start();
  setInterval(() => {
    if (!busy && document.visibilityState === 'visible') {
      if (retryStart) start();
      else send('heartbeat');
    }
  }, config.interval * 1000);
  setInterval(render, 250);
})();
