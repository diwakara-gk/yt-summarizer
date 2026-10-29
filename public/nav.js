// Shared sidebar navigation, injected into every page's #navMount.
// Single source of truth for the nav list so adding a new page (like
// notes-summarizer.html) means editing this file once, not every page.
// "Home" isn't a nav link here on purpose: clicking the brand (Summarizer
// Hub) at the top takes you there instead, same pattern as most consoles.
(function () {
  const PAGES = [
    { href: 'youtube-summarizer.html', icon: '\u25B6\uFE0F', label: 'YouTube Summarizer' },
    { href: 'notes-summarizer.html', icon: '\uD83D\uDCDD', label: 'Notes Summarizer' },
    { href: 'settings.html', icon: '\uD83D\uDD11', label: 'Manage API Key' },
  ];

  const COLLAPSE_KEY = 'sidebarCollapsed';

  function currentPage() {
    const path = location.pathname.split('/').pop();
    return path || 'index.html';
  }

  function isCollapsed() {
    try { return localStorage.getItem(COLLAPSE_KEY) === 'true'; } catch (_) { return false; }
  }

  function applyCollapsed(shell, toggleBtn, collapsed) {
    shell.classList.toggle('sidebar-collapsed', collapsed);
    toggleBtn.setAttribute('aria-expanded', String(!collapsed));
    toggleBtn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    const icon = toggleBtn.querySelector('.nav-icon');
    const label = toggleBtn.querySelector('.nav-label');
    if (icon) icon.textContent = collapsed ? '\u00BB' : '\u00AB';
    if (label) label.textContent = collapsed ? 'Expand' : 'Collapse';
    try { localStorage.setItem(COLLAPSE_KEY, String(collapsed)); } catch (_) {}
  }

  function renderSidebar() {
    const mount = document.getElementById('navMount');
    const shell = document.querySelector('.app-shell');
    if (!mount || !shell) return;

    const here = currentPage();
    const linksHtml = PAGES.map(page => {
      const classes = ['nav-link'];
      if (page.href === here) classes.push('active');
      if (page.disabled) classes.push('disabled');
      const href = page.disabled ? '#' : page.href;
      const extraAttrs = page.disabled ? 'aria-disabled="true" tabindex="-1"' : '';
      const badge = page.disabled ? '<span class="soon-badge">Soon</span>' : '';
      return `<a class="${classes.join(' ')}" href="${href}" ${extraAttrs} title="${page.label}">` +
        `<span class="nav-icon" aria-hidden="true">${page.icon}</span><span class="nav-label">${page.label}</span>${badge}</a>`;
    }).join('');

    mount.innerHTML =
      '<a class="brand" href="index.html" title="Go to Summarizer Hub"><span aria-hidden="true">\u26A1</span><span class="nav-label">Summarizer Hub</span></a>' +
      linksHtml +
      '<button type="button" id="navToggle" class="nav-toggle">' +
      '<span class="nav-icon" aria-hidden="true">\u00AB</span><span class="nav-label">Collapse</span></button>';

    const toggleBtn = document.getElementById('navToggle');
    applyCollapsed(shell, toggleBtn, isCollapsed());
    toggleBtn.addEventListener('click', () => {
      applyCollapsed(shell, toggleBtn, !shell.classList.contains('sidebar-collapsed'));
    });
  }

  document.addEventListener('DOMContentLoaded', renderSidebar);
})();
