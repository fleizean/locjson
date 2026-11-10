/* locjson site script.
 * 1. Light syntax colouring for <pre data-lang="json|python">.
 * 2. The resolver demo on index.html: an illustration of the documented
 *    lookup rules, not the library. It only knows five request tags whose
 *    chains are spelled out in the README.
 * No dependencies, no network, no storage. */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* tiny DOM helpers                                                    */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  var PH_RE = /(\{\{|\}\}|\{[A-Za-z_][A-Za-z0-9_]*\})/;

  // A string token, with {placeholders} marked. `{{` and `}}` stay plain.
  function strToken(text) {
    var span = el("span", "t-str");
    text.split(PH_RE).forEach(function (part, i) {
      if (!part) return;
      if (i % 2 === 1 && part !== "{{" && part !== "}}") span.appendChild(el("span", "t-ph", part));
      else span.appendChild(document.createTextNode(part));
    });
    return span;
  }

  /* ------------------------------------------------------------------ */
  /* 1. highlighter                                                      */

  var JSON_RE = /("(?:[^"\\\n]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}\[\],:])/g;
  var PY_RE = /(#[^\n]*)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')|\b(from|import|with|as|def|return|for|in|if|else|None|True|False)\b|\b(\d+)\b|([A-Za-z_]\w*)(?=\()/g;

  function highlight(pre) {
    var lang = pre.getAttribute("data-lang");
    var re = lang === "json" ? JSON_RE : lang === "python" ? PY_RE : null;
    if (!re) return;
    var target = pre.querySelector("code") || pre;
    var src = target.textContent;
    var frag = document.createDocumentFragment();
    var last = 0;
    var m;
    re.lastIndex = 0;
    while ((m = re.exec(src))) {
      if (m.index > last) frag.appendChild(document.createTextNode(src.slice(last, m.index)));
      if (lang === "json") {
        if (m[1] && m[2]) {
          frag.appendChild(el("span", "t-key", m[1]));
          frag.appendChild(el("span", "t-p", m[2]));
        } else if (m[1]) frag.appendChild(strToken(m[1]));
        else if (m[3]) frag.appendChild(el("span", "t-num", m[3]));
        else if (m[4]) frag.appendChild(el("span", "t-kw", m[4]));
        else frag.appendChild(el("span", "t-p", m[5]));
      } else {
        if (m[1]) frag.appendChild(el("span", "t-com", m[1]));
        else if (m[2]) frag.appendChild(strToken(m[2]));
        else if (m[3]) frag.appendChild(el("span", "t-kw", m[3]));
        else if (m[4]) frag.appendChild(el("span", "t-num", m[4]));
        else frag.appendChild(el("span", "t-fn", m[5]));
      }
      last = re.lastIndex;
    }
    if (last < src.length) frag.appendChild(document.createTextNode(src.slice(last)));
    target.textContent = "";
    target.appendChild(frag);
  }

  /* ------------------------------------------------------------------ */
  /* 2. resolver demo data                                               */

  // en and tr are the README's quick-start catalogs, unchanged.
  var CATALOGS = {
    "en": {
      "greeting": "Hello, {name}!",
      "nav": { "home": "Home", "settings": "Settings" },
      "inbox": { "messages": {
        "zero": "You have no messages",
        "one": "You have {count} message",
        "other": "You have {count} messages"
      } }
    },
    "tr": {
      "greeting": "Merhaba, {name}!",
      "nav": { "home": "Ana sayfa", "settings": "Ayarlar" },
      "inbox": { "messages": {
        "zero": "Hiç mesajınız yok",
        "one": "{count} mesajınız var",
        "other": "{count} mesajınız var"
      } }
    },
    "zh-Hant": {
      "greeting": "你好，{name}！",
      "nav": { "home": "首頁", "settings": "設定" },
      "inbox": { "messages": {
        "zero": "你沒有任何訊息",
        "other": "你有 {count} 則訊息"
      } }
    },
    "ar": {
      "$meta": { "locale": "ar", "direction": "rtl" },
      "greeting": "مرحبًا، {name}!",
      "nav": { "home": "الرئيسية", "settings": "" },
      "inbox": { "messages": {
        "zero": "ليس لديك أي رسائل",
        "one": "لديك رسالة واحدة",
        "two": "لديك رسالتان",
        "few": "لديك {count} رسائل",
        "many": "لديك {count} رسالة",
        "other": "لديك {count} رسالة"
      } }
    }
  };

  // Chains for Localizer(default_locale="en", fallbacks={"pt-BR": ["pt"]}),
  // as documented: requested -> explicit fallbacks -> script-aware parents -> default.
  var CHAINS = {
    "en": [["en", "requested · default"]],
    "tr": [["tr", "requested"], ["en", "default_locale"]],
    "pt-BR": [["pt-BR", "requested"], ["pt", "fallbacks[\"pt-BR\"]"], ["en", "default_locale"]],
    "zh-TW": [["zh-TW", "requested"], ["zh-Hant", "parent: TW → Hant"], ["en", "default_locale"]],
    "ar": [["ar", "requested"], ["en", "default_locale"]]
  };

  var CATEGORIES = ["zero", "one", "two", "few", "many", "other"];
  var RTL_LANGS = { ar: 1, he: 1, fa: 1, ur: 1 };

  // Planned 0.2 CLDR cardinal rules, for whole numbers n >= 0 only.
  var CLDR = {
    en: function (n) { return n === 1 ? "one" : "other"; },
    tr: function (n) { return n === 1 ? "one" : "other"; },
    zh: function () { return "other"; },
    ar: function (n) {
      var m = n % 100;
      if (n === 0) return "zero";
      if (n === 1) return "one";
      if (n === 2) return "two";
      if (m >= 3 && m <= 10) return "few";
      if (m >= 11 && m <= 99) return "many";
      return "other";
    }
  };

  // 0.1 default rule: "one" when abs(count) == 1, otherwise "other".
  function rule01(n) { return Math.abs(n) === 1 ? "one" : "other"; }

  function langOf(tag) { return tag.split("-")[0]; }

  function isPlural(obj) {
    var keys = Object.keys(obj).filter(function (k) { return k.charAt(0) !== "$"; });
    return keys.length > 0 && "other" in obj && keys.every(function (k) {
      return CATEGORIES.indexOf(k) !== -1 && typeof obj[k] === "string";
    });
  }

  function flatten(obj, prefix, out) {
    Object.keys(obj).forEach(function (k) {
      if (k.charAt(0) === "$") return;
      var v = obj[k];
      var key = prefix ? prefix + "." + k : k;
      if (v !== null && typeof v === "object") {
        if (isPlural(v)) out[key] = { plural: v };
        else flatten(v, key, out);
      } else out[key] = v;
    });
    return out;
  }

  var FLAT = {};
  Object.keys(CATALOGS).forEach(function (tag) { FLAT[tag] = flatten(CATALOGS[tag], "", {}); });

  function render(tpl, vars) {
    return tpl.replace(/\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (all, name) {
      if (all === "{{") return "{";
      if (all === "}}") return "}";
      return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : all;
    });
  }

  function direction(requested) {
    var chain = CHAINS[requested];
    for (var i = 0; i < chain.length; i++) {
      var cat = CATALOGS[chain[i][0]];
      if (cat && cat.$meta && cat.$meta.direction) {
        return { dir: cat.$meta.direction, why: "$meta.direction in locales/" + chain[i][0] + ".json" };
      }
    }
    return { dir: RTL_LANGS[langOf(requested)] ? "rtl" : "ltr", why: "built-in table" };
  }

  function selectForm(entry, count, sourceTag, rules) {
    function has(c) { return typeof entry[c] === "string" && entry[c] !== ""; }
    if (count === 0 && has("zero")) {
      return { form: "zero", category: null, explicitZero: true };
    }
    var category = rules === "0.1" ? rule01(count) : CLDR[langOf(sourceTag)](count);
    return { form: has(category) ? category : "other", category: category, explicitZero: false };
  }

  function resolve(key, requested, opts) {
    var steps = [];
    var hit = null;
    CHAINS[requested].forEach(function (pair) {
      var tag = pair[0];
      var step = { tag: tag, why: pair[1] };
      if (hit) step.state = "skipped";
      else if (!FLAT[tag]) step.state = "nofile";
      else {
        var v = FLAT[tag][key];
        if (v === undefined) step.state = "missing";
        else if (v === "" || v === null) step.state = "empty";
        else { step.state = "hit"; hit = { tag: tag, value: v }; }
      }
      steps.push(step);
    });

    var out = { key: key, requested: requested, steps: steps, hit: hit, dir: direction(requested) };
    if (!hit) {
      out.text = key; // missing="key"
      out.missing = true;
      return out;
    }
    if (hit.value.plural) {
      var sel = selectForm(hit.value.plural, opts.count, hit.tag, opts.rules);
      out.plural = sel;
      out.entry = hit.value.plural;
      out.text = render(hit.value.plural[sel.form], { count: opts.count });
    } else {
      out.text = render(hit.value, key === "greeting" ? { name: opts.name } : {});
    }
    return out;
  }

  /* ------------------------------------------------------------------ */
  /* 2b. JSON view with highlighted lines                                */

  // Pretty-prints a catalog as lines and remembers each line's key path,
  // so the lines that answered can be marked.
  function jsonLines(obj) {
    var lines = [];
    function walk(value, path, depth, name, last) {
      var comma = last ? "" : ",";
      if (value !== null && typeof value === "object") {
        var keys = Object.keys(value);
        lines.push({ depth: depth, name: name, open: "{", path: path });
        keys.forEach(function (k, i) { walk(value[k], path.concat(k), depth + 1, k, i === keys.length - 1); });
        lines.push({ depth: depth, close: "}" + comma, path: path });
      } else {
        lines.push({ depth: depth, name: name, value: value, comma: comma, path: path });
      }
    }
    walk(obj, [], 0, null, true);
    return lines;
  }

  function drawJSON(pre, obj, keyPath, form) {
    pre.textContent = "";
    var key = keyPath ? keyPath.split(".") : null;
    jsonLines(obj).forEach(function (ln) {
      var row = el("span", "ln");
      var p = ln.path.join(".");
      if (key) {
        var inside = p === keyPath || p.indexOf(keyPath + ".") === 0;
        if (inside) row.classList.add(form ? (ln.path[ln.path.length - 1] === form && ln.path.length === key.length + 1 ? "hit-strong" : "hit") : "hit-strong");
      }
      row.appendChild(document.createTextNode(new Array(ln.depth + 1).join("  ")));
      if (ln.name != null) {
        row.appendChild(el("span", "t-key", JSON.stringify(ln.name)));
        row.appendChild(el("span", "t-p", ": "));
      }
      if (ln.open) row.appendChild(el("span", "t-p", ln.open));
      else if (ln.close) row.appendChild(el("span", "t-p", ln.close));
      else {
        if (typeof ln.value === "string") row.appendChild(strToken(JSON.stringify(ln.value)));
        else row.appendChild(el("span", "t-kw", JSON.stringify(ln.value)));
        if (ln.comma) row.appendChild(el("span", "t-p", ln.comma));
      }
      pre.appendChild(row);
    });
  }

  /* ------------------------------------------------------------------ */
  /* 2c. demo wiring                                                     */

  function initDemo(root) {
    var form = root.querySelector("#controls");
    var countInput = root.querySelector("#count");
    var nameInput = root.querySelector("#name");
    var app = root.querySelector("#app");
    var strings = Array.prototype.slice.call(root.querySelectorAll(".str[data-key]"));
    var callEl = root.querySelector("#call");
    var resultEl = root.querySelector("#result");
    var chainEl = root.querySelector("#chain");
    var fileEl = root.querySelector("#file");
    var fileName = root.querySelector("#file-name");
    var fileNote = root.querySelector("#file-note");
    var factsEl = root.querySelector("#facts");
    var pvMeta = root.querySelector("#pv-meta");
    var badge = root.querySelector("#badge");
    var ctlCount = root.querySelector("#ctl-count");
    var ctlName = root.querySelector("#ctl-name");

    var state = { key: "inbox.messages", count: 3 };

    function radio(name) {
      var r = form.querySelector('input[name="' + name + '"]:checked');
      return r ? r.value : null;
    }

    function readCount() {
      var n = parseInt(countInput.value, 10);
      if (isNaN(n)) return state.count;
      return Math.min(9999, Math.max(0, n));
    }

    function pyStr(s) { return JSON.stringify(s); }

    function fact(dt, dd) {
      factsEl.appendChild(el("dt", null, dt));
      var d = el("dd");
      (Array.isArray(dd) ? dd : [dd]).forEach(function (part) {
        d.appendChild(typeof part === "string" ? document.createTextNode(part) : part);
      });
      factsEl.appendChild(d);
    }

    function code(t) { return el("code", null, t); }

    var STATE_TEXT = {
      hit: "answers",
      nofile: "no catalog",
      missing: "key not in file",
      empty: "\"\" untranslated",
      skipped: "not consulted"
    };

    function update() {
      var requested = radio("locale");
      var rules = radio("rules");
      state.count = readCount();
      var opts = { count: state.count, name: nameInput.value, rules: rules };

      // preview: every string, as the app would render it
      var dir = direction(requested);
      app.setAttribute("lang", requested);
      app.setAttribute("dir", dir.dir);
      pvMeta.textContent = 'lang="' + requested + '" dir="' + dir.dir + '"';
      badge.textContent = String(state.count);
      strings.forEach(function (btn) {
        var r = resolve(btn.getAttribute("data-key"), requested, opts);
        btn.textContent = r.text;
        btn.setAttribute("lang", r.hit ? r.hit.tag : "en");
        btn.classList.toggle("is-missing", !!r.missing);
        btn.setAttribute("aria-pressed", String(btn.getAttribute("data-key") === state.key));
      });

      // trace for the selected key
      var res = resolve(state.key, requested, opts);
      var args = [pyStr(state.key), "locale=" + pyStr(requested)];
      if (state.key === "inbox.messages") args.push("count=" + state.count);
      if (state.key === "greeting") args.push("name=" + pyStr(nameInput.value));
      callEl.textContent = "l10n.t(" + args.join(", ") + ")";

      resultEl.textContent = res.text;
      resultEl.setAttribute("lang", res.hit ? res.hit.tag : "en");
      resultEl.setAttribute("dir", res.missing ? "ltr" : dir.dir);
      resultEl.classList.toggle("is-missing", !!res.missing);

      ctlCount.toggleAttribute("data-off", state.key !== "inbox.messages");
      ctlName.toggleAttribute("data-off", state.key !== "greeting");

      chainEl.textContent = "";
      res.steps.forEach(function (s) {
        var li = el("li");
        var box = el("span", "step");
        box.setAttribute("data-state", s.state);
        box.appendChild(el("span", "step__why", s.why));
        box.appendChild(el("span", "step__tag", s.tag));
        box.appendChild(el("span", "step__state", STATE_TEXT[s.state]));
        li.appendChild(box);
        chainEl.appendChild(li);
      });

      // file view
      var shown = res.hit ? res.hit.tag : "en";
      fileName.textContent = "locales/" + shown + ".json";
      fileNote.textContent = res.hit ? "answered" : "default, no match";
      drawJSON(fileEl, CATALOGS[shown], res.hit ? state.key : null, res.plural ? res.plural.form : null);

      // facts
      factsEl.textContent = "";
      fact("chain", res.steps.map(function (s) { return s.tag; }).join(" → "));
      if (res.hit) {
        fact("answered by", [code(res.hit.tag), " · locales/" + res.hit.tag + ".json"]);
        var skippedEmpty = res.steps.filter(function (s) { return s.state === "empty"; });
        if (skippedEmpty.length) {
          fact("fell through", [code(skippedEmpty[0].tag), " has the key, but its value is \"\", which counts as untranslated."]);
        }
      } else {
        fact("answered by", "no file in the chain has this key");
        fact("missing", [code('missing="key"'), " returns the key itself and logs a DEBUG record on the ", code("locjson"), " logger."]);
      }

      if (res.plural) {
        var p = res.plural;
        var lines = ["count=" + state.count + " → "];
        if (p.explicitZero) {
          lines.push(code("zero"));
          lines.push(", because count is 0 and the entry has a zero form. This applies in every language.");
        } else {
          var ruleName = rules === "0.1" ? "0.1 one/other rule" : "planned 0.2 CLDR rule for " + langOf(res.hit.tag);
          lines.push("the " + ruleName + " gives ");
          lines.push(code(p.category));
          if (p.form !== p.category) {
            lines.push("; the entry has no " + p.category + " form, so ");
            lines.push(code("other"));
          }
          lines.push(".");
        }
        fact("plural", lines);
        if (rules === "0.1" && !p.explicitZero) {
          var cldr = CLDR[langOf(res.hit.tag)](state.count);
          if (cldr !== p.form && typeof res.entry[cldr] === "string" && res.entry[cldr] !== "") {
            var w = el("span", "warn");
            w.appendChild(document.createTextNode("This entry also has a "));
            w.appendChild(code(cldr));
            w.appendChild(document.createTextNode(" form. 0.1 never selects it; the planned 0.2 CLDR rules will."));
            factsEl.lastChild.appendChild(w);
          }
        }
      }

      fact("direction", [code(dir.dir), " · " + dir.why]);
      if (dir.dir === "rtl" && res.hit && res.hit.tag !== requested) {
        var note = el("span", "warn", "The text came from " + res.hit.tag + ", but the page direction follows the requested locale.");
        factsEl.lastChild.appendChild(note);
      }
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); });
    form.addEventListener("change", update);
    nameInput.addEventListener("input", update);
    countInput.addEventListener("input", function () {
      if (countInput.value !== "" && !isNaN(parseInt(countInput.value, 10))) update();
    });
    countInput.addEventListener("change", function () {
      countInput.value = String(readCount());
      update();
    });
    root.querySelectorAll("[data-step]").forEach(function (b) {
      b.addEventListener("click", function () {
        countInput.value = String(Math.min(9999, Math.max(0, readCount() + Number(b.getAttribute("data-step")))));
        update();
      });
    });
    root.querySelectorAll("[data-count]").forEach(function (b) {
      b.addEventListener("click", function () {
        countInput.value = b.getAttribute("data-count");
        update();
      });
    });
    strings.forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.key = btn.getAttribute("data-key");
        update();
      });
    });

    // the four catalogs, printed from the same data the demo uses
    var box = root.querySelector("#catalogs");
    if (box) {
      Object.keys(CATALOGS).forEach(function (tag) {
        var sheet = el("div", "sheet");
        var tab = el("div", "tab");
        tab.appendChild(el("span", null, "locales/" + tag + ".json"));
        tab.appendChild(el("span", "tab__kind", "JSON"));
        var pre = el("pre", "json");
        drawJSON(pre, CATALOGS[tag], null, null);
        sheet.appendChild(tab);
        sheet.appendChild(pre);
        box.appendChild(sheet);
      });
    }

    update();
  }

  /* ------------------------------------------------------------------ */

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("pre[data-lang]"), highlight);
    var demo = document.getElementById("demo");
    if (demo) initDemo(demo);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
