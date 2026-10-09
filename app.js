(() => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const j = async (u, o) => {
    const r = await fetch(u, o), d = r.status === 204 ? {} : await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(d.error || "Request failed"), { details: d.details });
    return d;
  };

  const btn = $("#menu-btn"), nav = $("#nav");
  btn.addEventListener("click", () => btn.setAttribute("aria-expanded", nav.classList.toggle("open")));
  nav.addEventListener("click", e => { if (e.target.tagName === "A") { nav.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); } });

  const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: 0.12 }) : null;
  const reveal = () => $$(".reveal:not(.in)").forEach(el => io ? io.observe(el) : el.classList.add("in"));
  reveal();

  const card = c => `<article class="card reveal"><h3>${esc(c.title)}</h3>${/science/i.test(c.title) ? '<span class="badge">Science Stream Only</span>' : ""}<p>${esc(c.description)}</p></article>`;
  async function load() {
    try {
      const [courses, content] = await Promise.all([j("/api/courses"), j("/api/content")]);
      const school = courses.filter(c => c.category === "school"), exams = courses.filter(c => c.category === "competitive");
      $("#school-list").innerHTML = school.map(card).join("") || "<p>No courses available right now.</p>";
      $("#exam-list").innerHTML = exams.map(card).join("") || "<p>No courses available right now.</p>";
      const opt = list => list.map(c => `<option value="${esc(c.title)}">${esc(c.title)}</option>`).join("");
      $("#class-select").innerHTML = `<option value="">Select…</option><optgroup label="School tuition">${opt(school)}</optgroup><optgroup label="Competitive exams">${opt(exams)}</optgroup>`;
      $$("[data-content]").forEach(el => { if (content[el.dataset.content]) el.textContent = content[el.dataset.content]; });
      $$("[data-show]").forEach(el => { el.hidden = !content[el.dataset.show]; });
      $("#announce").hidden = !content.announcement;
      reveal();
    } catch { $("#school-list").innerHTML = '<p class="err" role="alert">Courses could not be loaded. Please refresh the page.</p>'; }
  }
  load();

  const form = $("#enq-form"), msg = $("#enq-msg"), sbtn = $("#enq-btn");
  let busy = false;
  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (busy) return;
    $$("[data-err]", form).forEach(s => s.textContent = "");
    const d = Object.fromEntries(new FormData(form)), v = {};
    if (d.student_name.trim().length < 2) v.student_name = "Enter the student's name.";
    if (d.guardian_name.trim().length < 2) v.guardian_name = "Enter the parent or guardian's name.";
    if (!d.class_or_exam) v.class_or_exam = "Please choose a class or exam.";
    if (!/^\+?\d{10,13}$/.test(d.phone.replace(/[\s\-()]/g, ""))) v.phone = "Enter a valid phone number.";
    if (d.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) v.email = "Enter a valid email or leave it blank.";
    const show = x => Object.entries(x).forEach(([k, t]) => { const s = $(`[data-err="${k}"]`, form); if (s) s.textContent = t; });
    if (Object.keys(v).length) { show(v); msg.className = "err"; msg.textContent = "Please correct the highlighted fields."; return; }
    busy = true; sbtn.disabled = true; msg.className = ""; msg.textContent = "Sending…";
    try {
      await j("/api/enquiries", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
      form.reset(); msg.className = "ok"; msg.textContent = "Thank you! Your enquiry has been saved. The academy will contact you.";
    } catch (x) { show(x.details || {}); msg.className = "err"; msg.textContent = x.message; }
    finally { busy = false; sbtn.disabled = false; }
  });

  fetch("/api/pageview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: location.pathname }), keepalive: true }).catch(() => {});
})();
