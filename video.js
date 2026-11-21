/* BullVideo — Telegram Mini App uchun YouTube video moduli. O'yin kodidan butunlay alohida.

   Ishlatish (index.html dagi startGame ichida):
     var vc = BullVideo.create({
       mount:   <video paneli qo'shiladigan element>,   // o'yin ostiga qo'yiladi
       overlay: <o'yin maydoni (position:relative)>,    // xatolik kartasi shu yerda ko'rsatiladi
       api:     function (path, data) -> Promise,       // asosiy ilovaning POST /api/<yo'l> funksiyasi
       onPause: function (reason) {},                   // video muammosi: o'yinni to'xtating
       onResume: function () {}                         // video qayta ishladi: o'yinni davom ettiring
     });
     vc.start()   -> Promise<boolean>  birinchi videodan boshlaydi; video haqiqatan PLAYING bo'lganda true
     vc.ensure()  -> Promise<boolean>  video hozir yaroqlimi (qayta urinish/raund almashishida videoni tegmaydi)
     vc.destroy()                                      // o'yindan chiqilganda

   Foydalanuvchining navbati va ijro holati faqat shu brauzerda saqlanadi, shuning uchun bir nechta foydalanuvchi bir-biriga xalaqit bermaydi.
   Server (videos/next) faqat "shu videodan keyin qaysi video" ni aytadi; joriy video o'chirilgan bo'lsa ham ijro to'xtamaydi. */
