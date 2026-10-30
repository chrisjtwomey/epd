/* The settings page: one tab at a time, fields that show only for some values of
   another, rows to add and remove, a count of unsaved changes, and a list of what
   a save changes before it happens. Without it the form still posts, with every
   tab shown at once. */
(function () {
  'use strict';

  var form = document.getElementById('settings-form');
  if (!form) return;
  document.documentElement.classList.add('js');

  var url = form.dataset.url;
  var tabs = Array.from(document.querySelectorAll('nav.tabs a[data-tab]'));
  var panels = Array.from(document.querySelectorAll('.panel[data-tab]'));
  var unsaved = document.getElementById('unsaved');
  var dialog = document.getElementById('review');
  var initial = JSON.parse(document.getElementById('initial').textContent);

  function showTab(name) {
    var known = tabs.some(function (t) { return t.dataset.tab === name; });
    var chosen = known ? name : tabs[0] && tabs[0].dataset.tab;
    tabs.forEach(function (t) {
      if (t.dataset.tab === chosen) t.setAttribute('aria-current', 'page');
      else t.removeAttribute('aria-current');
    });
    panels.forEach(function (p) { p.classList.toggle('shown', p.dataset.tab === chosen); });
  }

  function current(key) {
    var el = form.querySelector('[data-key="' + key + '"]');
    if (!el) return null;
    if (el.tagName === 'TABLE') {
      return JSON.stringify(Array.from(el.querySelectorAll('tbody tr')).map(function (tr) {
        return Array.from(tr.querySelectorAll('input')).map(function (i) { return i.value; });
      }));
    }
    if (el.type === 'checkbox') return el.checked ? 'true' : 'false';
    return el.value;
  }

  function applyWhen() {
    document.querySelectorAll('.field[data-when]').forEach(function (field) {
      var parts = field.dataset.when.split('=');
      var value = current(parts[0]);
      var shown = parts[1] === '*' ? Boolean(value) : (parts[1] || '').split('|').indexOf(value) >= 0;
      field.hidden = !shown;
    });
  }

  function countChanges() {
    var count = Object.keys(initial).filter(function (key) {
      var now = current(key);
      if (now === null) return false;
      var el = form.querySelector('[data-key="' + key + '"]');
      return el.type === 'password' ? now !== '' : now !== initial[key];
    }).length;
    unsaved.textContent = count ? count + (count === 1 ? ' unsaved change' : ' unsaved changes') : '';
  }

  function refresh() {
    applyWhen();
    countChanges();
  }

  function post(action) {
    var data = new URLSearchParams(new FormData(form));
    data.set('action', action);
    return fetch(url, {
      method: 'POST',
      body: data,
      headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
    }).then(function (rsp) {
      return rsp.json().then(function (body) { return { ok: rsp.ok, body: body }; });
    });
  }

  function say(words, klass) {
    var old = document.getElementById('said');
    if (old) old.remove();
    var p = document.createElement('p');
    p.id = 'said';
    p.className = 'banner ' + klass;
    p.setAttribute('role', 'alert');
    p.textContent = words;
    form.before(p);
    p.scrollIntoView({ block: 'nearest' });
  }

  function waitForServer() {
    say('Saved. The server is restarting.', 'notice');
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      fetch(url, { cache: 'no-store' }).then(function (rsp) {
        if (rsp.ok) {
          clearInterval(timer);
          location.href = url + '?saved=1';
        }
      }).catch(function () {
        if (tries > 30) {
          clearInterval(timer);
          say('The server did not come back. Check its log.', 'problem');
        }
      });
    }, 2000);
  }

  form.addEventListener('click', function (event) {
    var button = event.target;
    if (button.classList.contains('add-row')) {
      var template = button.parentElement.querySelector('template');
      button.parentElement.querySelector('tbody').append(template.content.cloneNode(true));
      refresh();
    } else if (button.classList.contains('remove-row')) {
      button.closest('tr').remove();
      refresh();
    } else if (button.id === 'save') {
      event.preventDefault();
      post('review').then(function (result) {
        if (!result.ok) { say(result.body.problem, 'problem'); return; }
        if (result.body.same) { say('Nothing to save.', 'notice'); return; }
        var body = dialog.querySelector('tbody');
        body.textContent = '';
        result.body.changes.forEach(function (c) {
          var tr = body.insertRow();
          [c.name, c.old, c.new].forEach(function (cell) { tr.insertCell().textContent = cell; });
        });
        dialog.showModal();
      }).catch(function () { say('Cannot reach the server. Try again.', 'problem'); });
    }
  });

  document.getElementById('review-cancel').addEventListener('click', function () { dialog.close(); });
  document.getElementById('review-save').addEventListener('click', function () {
    dialog.close();
    post('save').then(function (result) {
      if (!result.ok) { say(result.body.problem, 'problem'); return; }
      if (result.body.restarted) waitForServer();
      else location.href = url + '?saved=1';
    }).catch(function () { say('Cannot reach the server. Try again.', 'problem'); });
  });

  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  window.addEventListener('hashchange', function () { showTab(location.hash.slice(1)); });
  showTab(location.hash.slice(1));
  refresh();
})();
