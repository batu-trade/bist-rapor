/* BIST Rapor — mobil web uygulaması.
 * Veriler GitHub Actions tarafından üretilen JSON dosyalarından okunur.
 * Kişisel portföy YALNIZCA bu cihazın tarayıcısında (localStorage) saklanır; hiçbir sunucuya gönderilmez.
 */
(function () {
  "use strict";
  const app = document.getElementById("app");
  const cache = {};
  const SLOT_NAMES = { premarket: "09:45 Açılış öncesi", opening: "10:15 Açılış sonrası", midday: "14:00 Gün ortası", close: "18:15 Kapanış" };
  const Q = { guvenilir: "Güvenilir", gecikmeli: "Gecikmeli", eksik: "Eksik", bayat: "Bayat", yok: "Veri yok" };
  const KIND = { veri: "Doğrulanmış veri", hesap: "Hesaplanmış gösterge", yorum: "Algoritmik yorum", senaryo: "Olası senaryo", uyari: "Uyarı" };

  // ---------- yardımcılar ----------
  function h(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function num(x, d) {
    if (x == null || isNaN(x)) return "—";
    return Number(x).toLocaleString("tr-TR", { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d });
  }
  function pct(x, d) {
    if (x == null || isNaN(x)) return "—";
    const s = x > 0 ? "+" : x < 0 ? "−" : "";
    return s + "%" + num(Math.abs(x), d == null ? 2 : d);
  }
  function cls(x) { return x > 0 ? "up" : x < 0 ? "down" : ""; }
  function tl(x) {
    if (x == null || isNaN(x)) return "—";
    const a = Math.abs(x);
    if (a >= 1e9) return num(x / 1e9, 2) + " mlr TL";
    if (a >= 1e6) return num(x / 1e6, 1) + " mn TL";
    return num(x, 0) + " TL";
  }
  function dt(s) { if (!s) return "—"; const d = new Date(s); return isNaN(d) ? "—" : d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  function hm(s) { if (!s) return "—"; const d = new Date(s); return isNaN(d) ? "—" : d.toLocaleTimeString("tr-TR", { timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit" }); }
  function qb(q) { return `<span class="badge q-${h(q || "yok")}">Veri: ${h(Q[q] || q || "—")}</span>`; }
  async function load(path, fresh) {
    if (!fresh && cache[path]) return cache[path];
    try {
      const res = await fetch("data/" + path + "?v=" + Date.now());
      if (!res.ok) throw new Error(res.status);
      const j = await res.json();
      cache[path] = j;
      return j;
    } catch (e) { return null; }
  }
  const store = {
    get(k, def) { try { const v = localStorage.getItem("bist." + k); return v ? JSON.parse(v) : def; } catch (e) { return def; } },
    set(k, v) { try { localStorage.setItem("bist." + k, JSON.stringify(v)); return true; } catch (e) { return false; } },
  };
  function cell(c) {
    if (c == null) return "—";
    if (typeof c === "object") {
      const t = h(c.t);
      if (c.link) return `<a href="#/hisse/${encodeURIComponent(c.link)}">${t}</a>`;
      return c.c ? `<span class="${h(c.c)}">${t}</span>` : t;
    }
    return h(c);
  }

  // ---------- rapor gösterimi ----------
  function renderItem(it) {
    const k = `<div class="kind kind-${h(it.kind)}">${h(KIND[it.kind] || it.kind)}</div>`;
    if (it.type === "text") {
      if (it.kind === "uyari") return `<div class="warnbox">${h(it.text)}</div>`;
      return `<div class="item">${k}<div>${h(it.text)}</div></div>`;
    }
    if (it.type === "list") return `<div class="item">${k}<ul class="bl">${it.items.map((x) => `<li>${h(x)}</li>`).join("")}</ul></div>`;
    if (it.type === "table") {
      if (!it.rows || !it.rows.length) return "";
      const head = it.columns.map((c) => `<th>${h(c)}</th>`).join("");
      const rows = it.rows.map((r) => "<tr>" + r.map((c, i) => `<td${(typeof c === "string" && c.length > 38) ? ' class="wrap"' : ""}>${cell(c)}</td>`).join("") + "</tr>").join("");
      return `<div class="item">${k}<div class="tbl"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>${it.note ? `<div class="note">${h(it.note)}</div>` : ""}</div>`;
    }
    if (it.type === "signals") return `<div class="item">${k}${it.signals.map(sigCard).join("")}</div>`;
    if (it.type === "news") return `<div class="item">${k}${it.items.map(newsItem).join("")}</div>`;
    return "";
  }
  function sigCard(s) {
    const name = s.kind === "swing" ? s.setup_tr : s.strategy_tr;
    const conf = s.kind === "swing" ? `Kalite ${h(s.grade)}` : `Güven: ${h(s.confidence)}`;
    const sz = s.size_example || {};
    const size = sz.ok ? `<div class="note">Örnek boyut (simülasyon defterine göre): ${num(sz.shares, 0)} lot ≈ ${tl(sz.position_value)}, en fazla risk ≈ ${tl(sz.risk_amount)}. ${sz.warnings && sz.warnings.length ? "⚠ " + h(sz.warnings.join(" • ")) : ""}</div>` :
      (sz.warnings ? `<div class="note">⚠ ${h(sz.warnings.join(" • "))}</div>` : "");
    return `<div class="sig">
      <div class="sig-h"><span class="sig-t"><a href="#/hisse/${encodeURIComponent(s.ticker)}">${h(s.ticker)}</a></span><span class="badge">${h(name)}</span></div>
      <div class="small muted">${h(s.name || "")} · Son ${num(s.price)} (${hm(s.time)}) · ${conf} · ${qb(s.quality)}</div>
      <div class="small">${h(s.explain || "")}</div>
      <div class="grid">
        <div><div class="l">Giriş bölgesi</div><div class="v">${num(s.entry_low)}–${num(s.entry_high)}</div></div>
        <div><div class="l">Zarar kes (stop)</div><div class="v down">${num(s.stop)}</div></div>
        <div><div class="l">Risk/getiri</div><div class="v">${num(s.rr, 1)}</div></div>
        <div><div class="l">Hedef 1</div><div class="v up">${num(s.t1)}</div></div>
        <div><div class="l">Hedef 2</div><div class="v up">${num(s.t2)}</div></div>
        <div><div class="l">${s.kind === "swing" ? "Tahmini süre" : "Yön"}</div><div class="v small">${h(s.kind === "swing" ? s.hold_days : s.direction)}</div></div>
      </div>
      <div class="small"><b>Neden ilginç?</b><ul class="bl pros">${(s.reasons || []).map((x) => `<li>${h(x)}</li>`).join("")}</ul></div>
      <div class="small"><b>Neden başarısız olabilir?</b><ul class="bl cons">${(s.risks || []).map((x) => `<li>${h(x)}</li>`).join("")}</ul></div>
      <div class="small muted">Geçersizlik: ${h(s.invalidation || "")}</div>${size}
    </div>`;
  }
  function newsItem(n) {
    const sc = n.sentiment === "olumlu" ? "up" : n.sentiment === "olumsuz" ? "down" : "muted";
    const safe = /^https:\/\//.test(n.link || "") ? n.link : "#";
    return `<div class="news-i"><a class="news-t" href="${h(safe)}" target="_blank" rel="noopener noreferrer">${h(n.title)}</a>
      <div class="small muted">${h(n.source)} · ${dt(n.published)} · ${h(n.category)} · <span class="${sc}">${h(n.sentiment)}</span>${n.tickers && n.tickers.length ? " · " + n.tickers.map((t) => `<a href="#/hisse/${encodeURIComponent(t)}">${h(t)}</a>`).join(", ") : ""}</div>
      <div class="small muted">Olası etki: ${h(n.impact)}</div></div>`;
  }
  function reportHeader(r) {
    const late = r.delay_minutes > 10;
    const timing = r.on_time ? `<span class="badge ok">Zamanında</span>` : late ? `<span class="badge warn">${num(r.delay_minutes, 0)} dk gecikmeli üretildi</span>` : `<span class="badge">Planlı saat dışında</span>`;
    const trig = r.trigger === "manual" ? `<span class="badge">Elle üretildi</span>` : "";
    const dq = r.data_quality || {};
    return `<div class="card">
      <div class="small muted">${h(r.day_name || "")} ${h(r.date)} · Planlanan ${h(r.scheduled_for)} · Üretildi ${hm(r.generated_at)}</div>
      <h1>${h(r.title)}</h1>
      <div>${timing}${trig}${qb(dq.overall)}</div>
      ${(r.warnings || []).map((w) => `<div class="warnbox">${h(w)}</div>`).join("")}
      <div class="headline">${h(r.headline)}</div>
      ${r.summary && r.summary.length ? `<ul class="bl">${r.summary.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }
  function picksCard(p) {
    if (!p) return "";
    const items = p.items || [];
    return `<div class="card"><h2>${h(p.title)}</h2>${items.length ? `<ul class="bl picks">${items.map((x) => `<li><a href="#/hisse/${encodeURIComponent(x.ticker)}"><b>${h(x.ticker)}</b></a> — ${h((x.why || []).join("; "))}</li>`).join("")}</ul>` :
      `<p class="muted small">Şu an yeterince güçlü bir aday yok. Sistem zorla öneri üretmez.</p>`}</div>`;
  }
  function renderReport(r) {
    if (!r) return `<div class="card"><p>Rapor bulunamadı.</p></div>`;
    let html = reportHeader(r) + picksCard(r.picks);
    (r.sections || []).forEach((s, i) => {
      html += `<details class="sec" ${i < 3 ? "open" : ""}><summary>${h(s.title)}</summary><div class="secbody">${s.items.map(renderItem).join("")}</div></details>`;
    });
    if (r.important && r.important.length) html += `<div class="card"><h2>Önemli gelişmeler</h2><ul class="bl">${r.important.map((x) => `<li>${h(x)}</li>`).join("")}</ul></div>`;
    const dq = r.data_quality || { details: [] };
    html += `<details class="sec"><summary>Veri kalitesi ve kaynaklar</summary><div class="secbody">
      <div class="tbl"><table><thead><tr><th>Veri</th><th>Kalite</th><th>Açıklama</th></tr></thead><tbody>
      ${dq.details.map((d) => `<tr><td>${h(d.name)}</td><td class="q-${h(d.quality)}">${h(Q[d.quality] || d.quality)}</td><td class="wrap">${h(d.note || "")}</td></tr>`).join("")}
      </tbody></table></div>
      <h3>Kaynaklar</h3><ul class="bl">${(r.sources || []).map((s) => `<li>${h(s)}</li>`).join("")}</ul>
      <p class="small muted">${h(r.universe_note || "")}</p>
      <h3>Etiketler</h3><ul class="bl">${Object.entries(r.kinds || KIND).map(([k, v]) => `<li><span class="kind kind-${h(k)}">${h(v)}</span></li>`).join("")}</ul>
    </div></details>`;
    html += `<p class="foot">${h(r.disclaimer || "")}</p>`;
    return html;
  }

  // ---------- sayfalar ----------
  async function pageToday(slotParam) {
    const idx = await load("index.json", true);
    const status = await load("status.json", true);
    if (!idx || !idx.reports || !idx.reports.length) {
      return `<div class="card"><h1>Henüz rapor yok</h1><p>Sistem kuruldu; ilk rapor bir sonraki işlem günü 09:45'te (İstanbul saati) otomatik üretilecek.</p>${statusSummary(status)}</div>`;
    }
    const latestDate = idx.reports[0].date;
    const today = idx.reports.filter((x) => x.date === latestDate);
    const slot = slotParam || today[0].slot;
    const meta = today.find((x) => x.slot === slot) || today[0];
    const rep = await load(`reports/${meta.date}/${meta.slot}.json`);
    const st = (status && status.reports && status.reports[latestDate]) || {};
    const chips = ["premarket", "opening", "midday", "close"].map((s) => {
      const have = today.find((x) => x.slot === s);
      const missed = st[s] && st[s].status === "missed";
      const failed = st[s] && st[s].status === "failed";
      const label = SLOT_NAMES[s] + (missed ? " (kaçırıldı)" : failed ? " (hata)" : "");
      return have ? `<a class="chip ${s === meta.slot ? "on" : ""}" href="#/bugun/${s}">${h(label)}</a>` : `<span class="chip dim">${h(label)}</span>`;
    }).join("");
    return `<div class="chips">${chips}</div>${statusAlerts(status, latestDate)}${renderReport(rep)}`;
  }
  function statusAlerts(status, day) {
    if (!status) return "";
    const st = (status.reports || {})[day] || {};
    const out = [];
    Object.entries(st).forEach(([slot, e]) => {
      if (e.status === "missed") out.push(`${SLOT_NAMES[slot]} raporu zamanında üretilemedi (bulut zamanlayıcısı gecikmiş olabilir).`);
      if (e.status === "failed") out.push(`${SLOT_NAMES[slot]} raporu hata nedeniyle üretilemedi: ${e.error || ""}`);
    });
    return out.map((x) => `<div class="warnbox">${h(x)}</div>`).join("");
  }
  function statusSummary(status) {
    if (!status) return "";
    const lr = status.last_run;
    return `<p class="small muted">Son çalışma: ${lr ? dt(lr.at) : "—"} · Site güncellemesi: ${dt(status.built_at)}</p>`;
  }

  async function pageOpps(tab) {
    tab = tab || "gunici";
    const stocks = await load("stocks.json");
    const fund = await load("fundamentals.json");
    const tabs = [["gunici", "Gün içi"], ["swing", "Swing (2–20 gün)"], ["uzun", "Uzun vade"]]
      .map(([k, v]) => `<a class="chip ${k === tab ? "on" : ""}" href="#/firsatlar/${k}">${v}</a>`).join("");
    let body = "";
    const when = stocks ? `<p class="small muted">Son güncelleme: ${dt(stocks.generated_at)} (rapor ${h(stocks.report_id || "")})</p>` : "";
    if (!stocks) body = `<div class="card">Veri henüz yok.</div>`;
    else if (tab === "gunici") {
      const sigs = stocks.items.map((s) => s.intraday).filter(Boolean).sort((a, b) => b.score - a.score);
      body = `<div class="card small">Gün içi fırsatlar ücretsiz ve yaklaşık 15 dakika gecikmeli 5 dakikalık verilerden hesaplanır. Gerçek fiyat farklı olabilir. Bunlar analitik senaryodur, alım-satım talimatı değildir.</div>` +
        (sigs.length ? sigs.map(sigCard).join("") : `<div class="card">Son raporda kriterleri karşılayan gün içi kurulum yok. Sistem zorla öneri üretmez.</div>`);
    } else if (tab === "swing") {
      const sigs = stocks.items.map((s) => s.swing).filter(Boolean).sort((a, b) => b.score - a.score);
      body = `<div class="card small">Swing: birkaç günden birkaç haftaya kadar tutulabilecek kurulumlar. Kurulum kalitesine göre sıralanmıştır (A en iyi).</div>` +
        (sigs.length ? sigs.map(sigCard).join("") : `<div class="card">Şu an kriterleri karşılayan swing kurulumu yok.</div>`);
    } else {
      body = fundPage(fund);
    }
    return `<div class="chips">${tabs}</div>${when}${body}`;
  }
  function fundPage(fund) {
    if (!fund || !fund.items || !fund.items.length) return `<div class="card">Temel analiz verisi henüz toplanıyor. Her kapanış raporunda bir kısmı güncellenir.</div>`;
    const order = ["Güçlü şirket, makul değerleme", "Güçlü şirket ama pahalı", "İzlemeye değer", "Ucuz ama riskli", "Temelleri zayıflıyor", "Veri yetersiz"];
    let html = `<div class="warnbox">${h(fund.note)}</div>`;
    order.forEach((c) => {
      const items = fund.items.filter((m) => m.class === c);
      if (!items.length) return;
      html += `<details class="sec" ${c === order[0] ? "open" : ""}><summary>${h(c)} (${items.length})</summary><div class="secbody">
        <p class="small muted">${h(items[0].class_explain)}</p>
        ${items.map((m) => `<a class="list-row" href="#/hisse/${encodeURIComponent(m.ticker)}"><span><b>${h(m.ticker)}</b><br><span class="small muted">${h(m.sector)}</span></span>
          <span class="r small">F/K ${num(m.pe, 1)} · PD/DD ${num(m.pb, 2)}<br>ROE ${m.roe == null ? "—" : "%" + num(m.roe, 0)} · Kalite ${m.quality == null ? "—" : num(m.quality, 0) + "/100"}</span></a>`).join("")}
      </div></details>`;
    });
    return html;
  }

  async function pageStocks() {
    const stocks = await load("stocks.json");
    if (!stocks) return `<div class="card">Veri henüz yok.</div>`;
    const fav = store.get("favs", []);
    const items = stocks.items.slice().sort((a, b) => (b.watch - a.watch) || (fav.includes(b.ticker) - fav.includes(a.ticker)) || a.ticker.localeCompare(b.ticker));
    const rows = items.map((s) => `<a class="list-row" data-t="${h(s.ticker)} ${h((s.name || "").toLowerCase())} ${h((s.sector || "").toLowerCase())}" href="#/hisse/${encodeURIComponent(s.ticker)}">
      <span><b>${h(s.ticker)}</b>${s.watch ? ' <span class="badge">izleme</span>' : ""}${fav.includes(s.ticker) ? " ★" : ""}<br><span class="small muted">${h(s.name || "")} · ${h(s.sector || "")}</span></span>
      <span class="r"><b>${num(s.price)}</b><br><span class="${cls(s.chg)} small">${pct(s.chg)}</span></span></a>`).join("");
    setTimeout(() => {
      const inp = document.getElementById("q");
      if (inp) inp.addEventListener("input", () => {
        const v = inp.value.trim().toLowerCase();
        document.querySelectorAll("#list .list-row").forEach((el) => { el.style.display = !v || el.dataset.t.toLowerCase().includes(v) ? "" : "none"; });
      });
    });
    return `<div class="card"><input id="q" type="search" placeholder="Hisse ara (örn. THYAO, banka)" autocomplete="off"></div>
      <p class="small muted">Fiyatlar ${dt(stocks.generated_at)} itibarıyla, ücretsiz kaynaktan ve gecikmelidir. Taranan liste resmî BIST 100 listesi değildir.</p>
      <div class="card" id="list">${rows}</div>`;
  }

  function spark(vals) {
    const v = (vals || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const min = Math.min(...v), max = Math.max(...v), w = 300, hh = 70;
    const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${hh - ((x - min) / (max - min || 1)) * (hh - 6) - 3}`).join(" ");
    const col = v[v.length - 1] >= v[0] ? "var(--up)" : "var(--down)";
    return `<svg class="spark" viewBox="0 0 ${w} ${hh}" preserveAspectRatio="none" role="img" aria-label="Son 90 günlük fiyat grafiği"><polyline fill="none" stroke="${col}" stroke-width="2" points="${pts}"/></svg>`;
  }
  async function pageStock(t) {
    const stocks = await load("stocks.json");
    const fund = await load("fundamentals.json");
    const s = stocks && stocks.items.find((x) => x.ticker === t);
    if (!s) return `<div class="card">${h(t)} için veri yok. Bu hisse taranan listede değilse izleme listenize ekleyebilirsiniz (Daha → İzleme listesini düzenle).</div>`;
    const m = fund && fund.items.find((x) => x.ticker === t);
    const fav = store.get("favs", []);
    const isFav = fav.includes(t);
    setTimeout(() => {
      const b = document.getElementById("favbtn");
      if (b) b.onclick = () => { const f = store.get("favs", []); const i = f.indexOf(t); if (i >= 0) f.splice(i, 1); else f.push(t); store.set("favs", f); route(); };
    });
    const sr = s.sr || { supports: [], resistances: [] };
    let html = `<div class="card"><div class="sig-h"><h1>${h(t)}</h1><span class="${cls(s.chg)}">${pct(s.chg)}</span></div>
      <div class="small muted">${h(s.name || "")} · ${h(s.sector || "")}${s.bist30 ? " · BIST 30 (yaklaşık)" : ""}</div>
      <div class="headline">${num(s.price)} TL <span class="small muted">(${dt(s.time)})</span></div>
      <div>${qb(s.q_daily)}${s.q_intra ? qb(s.q_intra) : ""}<span class="badge">Likidite: ${h(s.liq || "—")}</span></div>
      ${spark(s.spark)}<div class="note">Son 90 işlem günü kapanışları</div>
      <button class="ghost" id="favbtn">${isFav ? "★ Favorilerden çıkar" : "☆ Favorilere ekle"}</button></div>`;
    html += `<div class="card"><h2>Teknik görünüm</h2><div class="kind kind-hesap">Hesaplanmış gösterge</div>
      <div class="grid">
        <div><div class="l">Eğilim</div><div class="v small">${h(s.trend || "—")}</div></div>
        <div><div class="l">RSI (14)</div><div class="v">${num(s.rsi, 0)}</div></div>
        <div><div class="l">ADX</div><div class="v">${num(s.adx, 0)}</div></div>
        <div><div class="l">EMA 20</div><div class="v">${num(s.ema20)}</div></div>
        <div><div class="l">EMA 50</div><div class="v">${num(s.ema50)}</div></div>
        <div><div class="l">EMA 200</div><div class="v">${num(s.ema200)}</div></div>
        <div><div class="l">ATR (oynaklık)</div><div class="v">%${num(s.atr_pct, 1)}</div></div>
        <div><div class="l">Hacim / ort.</div><div class="v">${s.relvol ? num(s.relvol, 1) + "x" : "—"}</div></div>
        <div><div class="l">Ort. günlük hacim</div><div class="v small">${tl(s.avg_tl_vol20)}</div></div>
        <div><div class="l">5 gün</div><div class="v ${cls(s.ret5)}">${pct(s.ret5, 1)}</div></div>
        <div><div class="l">20 gün</div><div class="v ${cls(s.ret20)}">${pct(s.ret20, 1)}</div></div>
        <div><div class="l">BIST100'e göre (20g)</div><div class="v ${cls(s.rs20)}">${s.rs20 == null ? "—" : (s.rs20 > 0 ? "+" : "") + num(s.rs20, 1) + " puan"}</div></div>
      </div>
      <div class="small">Destekler: <b>${sr.supports.map((x) => num(x)).join(" / ") || "—"}</b> · Dirençler: <b>${sr.resistances.map((x) => num(x)).join(" / ") || "—"}</b></div>
      ${(s.unusual || []).length ? `<div class="small">Dikkat: ${h(s.unusual.join(", "))}</div>` : ""}
      ${(s.problems || []).length ? `<div class="warnbox">Veri uyarısı: ${h(s.problems.join("; "))}</div>` : ""}
      ${s.intra_status && s.intra_status.weakness ? `<div class="warnbox">${h(s.intra_status.weakness)}</div>` : ""}
    </div>`;
    if (s.intraday) html += `<div class="card"><h2>Gün içi kurulum</h2>${sigCard(s.intraday)}</div>`;
    if (s.swing) html += `<div class="card"><h2>Swing kurulumu</h2>${sigCard(s.swing)}</div>`;
    if (!s.intraday && !s.swing) html += `<div class="card small muted">Bu hissede şu an kriterleri karşılayan bir gün içi veya swing kurulumu yok.</div>`;
    if (m) {
      html += `<div class="card"><h2>Uzun vade (temel analiz)</h2><div class="kind kind-yorum">Algoritmik yorum</div>
        <div class="headline">${h(m.class)}</div><p class="small">${h(m.class_explain)}</p>
        <div class="grid">
          <div><div class="l">F/K</div><div class="v">${num(m.pe, 1)}</div></div>
          <div><div class="l">PD/DD</div><div class="v">${num(m.pb, 2)}</div></div>
          <div><div class="l">FD/FAVÖK</div><div class="v">${num(m.ev_ebitda, 1)}</div></div>
          <div><div class="l">ROE</div><div class="v">${m.roe == null ? "—" : "%" + num(m.roe, 0)}</div></div>
          <div><div class="l">ROIC</div><div class="v">${m.roic == null ? "—" : "%" + num(m.roic, 0)}</div></div>
          <div><div class="l">Net marj</div><div class="v">${m.net_margin == null ? "—" : "%" + num(m.net_margin, 1)}</div></div>
          <div><div class="l">FAVÖK marjı</div><div class="v">${m.ebitda_margin == null ? "—" : "%" + num(m.ebitda_margin, 1)}</div></div>
          <div><div class="l">Net borç/FAVÖK</div><div class="v">${num(m.nd_ebitda, 1)}</div></div>
          <div><div class="l">Temettü verimi</div><div class="v">${m.div_yield == null ? "—" : "%" + num(m.div_yield, 1)}</div></div>
          <div><div class="l">Satış büyümesi (reel)</div><div class="v ${cls(m.rev_growth_real)}">${pct(m.rev_growth_real, 0)}</div></div>
          <div><div class="l">Net kâr büyümesi (reel)</div><div class="v ${cls(m.ni_growth_real)}">${pct(m.ni_growth_real, 0)}</div></div>
          <div><div class="l">Temettü (5 yılda)</div><div class="v">${num(m.div_years_5y, 0)} yıl</div></div>
        </div>
        <div class="small">Sektör medyanı: F/K ${num(m.sector_pe_median, 1)} · PD/DD ${num(m.sector_pb_median, 2)} (${h(m.sector)})</div>
        ${m.positives.length ? `<ul class="bl pros small">${m.positives.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : ""}
        ${m.negatives.length ? `<ul class="bl cons small">${m.negatives.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : ""}
        ${m.notes.map((x) => `<div class="note">• ${h(x)}</div>`).join("")}
        <div class="note">Mali yıl: ${h(m.year || "—")} · Raporlama: ${h(m.reporting)} · Değerleme tarihi: ${h(m.valuation_date || "—")}. Kaynak: Yahoo Finance (ücretsiz, eksik olabilir). Resmî raporlar için KAP.</div>
      </div>`;
    }
    html += `<p class="foot">Yatırım tavsiyesi değildir. Veriler ücretsiz kaynaklardan ve gecikmelidir.</p>`;
    return html;
  }

  // ---------- portföy (yalnızca bu cihazda) ----------
  const CATS = { uzun_vade: "Uzun vade", swing: "Swing", gun_ici: "Gün içi", nakit_rezerv: "Nakit rezerv (yakın gelecek harcamaları)" };
  async function pagePortfolio() {
    const stocks = await load("stocks.json");
    const status = await load("status.json");
    const px = {};
    const sec = {};
    (stocks ? stocks.items : []).forEach((s) => { px[s.ticker] = s.price; sec[s.ticker] = s.sector; });
    const pf = store.get("portfolio", { holdings: [], cash: {}, need: 0 });
    let total = 0;
    const byCat = { uzun_vade: 0, swing: 0, gun_ici: 0, nakit_rezerv: 0 };
    const byT = {}, bySec = {};
    const rows = pf.holdings.map((x, i) => {
      const p = px[x.ticker];
      const val = p ? p * x.qty : x.cost * x.qty;
      total += val; byCat[x.cat] = (byCat[x.cat] || 0) + val;
      byT[x.ticker] = (byT[x.ticker] || 0) + val;
      const sname = sec[x.ticker] || "Diğer"; bySec[sname] = (bySec[sname] || 0) + val;
      const pl = p ? (p / x.cost - 1) * 100 : null;
      return `<tr><td><a href="#/hisse/${encodeURIComponent(x.ticker)}">${h(x.ticker)}</a></td><td>${num(x.qty, 0)}</td><td>${num(x.cost)}</td><td>${num(p)}</td><td class="${cls(pl)}">${pct(pl, 1)}</td><td>${tl(val)}</td><td>${h(CATS[x.cat] || x.cat)}</td><td><a href="#" data-del="${i}">Sil</a></td></tr>`;
    }).join("");
    Object.entries(pf.cash || {}).forEach(([k, v]) => { total += +v || 0; byCat[k] = (byCat[k] || 0) + (+v || 0); });
    const plan = (status && status.settings_public && status.settings_public.capital_split_pct) || { uzun_vade: 50, swing: 20, gun_ici: 10, nakit_rezerv: 20 };
    const planSum = Object.values(plan).reduce((a, b) => a + b, 0) || 100;
    const warns = [];
    const stockTotal = Object.values(byT).reduce((a, b) => a + b, 0);
    Object.entries(byT).forEach(([t, v]) => { if (stockTotal && v / stockTotal > 0.25) warns.push(`${t} hisse portföyünüzün %${num(v / stockTotal * 100, 0)}'i: tek hissede yoğunlaşma riski.`); });
    Object.entries(bySec).forEach(([s, v]) => { if (stockTotal && v / stockTotal > 0.4 && Object.keys(bySec).length > 1) warns.push(`${s} sektörü hisse portföyünüzün %${num(v / stockTotal * 100, 0)}'i: sektör yoğunlaşması.`); });
    if (pf.need && (byCat.nakit_rezerv || 0) < pf.need) warns.push(`Yakın gelecekte ihtiyaç duyacağınızı yazdığınız ${tl(pf.need)} için nakit rezerviniz (${tl(byCat.nakit_rezerv || 0)}) yetersiz. Bu parayı riskli işlemlerden ayrı tutmanız önerilir.`);
    const alloc = Object.keys(CATS).map((k) => {
      const cur = total ? (byCat[k] || 0) / total * 100 : 0;
      const tgt = (plan[k] || 0) / planSum * 100;
      return `<div class="small" style="margin:6px 0">${h(CATS[k])}: <b>${tl(byCat[k] || 0)}</b> (%${num(cur, 0)} · hedef %${num(tgt, 0)})<div class="bar"><i style="width:${Math.min(100, cur)}%"></i></div></div>`;
    }).join("");
    setTimeout(bindPortfolio);
    return `<div class="card small">🔒 Bu sayfadaki bilgiler <b>yalnızca bu telefonun tarayıcısında</b> saklanır, internete gönderilmez. Tarayıcı verisini silerseniz kaybolur; aşağıdan yedek alabilirsiniz. Fiyatlar gecikmelidir.</div>
      <div class="card"><h2>Toplam: ${tl(total)}</h2>${alloc}${warns.map((w) => `<div class="warnbox">${h(w)}</div>`).join("")}</div>
      <div class="card"><h2>Hisselerim</h2>${rows ? `<div class="tbl"><table><thead><tr><th>Hisse</th><th>Adet</th><th>Maliyet</th><th>Son</th><th>K/Z</th><th>Değer</th><th>Kategori</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="small muted">Henüz hisse eklemediniz.</p>`}
        <h3>Hisse ekle</h3>
        <div class="row3"><div><label>Kod</label><input id="pf-t" placeholder="THYAO" autocapitalize="characters"></div><div><label>Adet</label><input id="pf-q" type="number" inputmode="decimal"></div><div><label>Ort. maliyet</label><input id="pf-c" type="number" inputmode="decimal" step="0.01"></div></div>
        <label>Kategori</label><select id="pf-k">${Object.entries(CATS).filter(([k]) => k !== "nakit_rezerv").map(([k, v]) => `<option value="${k}">${h(v)}</option>`).join("")}</select>
        <p><button id="pf-add">Ekle</button></p></div>
      <div class="card"><h2>Nakit</h2>${Object.entries(CATS).map(([k, v]) => `<label>${h(v)} (TL)</label><input data-cash="${k}" type="number" inputmode="decimal" value="${h((pf.cash || {})[k] || "")}">`).join("")}
        <label>Önümüzdeki 12 ayda ihtiyaç duyacağım tutar (TL)</label><input id="pf-need" type="number" inputmode="decimal" value="${h(pf.need || "")}">
        <p><button id="pf-save">Kaydet</button></p></div>
      ${calcCard(status)}
      <div class="card"><h2>Yedek</h2><p class="small muted">Portföyünüzü başka bir cihaza taşımak veya yedeklemek için metni kopyalayın.</p>
        <textarea id="pf-json" rows="3">${h(JSON.stringify(pf))}</textarea><div class="row2"><button class="ghost" id="pf-copy">Kopyala</button><button class="ghost" id="pf-imp">Metinden geri yükle</button></div></div>`;
  }
  function calcCard(status) {
    const r = (status && status.settings_public && status.settings_public.risk) || { risk_per_trade_pct: 0.5, commission_pct: 0.15, slippage_pct: 0.1, max_position_pct: 25 };
    return `<div class="card"><h2>Pozisyon büyüklüğü hesaplayıcı</h2>
      <p class="small muted">Stop (zarar kes) seviyesine göre kaç lot alabileceğinizi hesaplar. Komisyon %${num(r.commission_pct, 2)} + kayma %${num(r.slippage_pct, 2)} (tek yön) dahildir.</p>
      <div class="row2"><div><label>İşlem sermayesi (TL)</label><input id="c-cap" type="number" inputmode="decimal"></div><div><label>İşlem başı risk (%)</label><input id="c-risk" type="number" step="0.1" value="${r.risk_per_trade_pct}"></div></div>
      <div class="row2"><div><label>Giriş fiyatı</label><input id="c-e" type="number" step="0.01" inputmode="decimal"></div><div><label>Stop fiyatı</label><input id="c-s" type="number" step="0.01" inputmode="decimal"></div></div>
      <div id="c-out" class="headline small" data-c="${r.commission_pct}" data-sl="${r.slippage_pct}" data-mp="${r.max_position_pct}"></div></div>`;
  }
  function bindPortfolio() {
    const pf = store.get("portfolio", { holdings: [], cash: {}, need: 0 });
    const $ = (id) => document.getElementById(id);
    if (!$("pf-add")) return;
    $("pf-add").onclick = () => {
      const t = ($("pf-t").value || "").trim().toUpperCase().replace(".IS", "");
      const q = parseFloat($("pf-q").value), c = parseFloat($("pf-c").value);
      if (!t || !(q > 0) || !(c > 0)) { alert("Kod, adet ve maliyet girin."); return; }
      pf.holdings.push({ ticker: t, qty: q, cost: c, cat: $("pf-k").value });
      store.set("portfolio", pf); route();
    };
    document.querySelectorAll("[data-del]").forEach((a) => a.onclick = (e) => { e.preventDefault(); pf.holdings.splice(+a.dataset.del, 1); store.set("portfolio", pf); route(); });
    $("pf-save").onclick = () => {
      pf.cash = {}; document.querySelectorAll("[data-cash]").forEach((i) => { if (i.value) pf.cash[i.dataset.cash] = parseFloat(i.value); });
      pf.need = parseFloat($("pf-need").value) || 0; store.set("portfolio", pf); route();
    };
    $("pf-copy").onclick = () => { $("pf-json").select(); try { navigator.clipboard.writeText($("pf-json").value); } catch (e) { document.execCommand("copy"); } };
    $("pf-imp").onclick = () => { try { const j = JSON.parse($("pf-json").value); if (!j.holdings) throw 0; store.set("portfolio", j); route(); } catch (e) { alert("Geçersiz yedek metni."); } };
    const calc = () => {
      const out = $("c-out"); const cap = parseFloat($("c-cap").value), rk = parseFloat($("c-risk").value), e = parseFloat($("c-e").value), s = parseFloat($("c-s").value);
      if (!(cap > 0 && rk > 0 && e > 0 && s > 0)) { out.textContent = ""; return; }
      if (s >= e) { out.textContent = "Stop, giriş fiyatının altında olmalı."; return; }
      const c = (parseFloat(out.dataset.c) + parseFloat(out.dataset.sl)) / 100;
      const rps = (e - s) + e * c + s * c;
      let sh = Math.floor(cap * rk / 100 / rps);
      const maxSh = Math.floor(cap * parseFloat(out.dataset.mp) / 100 / (e * (1 + c)));
      let note = "";
      if (sh > maxSh) { sh = maxSh; note = ` (sermayenin %${out.dataset.mp} sınırına göre küçültüldü)`; }
      out.textContent = sh > 0 ? `${sh} lot ≈ ${tl(sh * e)} · en fazla risk ≈ ${tl(sh * rps)} · stop mesafesi %${num((e - s) / e * 100, 1)}${note}` : "Bu stop mesafesi için sermaye yetersiz.";
    };
    ["c-cap", "c-risk", "c-e", "c-s"].forEach((id) => $(id).addEventListener("input", calc));
  }

  // ---------- diğer sayfalar ----------
  async function pageMore() {
    const status = await load("status.json");
    const repo = status && status.repo;
    const gh = repo ? `https://github.com/${repo}` : null;
    return `<div class="card"><a class="list-row" href="#/arsiv"><span>Rapor arşivi</span><span>›</span></a>
      <a class="list-row" href="#/haberler"><span>Haberler ve KAP başlıkları</span><span>›</span></a>
      <a class="list-row" href="#/piyasa"><span>Piyasa özeti (endeks, sektör, küresel)</span><span>›</span></a>
      <a class="list-row" href="#/simulasyon"><span>Simülasyon (kağıt üzerinde işlem) sonuçları</span><span>›</span></a>
      <a class="list-row" href="#/durum"><span>Veri kaynağı ve sistem durumu</span><span>›</span></a>
      <a class="list-row" href="#/sozluk"><span>Terimler sözlüğü</span><span>›</span></a>
      <a class="list-row" href="#/yardim"><span>Nasıl kullanılır?</span><span>›</span></a></div>
      ${gh ? `<div class="card"><h2>Yönetim (GitHub hesabı gerekir)</h2>
        <a class="list-row" href="${h(gh)}/edit/main/config/watchlist.txt" target="_blank" rel="noopener"><span>İzleme listesini düzenle</span><span>↗</span></a>
        <a class="list-row" href="${h(gh)}/actions/workflows/reports.yml" target="_blank" rel="noopener"><span>Raporu şimdi elle üret ("Run workflow")</span><span>↗</span></a>
        <a class="list-row" href="${h(gh)}/edit/main/config/settings.json" target="_blank" rel="noopener"><span>Risk ayarlarını düzenle</span><span>↗</span></a></div>` : ""}
      <div class="card"><label>Görünüm</label><select id="theme"><option value="">Telefon ayarına göre</option><option value="light">Açık</option><option value="dark">Koyu</option></select></div>`;
  }
  async function pageArchive() {
    const idx = await load("index.json", true);
    if (!idx) return `<div class="card">Arşiv yok.</div>`;
    const byDay = {};
    idx.reports.forEach((r) => (byDay[r.date] = byDay[r.date] || []).push(r));
    return Object.entries(byDay).slice(0, 60).map(([d, rs]) => `<div class="card"><h2>${h(rs[0].day_name || "")} ${h(d)}</h2>
      ${rs.map((r) => `<a class="list-row" href="#/rapor/${encodeURIComponent(r.date)}/${encodeURIComponent(r.slot)}"><span>${h(SLOT_NAMES[r.slot] || r.title)}<br><span class="small muted">${h(r.headline || "")}</span></span><span class="r small">${hm(r.generated_at)}${r.on_time ? "" : "<br>⚠"}</span></a>`).join("")}</div>`).join("");
  }
  async function pageNews() {
    const mk = await load("market.json");
    if (!mk || !mk.news) return `<div class="card">Haber verisi yok.</div>`;
    const cal = (mk.macro || []).map((e) => `<tr><td>${h(e.date)}</td><td>${h(e.time)}</td><td class="wrap">${h(e.event)}</td></tr>`).join("");
    return `<div class="warnbox">KAP otomatik erişime kapalı olduğu için başlıklar Google Haberler'den alınır (yalnızca başlık + bağlantı). Resmî metin için kap.org.tr'yi kontrol edin.</div>
      <div class="card"><h2>Başlıklar</h2>${mk.news.items.length ? mk.news.items.map(newsItem).join("") : "<p class='muted'>Başlık yok.</p>"}<p class="note">${dt(mk.generated_at)}</p></div>
      <div class="card"><h2>Ekonomik takvim</h2>${cal ? `<div class="tbl"><table><tbody>${cal}</tbody></table></div>` : "<p class='muted small'>Yakın tarihte kayıtlı olay yok.</p>"}</div>`;
  }
  async function pageMarket() {
    const mk = await load("market.json");
    if (!mk) return `<div class="card">Veri yok.</div>`;
    const ix = (mk.indices || []).map((x) => `<div class="card"><div class="sig-h"><h2>${h(x.name)}</h2><span class="${cls(x.chg)}">${pct(x.chg)}</span></div>
      <div class="headline">${num(x.price)}</div><div class="small muted">${dt(x.time)} · ${qb(x.quality)}</div>
      <div class="small">Eğilim: ${h(x.trend || "—")} — ${h(x.trend_explain || "")}</div>
      <div class="small">RSI ${num(x.rsi, 0)} · EMA20 ${num(x.ema20)} · EMA50 ${num(x.ema50)} · EMA200 ${num(x.ema200)}</div>
      <div class="small">Destekler: ${((x.sr || {}).supports || []).map((v) => num(v)).join(" / ") || "—"} · Dirençler: ${((x.sr || {}).resistances || []).map((v) => num(v)).join(" / ") || "—"}</div></div>`).join("");
    const tbl = (rows, title) => `<div class="card"><h2>${title}</h2><div class="tbl"><table><thead><tr><th>Ad</th><th>Son</th><th>Gün</th><th>20 gün</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${h(r.name)}</td><td>${num(r.price, r.price < 10 ? 4 : 2)}</td><td class="${cls(r.chg)}">${pct(r.chg)}</td><td class="${cls(r.ret20)}">${pct(r.ret20, 1)}</td></tr>`).join("")}</tbody></table></div></div>`;
    const b = mk.breadth || {};
    return `${ix}<div class="card small">Piyasa genişliği: ${b.adv || 0} yükselen · ${b.dec || 0} düşen · ${b.flat || 0} yatay (taranan ${b.total || 0} hisse)</div>
      ${tbl(mk.sectors || [], "Sektör endeksleri")}${tbl(mk.global || [], "Küresel piyasalar")}<p class="note">Güncelleme: ${dt(mk.generated_at)}</p>`;
  }
  async function pagePaper() {
    const p = await load("paper.json");
    if (!p) return `<div class="card">Simülasyon verisi yok.</div>`;
    const st = (p.stats || []).map((s) => `<div class="card"><h2>${s.book === "intraday" ? "Gün içi defter" : "Swing defter"}</h2>
      <div class="grid"><div><div class="l">Başlangıç</div><div class="v small">${tl(s.start_capital)}</div></div><div><div class="l">Güncel</div><div class="v small">${tl(s.equity)}</div></div>
      <div><div class="l">Toplam K/Z</div><div class="v ${cls(s.total_pnl)}">${tl(s.total_pnl)}</div></div><div><div class="l">İşlem</div><div class="v">${s.trades}</div></div>
      <div><div class="l">Kazanma oranı</div><div class="v">${s.win_rate == null ? "—" : "%" + num(s.win_rate, 0)}</div></div><div><div class="l">Maks. düşüş</div><div class="v">%${num(s.max_drawdown_pct, 1)}</div></div></div></div>`).join("");
    const rows = (p.closed || []).slice().reverse().map((t) => `<tr><td>${h(t.ticker)}</td><td>${t.book === "intraday" ? "Gün içi" : "Swing"}</td><td>${dt(t.entry_time)}</td><td>${num(t.entry)}</td><td>${h(t.exit_reason)}</td><td class="${cls(t.pnl)}">${num(t.pnl, 0)}</td><td>${num(t.r_multiple, 2)}</td></tr>`).join("");
    return `<div class="warnbox">${h(p.note || "SİMÜLASYON")}: Bu sonuçlar gerçek para ile yapılmış işlemler değildir ve gerçek portföyünüzle karıştırılmaz. Komisyon ve kayma dahildir.</div>${st}
      <div class="card"><h2>Kapanan işlemler</h2>${rows ? `<div class="tbl"><table><thead><tr><th>Hisse</th><th>Defter</th><th>Giriş</th><th>Fiyat</th><th>Çıkış</th><th>K/Z TL</th><th>R</th></tr></thead><tbody>${rows}</tbody></table></div>` : "<p class='muted small'>Henüz kapanan işlem yok.</p>"}</div>`;
  }
  async function pageStatus() {
    const s = await load("status.json", true);
    if (!s) return `<div class="card">Durum bilgisi yok.</div>`;
    const lr = s.last_run || {};
    const reps = Object.entries(s.reports || {}).map(([d, v]) => `<tr><td>${h(d)}</td>${["premarket", "opening", "midday", "close"].map((k) => { const e = v[k]; if (!e) return "<td>—</td>"; const ok = e.status === "ok"; return `<td class="${ok ? "up" : "down"}">${ok ? hm(e.generated_at) : h(e.status === "missed" ? "kaçırıldı" : e.status === "partial" ? "kısmi" : "hata")}</td>`; }).join("")}</tr>`).join("");
    const days = Object.entries(s.days || {}).map(([d, v]) => `<li>${h(d)}: ${h(v.note)}</li>`).join("");
    const log = (s.log || []).slice(0, 30).map((l) => `<tr><td>${dt(l.ts)}</td><td class="${l.status === "error" ? "down" : l.status === "warning" ? "q-bayat" : ""}">${h(l.status)}</td><td class="wrap">${h(l.message)}</td></tr>`).join("");
    return `<div class="card"><h2>Sistem durumu</h2><p class="small">Son çalışma: <b>${dt(lr.at)}</b> (${h(lr.trigger || "—")}) · ${num(lr.requests, 0)} veri isteği, ${num(lr.fetch_failures, 0)} başarısız</p>
      <p class="small">Site güncellemesi: ${dt(s.built_at)}</p>
      <p class="small muted">Raporlar GitHub Actions'ın ücretsiz zamanlayıcısıyla üretilir. GitHub tam dakika garantisi vermez; gecikmeler raporda gösterilir. Kaçırılan raporlar "kaçırıldı" olarak işaretlenir ve elle üretilebilir.</p></div>
      <div class="card"><h2>Son günlerin raporları</h2><div class="tbl"><table><thead><tr><th>Gün</th><th>09:45</th><th>10:15</th><th>14:00</th><th>18:15</th></tr></thead><tbody>${reps}</tbody></table></div>
      ${days ? `<h3>İşlem olmayan günler</h3><ul class="bl small">${days}</ul>` : ""}</div>
      <div class="card"><h2>Veri kaynakları</h2><ul class="bl small">
        <li><b>Yahoo Finance</b> (ücretsiz): BIST fiyatları yaklaşık 15 dk gecikmelidir, gerçek zamanlı değildir.</li>
        <li><b>TCMB</b> gösterge kurları: resmî, günde bir kez.</li>
        <li><b>Google Haberler RSS</b>: KAP'la ilgili haber başlıkları (KAP'ın kendisi değil).</li>
        <li><b>Mali tablolar</b>: Yahoo Finance yıllık veriler; eksik olabilir.</li></ul>
        <p class="small muted">${h(s.universe_note || "")}</p></div>
      <div class="card"><h2>Çalışma günlüğü</h2><div class="tbl"><table><tbody>${log}</tbody></table></div></div>`;
  }
  const GLOSSARY = [
    ["RSI", "0–100 arası momentum göstergesi. 70 üzeri 'aşırı alım' (kısa vadede pahalanmış), 30 altı 'aşırı satım' (kısa vadede çok düşmüş) kabul edilir."],
    ["MACD", "İki hareketli ortalamanın farkı. Histogram yükseliyorsa yukarı momentum güçleniyor demektir."],
    ["EMA 9/20/50/200", "Üssel hareketli ortalama: son günlere daha fazla ağırlık veren ortalama fiyat. Fiyat 200 günlüğün üzerindeyse uzun vadeli eğilim genelde yukarı kabul edilir."],
    ["VWAP", "Gün içi hacim ağırlıklı ortalama fiyat. Fiyat VWAP üzerindeyse o gün alanların ortalamada kârda olduğunu, alıcıların güçlü olduğunu gösterir."],
    ["ATR", "Ortalama gerçek aralık: hissenin günde ortalama ne kadar oynadığı. Stop mesafesini belirlemede kullanılır."],
    ["Bollinger Bantları", "Ortalamanın iki standart sapma üstü ve altı. Bant dışına çıkış olağandışı hareket işaretidir."],
    ["ADX", "Eğilimin gücü (yönü değil). 20–25 üzeri güçlü eğilim demektir."],
    ["Göreceli hacim", "Bugünkü hacmin normal hacme oranı. 2x = normalin iki katı işlem; ilgi arttığını gösterir."],
    ["Destek / Direnç", "Destek: düşüşte alıcıların çıkma eğiliminde olduğu fiyat. Direnç: yükselişte satıcıların çıkma eğiliminde olduğu fiyat."],
    ["Kırılım", "Fiyatın önemli bir direnci (ör. 20 günün zirvesi) yukarı geçmesi."],
    ["Stop-loss (zarar kes)", "Önceden belirlenen, fiyat buraya gelirse zararı sınırlamak için çıkılacak seviye."],
    ["Risk/getiri (R/R)", "Potansiyel kazancın, göze alınan zarara oranı. 2 = 1 TL riske karşı 2 TL potansiyel kazanç."],
    ["R çarpanı", "Bir işlemin sonucunun başlangıç riskine oranı. +2R = riskin iki katı kazanç."],
    ["Swing işlem", "Birkaç günden birkaç haftaya kadar tutulan işlem."],
    ["Kağıt üzerinde işlem (simülasyon)", "Gerçek para kullanmadan, stratejiyi test etmek için yapılan sanal işlem."],
    ["F/K", "Fiyat/Kazanç: şirketin piyasa değerinin yıllık net kârına oranı. Düşük F/K tek başına ucuzluk anlamına gelmez."],
    ["PD/DD", "Piyasa değeri / defter değeri. Özellikle bankalarda önemlidir."],
    ["FD/FAVÖK", "Firma değeri / faiz-amortisman-vergi öncesi kâr. Borcu da hesaba katan değerleme çarpanı."],
    ["FAVÖK (EBITDA)", "Faiz, amortisman ve vergi öncesi kâr: işletmenin ana faaliyetinden elde ettiği kâr."],
    ["ROE", "Özsermaye kârlılığı: şirketin ortaklarının parasıyla yılda yüzde kaç kâr ettiği. Türkiye'de enflasyonun üzerinde olması önemlidir."],
    ["ROIC", "Yatırılan sermaye getirisi: şirketin tüm sermayesini (borç dahil) ne kadar verimli kullandığı."],
    ["Serbest nakit akışı", "Şirketin yatırımlarını yaptıktan sonra elinde kalan nakit. Temettü ve borç ödemenin kaynağıdır."],
    ["Net borç", "Toplam finansal borç eksi nakit. Negatifse şirketin net nakdi vardır."],
    ["Enflasyon muhasebesi (TMS 29)", "Yüksek enflasyon nedeniyle 2023'ten itibaren mali tabloların enflasyona göre düzeltilmesi. Nominal büyüme rakamları yanıltıcı olabilir."],
    ["Reel büyüme", "Enflasyon etkisi çıkarıldıktan sonraki büyüme."],
    ["Gecikmeli veri", "Ücretsiz kaynaklarda BIST fiyatları yaklaşık 15 dakika geriden gelir. Gerçek fiyat o an farklı olabilir."],
  ];
  function pageGlossary() {
    return `<div class="card"><h2>Terimler sözlüğü</h2>${GLOSSARY.map(([k, v]) => `<details class="sec"><summary>${h(k)}</summary><div class="secbody small">${h(v)}</div></details>`).join("")}</div>`;
  }
  function pageHelp() {
    return `<div class="card"><h2>Nasıl kullanılır?</h2><ul class="bl small">
      <li>Her işlem günü dört rapor otomatik üretilir: <b>09:45</b> açılış öncesi, <b>10:15</b> açılış sonrası, <b>14:00</b> gün ortası, <b>18:15</b> kapanış (İstanbul saati). Bulut zamanlayıcısı bazen birkaç dakika (nadiren daha fazla) gecikebilir; gerçek üretim saati raporda yazar.</li>
      <li><b>Bugün</b> sekmesinde günün raporları arasında üstteki düğmelerle geçiş yapın.</li>
      <li>Her bilgi etiketlidir: <span class="kind kind-veri">Doğrulanmış veri</span>, <span class="kind kind-hesap">Hesaplanmış gösterge</span>, <span class="kind kind-yorum">Algoritmik yorum</span>, <span class="kind kind-senaryo">Olası senaryo</span>.</li>
      <li><b>Portföyüm</b> sekmesine girdiğiniz bilgiler yalnızca bu telefonda kalır.</li>
      <li>Ana ekrana eklemek için: iPhone'da Safari → Paylaş → <b>Ana Ekrana Ekle</b>. Android'de Chrome → ⋮ → <b>Ana ekrana ekle</b>.</li>
      <li>Bu sistem yatırım tavsiyesi vermez; gerçek emir göndermez. Simülasyon sonuçları gerçek getiri değildir.</li></ul></div>`;
  }

  // ---------- yönlendirme ----------
  async function route() {
    const parts = (location.hash.replace(/^#\/?/, "") || "").split("/").map(decodeURIComponent);
    const p = parts[0] || "";
    const tabOf = { "": "bugun", bugun: "bugun", rapor: "bugun", firsatlar: "firsatlar", hisseler: "hisseler", hisse: "hisseler", portfoy: "portfoy" };
    document.querySelectorAll(".tabbar a").forEach((a) => a.classList.toggle("on", a.dataset.tab === (tabOf[p] || "daha")));
    let html = "";
    try {
      if (p === "" || p === "bugun") html = await pageToday(parts[1]);
      else if (p === "rapor") html = renderReport(await load(`reports/${parts[1]}/${parts[2]}.json`));
      else if (p === "firsatlar") html = await pageOpps(parts[1]);
      else if (p === "hisseler") html = await pageStocks();
      else if (p === "hisse") html = await pageStock((parts[1] || "").toUpperCase());
      else if (p === "portfoy") html = await pagePortfolio();
      else if (p === "arsiv") html = await pageArchive();
      else if (p === "haberler") html = await pageNews();
      else if (p === "piyasa") html = await pageMarket();
      else if (p === "simulasyon") html = await pagePaper();
      else if (p === "durum") html = await pageStatus();
      else if (p === "sozluk") html = pageGlossary();
      else if (p === "yardim") html = pageHelp();
      else html = await pageMore();
    } catch (e) {
      html = `<div class="warnbox">Sayfa yüklenemedi: ${h(e.message || e)}</div>`;
    }
    app.innerHTML = html;
    const th = document.getElementById("theme");
    if (th) { th.value = store.get("theme", ""); th.onchange = () => { store.set("theme", th.value); applyTheme(); }; }
    if (!location.hash.startsWith("#/hisse/")) window.scrollTo(0, 0);
  }
  function applyTheme() {
    const t = store.get("theme", "");
    if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
  }
  async function topStatus() {
    const s = await load("status.json");
    const el = document.getElementById("top-status");
    if (s && el) el.textContent = "Güncelleme " + dt(s.built_at);
  }
  applyTheme();
  window.addEventListener("hashchange", route);
  route();
  topStatus();
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();
