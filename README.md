# ALPHA X ACADEMY — HTML / CSS / JavaScript / Python / SQLite

Runs with Python 3.8+ only (standard library). No npm, pip, Docker or database server.

## Run (Windows PowerShell + VS Code)
1. Install Python from python.org (tick "Add python.exe to PATH"). Check: `python --version`
2. VS Code → File → Open Folder → this folder → Terminal → New Terminal.
3. Create the administrator (prompts for a password of 12+ characters, hidden):
   `python create_admin.py`
4. Start the server: `python server.py`
5. Website: http://127.0.0.1:8000 — Admin: http://127.0.0.1:8000/admin/login
The database file `alpha_x_academy.db` and all tables/starter courses are created automatically on first run. Stop with Ctrl+C.
To reset a forgotten password, run `python create_admin.py` again with the same username and answer `y`.

## What is real
Enquiries, page views, courses and content are stored in SQLite. Dashboard numbers are queries on those tables (zero until visitors arrive). Phone, email, fees, results and faculty are NOT invented: add phone/email in Admin → Website content (blank = hidden).

## Analytics definitions
Page view = one load of the home page recorded by the server. Unique visitor (approximate) = distinct random cookie id (`axv`, 180 days, no IP stored). Cleared cookies, private mode or other devices change the count; it is not a count of real people. Dates use the server computer's local time.

## Security notes
PBKDF2-SHA256 (310k iterations, random salt); parameterized SQL; HttpOnly + SameSite=Strict admin cookie (8-hour expiry, invalidated on logout); CSRF token on all admin changes; Origin check; login limited to 5 failures / 15 min per IP; enquiries limited to 5 / 10 min per IP; CSP with no inline scripts; output escaped. Limitations: rate limits are in memory (reset on restart); no HTTPS built in — for a public server put it behind an HTTPS proxy and set `AX_SECURE_COOKIES=1`; back up `alpha_x_academy.db` regularly; this is not a hardened production deployment. Env options: `AX_HOST`, `AX_PORT`, `AX_DB`.

## Test checklist
- [ ] Home page loads; nav links scroll; mobile menu works (narrow the window)
- [ ] Classes 11/12 show "Science Stream Only"; no Arts/Commerce anywhere
- [ ] Submit blank form → field errors; valid form → success; row appears in admin; same submission twice within 10 min → one row
- [ ] `/admin` while logged out redirects to login; wrong password rejected; 6th wrong attempt blocked
- [ ] Dashboard: enquiry/page-view counts match activity; status change persists after refresh; search/filter work; delete asks confirmation
- [ ] Add, edit, deactivate a course → public site and enquiry dropdown update after refresh
- [ ] Edit announcement/address/hours → public site updates; logout then Back button cannot use dashboard
- [ ] Enable "reduce motion" in your OS → animations stop
