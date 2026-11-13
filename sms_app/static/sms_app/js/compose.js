// Send SMS page: character counter, SMS part counter, live preview,
// clear button, and protection against double submission.
(function () {
  'use strict';

  var form = document.getElementById('sms-form');
  if (!form) return;

  var phoneInput = document.getElementById('id_recipient');
  var messageInput = document.getElementById('id_message');
  var charCount = document.getElementById('char-count');
  var smsParts = document.getElementById('sms-parts');
  var counter = document.getElementById('message-counter');
  var unicodeNote = document.getElementById('unicode-note');
  var previewTo = document.getElementById('preview-to');
  var bubble = document.getElementById('preview-bubble');
  var sendBtn = document.getElementById('send-btn');
  var clearBtn = document.getElementById('clear-btn');
  var maxLength = parseInt(messageInput.getAttribute('maxlength'), 10) || 459;

  // Characters in the standard GSM-7 SMS alphabet. Anything else (like emoji)
  // switches the whole message to Unicode, where one SMS holds only 70 characters.
  var GSM_BASIC = '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà';
  var GSM_EXTENDED = '^{}\\[~]|€'; // each of these counts as 2 characters

  function analyze(text) {
    var units = 0;
    var unicode = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (GSM_BASIC.indexOf(ch) !== -1) units += 1;
      else if (GSM_EXTENDED.indexOf(ch) !== -1) units += 2;
      else { unicode = true; break; }
    }
    if (unicode) units = text.length;

    var single = unicode ? 70 : 160;  // one SMS
    var perPart = unicode ? 67 : 153; // each part of a long SMS
    var parts = units === 0 ? 0 : (units <= single ? 1 : Math.ceil(units / perPart));
    var limit = parts <= 1 ? single : parts * perPart;
    return { units: units, unicode: unicode, parts: parts, limit: limit };
  }

  function formatPhone(value) {
    var digits = value.replace(/\D/g, '');
    if (digits.indexOf('63') === 0 && digits.length === 12) digits = '0' + digits.slice(2);
    if (digits.length === 10 && digits.charAt(0) === '9') digits = '0' + digits;
    if (digits.length === 11) {
      return digits.slice(0, 4) + ' ' + digits.slice(4, 7) + ' ' + digits.slice(7);
    }
    return value.trim();
  }

  function update() {
    var text = messageInput.value;
    var info = analyze(text);

    charCount.textContent = info.units + ' / ' + info.limit + ' characters';
    smsParts.textContent = info.parts <= 1 ? '1 SMS' : info.parts + ' SMS parts';
    counter.classList.toggle('is-near-limit', text.length > maxLength - 40);
    unicodeNote.hidden = !info.unicode;

    var phone = phoneInput.value.trim();
    previewTo.textContent = phone ? 'To: ' + formatPhone(phone) : 'To: no number yet';

    if (text.trim()) {
      bubble.textContent = text;
      bubble.classList.remove('is-empty');
    } else {
      bubble.textContent = 'Your message will appear here.';
      bubble.classList.add('is-empty');
    }
  }

  messageInput.addEventListener('input', update);
  phoneInput.addEventListener('input', update);

  clearBtn.addEventListener('click', function () {
    phoneInput.value = '';
    messageInput.value = '';
    update();
    phoneInput.focus();
  });

  form.addEventListener('submit', function () {
    // Prevent sending the same SMS twice by double-clicking.
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending…';
  });

  // Re-enable the button if the user comes back with the browser's Back button.
  window.addEventListener('pageshow', function () {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Send SMS';
  });

  update();
})();
