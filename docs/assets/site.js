// Copy-to-clipboard for the command blocks. Progressive enhancement:
// without JS the buttons stay inert, the commands are still selectable.
(function () {
  var buttons = document.querySelectorAll('.copy');

  Array.prototype.forEach.call(buttons, function (btn) {
    btn.addEventListener('click', function () {
      var block = btn.closest('.code');
      var pre = block && block.querySelector('pre');
      if (!pre) return;

      var text = pre.innerText.replace(/\u00a0/g, ' ').trim() + '\n';

      function done(ok) {
        btn.textContent = ok ? 'Copied' : 'Select';
        btn.classList.toggle('done', ok);
        clearTimeout(btn._reset);
        btn._reset = setTimeout(function () {
          btn.textContent = 'Copy';
          btn.classList.remove('done');
        }, 1600);
      }

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(
          function () { done(true); },
          function () { fallback(); }
        );
        return;
      }
      fallback();

      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '-1000px';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        done(ok);
      }
    });
  });
})();
