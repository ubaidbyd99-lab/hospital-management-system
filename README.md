# LifeLine General Hospital — Hospital Management System

A complete Flask + Oracle Database XE 11g project for a Database Systems (DBS) course. Patients, doctors, appointments, bills, and the admin login are stored in Oracle. The website is not a static demo.

Hospital name in the app: **LifeLine General Hospital**.

## What this project includes

- Professional login page and responsive hospital dashboard
- Patient, doctor, appointment, and billing CRUD
- Unique IDs from Oracle sequences
- Duplicate appointment prevention for the same doctor and time
- Revenue totals from paid / partial bills
- Printable bill receipt
- Hashed admin password and session protection
- `hospital.sql` for Oracle XE 11g
- University documentation in `docs/PROJECT_DOCUMENTATION.md`

## 1. Install and verify Python (Windows)

1. Install Python 3.10 or later from [python.org](https://www.python.org/downloads/). During setup, tick **Add python.exe to PATH**.
2. Open **Command Prompt** or **PowerShell**.
3. Check the version:

```bat
python --version
```

You should see a version number, for example `Python 3.12.x`. If the command fails, reopen the terminal after installation.

## 2. Verify that Oracle Database is running

This project needs **Oracle Database XE 11g** (or another 11g database your lab provides). It does **not** use SQLite or MySQL.

1. Confirm the Oracle service is running. On many Windows PCs the service name is `OracleServiceXE`.
2. Open **SQL*Plus** or **SQL Developer** and connect as `SYSTEM` to prove the database is up.
3. Default XE 11g settings are usually:

- Host: `localhost`
- Port: `1521`
- SID: `XE`

If your teacher gave different values, use those in `.env`.

### Instant Client (required for Python + 11g)

`oracledb` in **thin mode cannot talk to Oracle 11g**. You must install Oracle Instant Client (thick mode).

1. Download Instant Client (Basic package, 64-bit) from Oracle’s Instant Client page.
2. Unzip it to a folder such as `C:\oracle\instantclient_21_13`.
3. Put that folder path in `.env` as `ORACLE_CLIENT_LIB`.
4. Optional but helpful: add the same folder to the Windows **PATH**.

## 3. Open the project folder in VS Code

1. Start **Visual Studio Code**.
2. Choose **File → Open Folder**.
3. Select:

```text
C:\Users\ubaid\hospital-management-system
```

4. Open the integrated terminal: **Terminal → New Terminal**. Run the commands below in that terminal so you stay inside the project folder.

## 4. Create and activate a Python virtual environment

In the VS Code terminal:

```bat
cd C:\Users\ubaid\hospital-management-system
python -m venv .venv
.venv\Scripts\activate
```

When it works, the prompt starts with `(.venv)`.

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.venv\Scripts\activate
```

## 5. Install the required dependencies

With `.venv` active:

```bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Configure the Oracle connection securely

1. In the project folder, copy `.env.example` to `.env`.

```bat
copy .env.example .env
```

2. Open `.env` in VS Code and set your real values. Example:

```env
FLASK_SECRET_KEY=any-long-random-sentence-you-choose
ORACLE_USER=hms_app
ORACLE_PASSWORD=the-password-you-set-in-sql
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SID=XE
ORACLE_CLIENT_LIB=C:\oracle\instantclient_21_13
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=Admin@123
```

Do **not** put the database password in HTML or JavaScript. Only `.env` and the Flask server read it.

## 7. Run `hospital.sql`

### Step A — create a dedicated app user (as SYSTEM)

Open SQL*Plus as SYSTEM, or SQL Developer connected as SYSTEM, then run:

```sql
CREATE USER hms_app IDENTIFIED BY hms_app_password
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION TO hms_app;
GRANT CREATE TABLE TO hms_app;
GRANT CREATE SEQUENCE TO hms_app;
GRANT CREATE TRIGGER TO hms_app;
GRANT CREATE VIEW TO hms_app;
```

Change `hms_app_password` to a password you will also put in `.env`.

SQL*Plus example (run this in Command Prompt, not inside Python):

```bat
sqlplus SYSTEM/your_system_password@XE
```

Then paste the `CREATE USER` / `GRANT` statements.

### Step B — create tables (as HMS_APP)

Connect as `hms_app` and run the rest of `hospital.sql` (Section B).

SQL*Plus from the project folder:

```bat
cd C:\Users\ubaid\hospital-management-system
sqlplus hms_app/hms_app_password@XE @hospital.sql
```

If Section A comments are still in the file, that is fine: they are comments. Section B creates sequences, tables, indexes, and triggers.

In **SQL Developer**: open `hospital.sql`, choose the `HMS_APP` connection, and run the script (F5).

The app user can create objects in its own schema. It should **not** be given DBA or SYSDBA for this project.

## 8. Start the Flask application

In VS Code, with `.venv` active:

```bat
cd C:\Users\ubaid\hospital-management-system
python app.py
```

Leave this window open. You should see Flask listening on port 5000.

If Oracle is down, the login page still opens, but saving data shows a clear connection error instead of crashing silently.

## 9. Open the website in a browser

Visit:

```text
http://127.0.0.1:5000
```

First-run admin account (unless you changed `.env`):

- Username: `admin`
- Password: `Admin@123`

The password is stored as a hash in the `USERS` table, not as plain text.

## 10. Test the main flows

Use this order so foreign keys succeed:

1. **Add a patient** → Patients → Add patient. Confirm the new ID appears in the table after refresh.
2. **Add a doctor** → Doctors → Add doctor. Open **Appointments** on that doctor (empty at first).
3. **Book an appointment** → choose the patient and doctor, date, and time. Try booking the same doctor at the same time again; the app should refuse it.
4. **Update records** → edit the patient phone or doctor fee and save.
5. **Generate a bill** → from Billing, or click **Bill** on an appointment. Enter extra charges and a paid amount. Open **Print** and use the browser print dialog.
6. Return to the dashboard. Totals should match Oracle, not hardcoded sample numbers.
7. Stop Flask (`Ctrl+C`) and start it again. The same rows should still be there.

### Extra checks

- Search patients by ID and by name.
- Cancel an appointment, then book that doctor’s slot again.
- Delete should ask for confirmation. Patients with appointments/bills cannot be deleted until those rows are removed.

## Project structure

```text
hospital-management-system/
  app.py
  db.py
  config.py
  validators.py
  hospital.sql
  requirements.txt
  .env.example
  README.md
  templates/
  static/css/style.css
  static/js/app.js
  static/img/logo.svg
  docs/PROJECT_DOCUMENTATION.md
```

## Common problems

| Problem | What to try |
| --- | --- |
| `Oracle Instant Client is required` | Install Instant Client and set `ORACLE_CLIENT_LIB`. |
| `DPI-1047` / cannot load client | 64-bit Python needs 64-bit Instant Client. Add the folder to PATH. |
| `ORA-01017 invalid username/password` | Check `ORACLE_USER` / `ORACLE_PASSWORD`. Connect with SQL*Plus first. |
| `ORA-12541` / `ORA-12505` | Listener not running, or SID is not `XE`. |
| `ORA-00942 table or view does not exist` | You ran Flask as `hms_app` but created tables as SYSTEM. Recreate objects as `hms_app`. |
| Login fails after SQL ran | Start the app once while Oracle is up so it can insert the hashed admin user. |
| `pip` / `python` not found | Reinstall Python with **Add to PATH**, then open a new VS Code terminal. |

## Git (optional)

Git was not required to run the app. If you install Git later:

```bat
cd C:\Users\ubaid\hospital-management-system
git init
git add .
git commit -m "Initial Hospital Management System for DBS"
```

Never commit the real `.env` file.

## Documentation for the report / viva

Open `docs/PROJECT_DOCUMENTATION.md` for the introduction, ER diagram, schema, sample SQL, testing checklist, and viva questions.
