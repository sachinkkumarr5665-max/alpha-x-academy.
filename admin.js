(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const page = document.body.dataset.page;
  let csrf = "";
  const say = (t, bad) => { const m = $("#msg"); m.textContent = t; m.className = bad ? "err" : "ok"; };
  async function api(p, m = "GET", b) {
    const o = { method: m, headers: {} };
    if (m !== "GET") o.headers["X-CSRF-Token"] = csrf;
    if (b) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(b); }
    const r = await fetch("/api/admin" + p, o);
    if (r.status === 401 && page === "dash") { location.href = "/admin/login"; throw new Error("Session expired"); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(d.error || "Request failed"), { details: d.details });
    return d;
  }
  const fail = e => say(e.message + (e.details ? " " + Object.values(e.details).join(" ") : ""), true);

  if (page === "login") {
    $("#login-form").addEventListener("submit", async e => {
      e.preventDefault();
      try { await api("/login", "POST", Object.fromEntries(new FormData(e.target))); location.href = "/admin"; } catch (x) { fail(x); }
    });
    return;
  }

  const FIELDS = [["announcement", "Homepage announcement (leave blank to hide)"], ["hero_title", "Hero title"], ["hero_subtitle", "Hero subtitle"],
    ["about_text", "About text"], ["address", "Address"], ["opening_hours", "Opening hours"], ["phone", "Phone (blank = hidden)"], ["email", "Email (blank = hidden)"]];

  async function stats() {
    const s = await api("/stats");
    const cards = [["Total enquiries", s.total_enquiries], ["Today's enquiries", s.today_enquiries], ["Total page views", s.total_views],
      ["Today's page views", s.today_views], ["Approx. unique visitors", s.unique_visitors], ["Approx. unique today", s.unique_today]];
    $("#stats").innerHTML = cards.map(([l, v]) => `<div class="card"><small>${esc(l)}</small><strong>${v}</strong></div>`).join("");
    const max = Math.max(1, ...s.by_day.map(d => d.views));
    $("#views").innerHTML = "<tr><th>Date</th><th>Page views</th><th>Approx. visitors</th><th></th></tr>" +
      s.by_day.map(d => `<tr><td>${esc(d.day)}</td><td>${d.views}</td><td>${d.visitors}</td><td><span class="bar" data-w="${Math.round(d.views / max * 100)}"></span></td></tr>`).join("");
    document.querySelectorAll(".bar").forEach(b => { b.style.width = b.dataset.w + "%"; });
  }
  const STAT = ["New", "Contacted", "Admitted", "Closed"];
  async function enquiries() {
    const rows = await api(`/enquiries?q=${encodeURIComponent($("#q").value)}&status=${encodeURIComponent($("#fstatus").value)}`);
    $("#enq").innerHTML = "<tr><th>Date</th><th>Student</th><th>Guardian</th><th>Class/Exam</th><th>Phone</th><th>Email</th><th>Message</th><th>Status</th><th></th></tr>" +
      (rows.map(r => `<tr><td>${esc(r.created_at.replace("T", " "))}</td><td>${esc(r.student_name)}</td><td>${esc(r.guardian_name)}</td><td>${esc(r.class_or_exam)}</td><td>${esc(r.phone)}</td><td>${esc(r.email)}</td><td>${esc(r.message)}</td>` +
        `<td><select class="st" data-id="${r.id}" aria-label="Status">${STAT.map(s => `<option${s === r.status ? " selected" : ""}>${s}</option>`).join("")}</select></td>` +
        `<td><button class="btn ghost small del" data-id="${r.id}">Delete</button></td></tr>`).join("") || '<tr><td colspan="9">No enquiries found.</td></tr>');
  }
  let courses = [];
  async function loadCourses() {
    courses = await api("/courses");
    $("#courses").innerHTML = "<tr><th>Title</th><th>Category</th><th>Class/Exam</th><th>Status</th><th></th></tr>" +
      courses.map(c => `<tr><td>${esc(c.title)}</td><td>${esc(c.category)}</td><td>${esc(c.class_or_exam)}</td><td>${c.is_active ? "Active" : "Inactive"}</td>` +
        `<td><button class="btn ghost small edit" data-id="${c.id}">Edit</button> <button class="btn ghost small tog" data-id="${c.id}">${c.is_active ? "Deactivate" : "Activate"}</button></td></tr>`).join("");
  }
  async function content() {
    const c = await api("/content");
    $("#content-form").innerHTML = FIELDS.map(([k, l]) => `<label>${esc(l)}<textarea name="${k}" rows="2">${esc(c[k])}</textarea></label>`).join("") + '<button class="btn" type="submit">Save content</button>';
  }

  document.addEventListener("change", async e => {
    if (e.target.classList.contains("st")) try { await api("/enquiries/" + e.target.dataset.id, "PATCH", { status: e.target.value }); say("Status updated."); } catch (x) { fail(x); }
    if (e.target.id === "fstatus") enquiries().catch(fail);
  });
  document.addEventListener("click", async e => {
    const t = e.target, id = t.dataset && t.dataset.id;
    try {
      if (t.classList.contains("del") && confirm("Delete this enquiry permanently?")) { await api("/enquiries/" + id, "DELETE"); say("Enquiry deleted."); await Promise.all([enquiries(), stats()]); }
      if (t.classList.contains("tog")) { const c = courses.find(x => x.id == id); await api("/courses/" + id, "PATCH", { is_active: !c.is_active }); say("Course updated."); loadCourses(); }
      if (t.classList.contains("edit")) { const c = courses.find(x => x.id == id), f = $("#course-form"); for (const k of ["id", "title", "category", "class_or_exam", "description"]) f.elements[k].value = c[k]; f.scrollIntoView({ behavior: "smooth" }); }
    } catch (x) { fail(x); }
  });
  let timer;
  $("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => enquiries().catch(fail), 300); });
  $("#course-form").addEventListener("submit", async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target)), id = d.id; delete d.id;
    try { await api(id ? "/courses/" + id : "/courses", id ? "PATCH" : "POST", d); e.target.reset(); e.target.elements.id.value = ""; say("Course saved."); loadCourses(); } catch (x) { fail(x); }
  });
  $("#course-reset").addEventListener("click", () => { $("#course-form").elements.id.value = ""; });
  $("#content-form").addEventListener("submit", async e => {
    e.preventDefault();
    try { await api("/content", "PUT", Object.fromEntries(new FormData(e.target))); say("Website content saved."); } catch (x) { fail(x); }
  });
  $("#logout").addEventListener("click", async () => { try { await api("/logout", "POST"); } finally { location.href = "/admin/login"; } });

  api("/me").then(me => { csrf = me.csrf; $("#who").textContent = me.username; return Promise.all([stats(), enquiries(), loadCourses(), content()]); }).catch(fail);
})();
