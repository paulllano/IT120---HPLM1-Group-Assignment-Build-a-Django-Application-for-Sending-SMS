// Keep the page where it was after clicking a link or button that reloads the
// same page (choosing a conversation, "Check status", "Send SMS"), instead of
// jumping back to the top.
(function () {
  'use strict';

  var KEY = 'sms-sender-scroll';

  function remember() {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ path: location.pathname, y: window.scrollY }));
    } catch (e) { /* storage unavailable: just skip */ }
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest('a[href]');
    if (!link || link.target || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    var url = new URL(link.href, location.href);
    if (url.origin === location.origin && url.pathname === location.pathname) remember();
  });

  // Forms such as "Check status" post elsewhere but come back to this page.
  document.addEventListener('submit', remember);

  // Restore the position only when we're back on the same page.
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    sessionStorage.removeItem(KEY);
    if (saved && saved.path === location.pathname) {
      window.scrollTo(0, saved.y);
    }
  } catch (e) { /* ignore */ }
})();
