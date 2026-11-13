// History page: open the conversation scrolled to the newest message, like a messaging app.
(function () {
  'use strict';
  var body = document.getElementById('thread-body');
  if (body) body.scrollTop = body.scrollHeight;
})();