(function () {
  "use strict";

  var MSG = "Internet ishlamayapti yoki video yuklanmadi. Internet aloqasini tekshiring va davom ettirish tugmasini bosing";
  var MSG_BLOCK = "Video avtomatik boshlanmadi. Davom ettirish tugmasini bosing";
  var START_MS = 12000;     // video boshlanishini kutish (birinchi ishga tushirish va "Davom ettirish")
  var BUF_MS = 10000;       // BUFFERING shundan uzoq cho'zilsa — xatolik
  var PAUSE_MS = 1500;      // video kutilmaganda PAUSED holatida qolsa
  var IDLE_MS = 8000;       // video yuklangandan keyin PLAYING bo'lmasa (avtomatik ijro bloklangan)
  var API_MS = 6000;        // serverdan ro'yxat olish kutilishi
  var SKIP_MAX = 3;         // buzilgan (o'chirilgan/yopiq) videolarni ketma-ket o'tkazib yuborish chegarasi

  var CSS = ".bv-wrap{flex:none;position:relative;z-index:3;background:#05070d;border-top:2px solid rgba(255,255,255,.12);padding-bottom:env(safe-area-inset-bottom,0px)}" +
    ".bv-cap{display:flex;align-items:center;gap:8px;padding:6px 12px;font:700 12px/1.2 system-ui,-apple-system,sans-serif;color:#bfeee2;white-space:nowrap;overflow:hidden}" +
    ".bv-cap .t{overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}" +
    ".bv-up{flex:none;border:0;border-radius:12px;padding:6px 10px;background:rgba(255,255,255,.14);color:#fff;font:800 12px system-ui,sans-serif;cursor:pointer}" +
    ".bv-down{position:absolute;left:50%;bottom:calc(6px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);z-index:6;border:0;border-radius:14px;padding:6px 12px;background:rgba(10,14,30,.55);color:#fff;font:800 12px system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(4px)}" +
    ".bv-player{position:relative;width:100%;height:clamp(200px,56.25vw,36vh);background:#000}" +
    ".bv-player iframe{position:absolute;inset:0;width:100%;height:100%;border:0;display:block}" +
    ".bv-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#7d8aa0;font:600 14px system-ui,sans-serif;text-align:center;padding:16px}" +
    ".bv-fault{position:absolute;inset:0;z-index:9;display:none;align-items:center;justify-content:center;background:rgba(5,8,20,.86);padding:20px}" +
    ".bv-fault.show{display:flex}" +
    ".bv-card{width:min(100%,340px);background:#fff;color:#24307a;border-radius:24px;padding:22px 20px;text-align:center;display:flex;flex-direction:column;gap:14px;box-shadow:0 8px 0 #3b3d8f;font-family:system-ui,-apple-system,sans-serif}" +
    ".bv-card .i{font-size:34px;line-height:1}" +
    ".bv-card .m{font-size:15px;line-height:1.45;font-weight:600}" +
    ".bv-card button{padding:14px;border-radius:14px;font-weight:900;font-size:18px;background:#ff8a1f;color:#fff;box-shadow:0 5px 0 #c4600a;border:0;cursor:pointer}" +
    ".bv-card button:disabled{opacity:.6}";

  function injectCss() {
    if (document.getElementById("bv-css")) return;
    var s = document.createElement("style");
    s.id = "bv-css"; s.textContent = CSS;
    document.head.appendChild(s);
  }

  function mk(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function withTimeout(p, ms) {
    return new Promise(function (ok, bad) {
      var t = setTimeout(function () { bad(new Error("timeout")); }, ms);
      p.then(function (v) { clearTimeout(t); ok(v); }, function (e) { clearTimeout(t); bad(e); });
    });
  }

  /* ---------- YouTube IFrame API ---------- */
  var apiP = null;
  function loadApi() {
    if (window.YT && window.YT.Player) return Promise.resolve();
    if (apiP) return apiP;
    apiP = new Promise(function (ok, bad) {
      var prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = function () { try { if (prev) prev(); } catch (e) {} ok(); };
      var s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api"; s.async = true;
      s.onerror = function () { apiP = null; s.remove(); bad(new Error("yt api")); };
      document.head.appendChild(s);
      setTimeout(function () { if (!(window.YT && window.YT.Player)) { apiP = null; bad(new Error("yt timeout")); } }, 12000);
    });
    return apiP;
  }

  function netOk() {
    if (navigator.onLine === false) return Promise.resolve(false);
    var ctl = window.AbortController ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 5000);
    return fetch("/health?_=" + Date.now(), { cache: "no-store", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { clearTimeout(t); return r.ok; }, function () { clearTimeout(t); return false; });
  }

  /* ---------- modul ---------- */
  function create(opts) {
    injectCss();
    var P = null, pPromise = null;             // YT.Player
    var status = "idle";                        // idle | starting | running | fault
    var cur = null, cued = null, prefetched = null, prefetchFor = 0;
    var empty = false, advancing = false, resuming = false, destroyed = false;
    var stateSince = Date.now(), loadAt = 0, skips = 0;
    var waiters = [];

    /* --- ko'rinish --- */
    var wrap = mk("div", "bv-wrap"), cap = mk("div", "bv-cap"), capT = mk("span", "t", "Video yuklanmoqda…");
    var box = mk("div", "bv-player");
    var up = mk("button", "bv-up", "⬆ O‘yin");
    cap.appendChild(mk("span", "d", "🎵")); cap.appendChild(capT); cap.appendChild(up);
    wrap.appendChild(cap); wrap.appendChild(box);
    opts.mount.appendChild(wrap);
    /* o'yin butun ekranni egallaydi, video ekran tagida: pastga surish yoki tugma bilan o'tiladi */
    var down = mk("button", "bv-down", "🎵 Video ⬇");
    opts.overlay.appendChild(down);
    down.onclick = function () { opts.mount.scrollTo({ top: wrap.offsetTop, behavior: "smooth" }); };
    up.onclick = function () { opts.mount.scrollTo({ top: 0, behavior: "smooth" }); };

    var fault_ = mk("div", "bv-fault"), card = mk("div", "bv-card"), msgEl = mk("div", "m", MSG), btn = mk("button", null, "Davom ettirish");
    card.appendChild(mk("div", "i", "⏸")); card.appendChild(msgEl); card.appendChild(btn);
    fault_.appendChild(card);
    opts.overlay.appendChild(fault_);
    btn.onclick = resume;

    function setTitle(t) { capT.textContent = t || "Video"; }
    function showEmpty() {
      if (box.querySelector(".bv-empty")) return;
      box.appendChild(mk("div", "bv-empty", "Hozircha video qo‘yilmagan"));
      setTitle("Video yo‘q");
    }

    /* --- pleyer --- */
    function safeState() { try { return P ? P.getPlayerState() : -1; } catch (e) { return -1; } }

    function ensurePlayer(vid) {
      if (P) return Promise.resolve();
      if (pPromise) return pPromise;
      pPromise = loadApi().then(function () {
        return new Promise(function (ok, bad) {
          var holder = mk("div"), done = false;
          box.appendChild(holder);
          var t = setTimeout(function () { if (!done) bad(new Error("player timeout")); }, 12000);
          var pl = new window.YT.Player(holder, {
            width: "100%", height: "100%", videoId: vid,
            playerVars: { autoplay: 0, controls: 0, disablekb: 1, fs: 0, rel: 0, modestbranding: 1, playsinline: 1, iv_load_policy: 3, mute: 1, enablejsapi: 1, origin: location.origin },
            events: {
              onReady: function () {
                done = true; clearTimeout(t);
                if (destroyed) { try { pl.destroy(); } catch (e) {} return bad(new Error("destroyed")); }
                P = pl; try { pl.mute(); } catch (e) {} ok();
              },
              onStateChange: onState,
              onError: onErr
            }
          });
        });
      }).then(function () { pPromise = null; }, function (e) { pPromise = null; throw e; });
      return pPromise;
    }

    function play(v) {
      cur = v; prefetched = null; empty = false;
      var em = box.querySelector(".bv-empty"); if (em) em.remove();
      setTitle(v.title);
      loadAt = stateSince = Date.now();
      try { P.mute(); P.loadVideoById({ videoId: v.vid, startSeconds: 0 }); P.mute(); } catch (e) {}
    }

    function waitPlaying(ms) {
      return new Promise(function (ok, bad) {
        var w = { ok: ok, bad: bad }, iv, t;
        function clear() { clearInterval(iv); clearTimeout(t); var i = waiters.indexOf(w); if (i >= 0) waiters.splice(i, 1); }
        w.ok = function () { clear(); ok(); };
        w.bad = function (e) { clear(); bad(e || new Error("play")); };
        waiters.push(w);
        t = setTimeout(function () { w.bad(new Error("timeout")); }, ms);
        iv = setInterval(function () {
          var st = safeState(), age = Date.now() - loadAt;
          if (st === 1 && age > 700) w.ok();
          else if (age > 5000 && (st === -1 || st === 5 || st === 2)) w.bad(new Error("blocked"));      // buffering ham boshlanmadi — avtomatik ijro bloklangan
        }, 500);
      });
    }
    function settle(okFlag, err) { waiters.slice().forEach(function (w) { okFlag ? w.ok() : w.bad(err); }); }

    function begin(v) {                          // pleyerni tayyorlab, videoni boshidan ishga tushiradi, PLAYING ni kutadi
      return ensurePlayer(v.vid).then(function () { play(v); return waitPlaying(START_MS); });
    }

    /* --- YouTube hodisalari --- */
    function onState(e) {
      if (destroyed) return;
      stateSince = Date.now();
      var s = e.data;
      if (s === 1) {
        skips = 0;
        try { if (P && !P.isMuted()) P.mute(); } catch (x) {}
        settle(true);
        prefetch();
      } else if (s === 0) {
        if (status !== "fault") advance();
      }
    }

    function onErr(e) {
      if (destroyed) return;
      var code = e && e.data;
      if ((code === 100 || code === 101 || code === 150) && skips < SKIP_MAX) {   // video o'chirilgan/yopiq: keyingisiga o'tamiz
        skips++;
        advance();
        return;
      }
      settle(false, new Error("yt " + code));
      if (status === "running") fault("error");
    }

    function prefetch() {
      if (!cur || prefetchFor === cur.id) return;
      var me = cur; prefetchFor = me.id;
      withTimeout(opts.api("videos/next", { after_id: me.id, after_pos: me.pos }), API_MS)
        .then(function (r) { if (cur && cur.id === me.id) prefetched = r.video || null; }, function () {});
    }

    function fetchFirst() {
      return withTimeout(opts.api("videos/next", {}), API_MS).then(function (r) { return r.video || null; });
    }

    function advance() {                         // joriy video tugadi → ro'yxatdagi keyingisi (oxirgisidan keyin — birinchisi)
      if (advancing || destroyed) return;
      advancing = true;
      var from = cur;
      withTimeout(opts.api("videos/next", { after_id: from && from.id, after_pos: from && from.pos }), API_MS)
        .then(function (r) { return { v: r.video || null, ok: true }; }, function () { return { v: prefetched, ok: false }; })
        .then(function (x) {
          if (destroyed) return;
          if (x.v) return ensurePlayer(x.v.vid).then(function () { play(x.v); });
          if (x.ok) { empty = true; showEmpty(); } else fault("offline");
        })
        .then(function () { advancing = false; }, function () { advancing = false; if (status === "running") fault("error"); });
    }

    /* --- xatolik va davom ettirish --- */
    function fault(reason) {
      if (destroyed || status === "fault") return;
      status = "fault";
      msgEl.textContent = reason === "blocked" ? MSG_BLOCK : MSG;
      fault_.classList.add("show");
      if (opts.onPause) opts.onPause(reason);
    }

    function recover() {
      status = "running";
      fault_.classList.remove("show");
      if (opts.onResume) opts.onResume();
    }

    function restart() {                         // joriy videoni boshidan; yo'q bo'lsa — birinchi videoni
      if (cur) return begin(cur);
      return fetchFirst().then(function (v) {
        if (!v) { empty = true; showEmpty(); return; }
        return begin(v);
      });
    }

    function resume() {
      if (resuming || destroyed) return;
      resuming = true; btn.disabled = true; btn.textContent = "Tekshirilmoqda…";
      try { if (P) { P.mute(); P.playVideo(); } } catch (e) {}     // foydalanuvchi bosishi ichida ijroni "uyg'otamiz"
      netOk().then(function (ok) { if (!ok) throw new Error("offline"); return restart(); })
        .then(function () { if (!destroyed) recover(); },
          function () { if (!destroyed) { msgEl.textContent = MSG; } })
        .then(function () { resuming = false; btn.disabled = false; btn.textContent = "Davom ettirish"; });
    }

    /* --- kuzatuvchi: video holati va internet --- */
    var dog = setInterval(function () {
      if (status !== "running" || !P || advancing || empty || destroyed) return;
      var st = safeState(), el = Date.now() - stateSince;
      if (st === 1 || st === 0) return;
      if (st === 3) { if (el > BUF_MS) fault("buffering"); }
      else if (st === 2) { if (el > PAUSE_MS) fault("stopped"); }
      else if (el > IDLE_MS) fault("blocked");                    // -1 (UNSTARTED) yoki 5 (CUED)
    }, 1000);
    function onOffline() { if (status === "running") fault("offline"); }
    window.addEventListener("offline", onOffline);

    /* --- tashqi boshqaruv --- */
    function start() {                           // "Boshlash": har doim birinchi videodan
      if (destroyed) return Promise.resolve(false);
      status = "starting";
      var first = cued ? Promise.resolve(cued) : fetchFirst();
      return first.then(function (v) {
        if (!v) { empty = true; showEmpty(); status = "running"; return true; }
        return begin(v).then(function () { if (destroyed) return false; status = "running"; return true; });
      }).catch(function () {
        if (destroyed) return false;
        fault(navigator.onLine === false ? "offline" : (P ? "blocked" : "error"));
        return false;
      });
    }

    function ensure() { return Promise.resolve(!destroyed && (status === "running" || status === "starting")); }

    function destroy() {
      destroyed = true;
      clearInterval(dog);
      window.removeEventListener("offline", onOffline);
      settle(false, new Error("destroyed"));
      try { if (P) P.destroy(); } catch (e) {}
      P = null;
      wrap.remove(); fault_.remove();
    }

    /* --- o'yin boshlanmasdan oldin birinchi videoni ko'rsatib qo'yamiz (ijro yo'q) --- */
    fetchFirst().then(function (v) {
      if (destroyed) return;
      if (!v) { empty = true; showEmpty(); return; }
      cued = v; setTitle(v.title);
      return ensurePlayer(v.vid);
    }).catch(function () {});

    return { start: start, ensure: ensure, resume: resume, destroy: destroy, state: function () { return status; } };
  }

  window.BullVideo = { create: create };
})();
