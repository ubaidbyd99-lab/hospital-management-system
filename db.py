"""Oracle Database helpers for LifeLine General Hospital.

Oracle XE 11g is not supported by python-oracledb thin mode, so this module
initializes Instant Client (thick mode) when ORACLE_CLIENT_LIB is set.
All SQL uses bind variables.
"""

import os
from contextlib import contextmanager
from datetime import datetime, date

import oracledb
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

_client_ready = False
_client_error = None


class DatabaseUnavailable(Exception):
    """Raised when Oracle cannot be reached or thick mode is not configured."""


def _client_dir_usable(path):
    return bool(path and os.path.isdir(path) and os.path.isfile(os.path.join(path, "oci.dll")))


def find_oracle_client_lib():
    """Locate a directory that contains oci.dll, even when .env is stale."""
    configured = (Config.ORACLE_CLIENT_LIB or "").strip()
    if _client_dir_usable(configured):
        return configured

    candidates = []
    path_sources = [os.environ.get("PATH") or ""]
    # User/machine PATH may have been updated by an installer after this
    # process started, so consult the registry as well.
    try:
        import winreg

        for hive, subkey in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
                    path_sources.append(value)
            except FileNotFoundError:
                pass
    except Exception:
        pass

    for source in path_sources:
        for entry in str(source).split(os.pathsep):
            entry = entry.strip().strip('"')
            if _client_dir_usable(entry):
                candidates.append(entry)

    # Fall back to a shallow search of common Oracle installation roots.
    roots = [
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Microsoft\WinGet\Packages"),
        "C:\\oracle",
        "C:\\app",
        r"C:\Program Files\Oracle",
        r"C:\Program Files (x86)\Oracle",
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for current, dirnames, filenames in os.walk(root):
            if "oci.dll" in filenames:
                candidates.append(current)
                # Stop descending once a client directory has been found.
                dirnames[:] = []

    for candidate in candidates:
        if _client_dir_usable(candidate):
            return candidate
    return None


def init_oracle_client():
    global _client_ready, _client_error
    if _client_ready:
        return
    lib_dir = (Config.ORACLE_CLIENT_LIB or "").strip()
    if not _client_dir_usable(lib_dir):
        lib_dir = find_oracle_client_lib()
    try:
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
        else:
            # Still try default search path (PATH / ORACLE_HOME).
            oracledb.init_oracle_client()
        _client_ready = True
        _client_error = None
    except Exception as exc:
        _client_error = str(exc)
        # Thick mode may already be initialized in this process.
        if "already been initialized" in str(exc).lower():
            _client_ready = True
            _client_error = None
            return
        raise DatabaseUnavailable(
            "Oracle Instant Client is required for Oracle XE 11g. "
            "Install Instant Client, then set ORACLE_CLIENT_LIB in .env. "
            f"Details: {exc}"
        ) from exc


def _dsn():
    if Config.ORACLE_SERVICE:
        return oracledb.makedsn(
            Config.ORACLE_HOST, Config.ORACLE_PORT, service_name=Config.ORACLE_SERVICE
        )
    return oracledb.makedsn(Config.ORACLE_HOST, Config.ORACLE_PORT, sid=Config.ORACLE_SID)


def _row_to_dict(cursor, row):
    if row is None:
        return None
    columns = [col[0].lower() for col in cursor.description]
    data = dict(zip(columns, row))
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value
        elif isinstance(value, date) and not isinstance(value, datetime):
            data[key] = datetime.combine(value, datetime.min.time())
    return data


def _rows_to_dicts(cursor, rows):
    return [_row_to_dict(cursor, row) for row in rows]


@contextmanager
def get_connection():
    if not Config.ORACLE_PASSWORD:
        raise DatabaseUnavailable(
            "ORACLE_PASSWORD is missing. Copy .env.example to .env and set the HMS_APP password."
        )
    init_oracle_client()
    try:
        conn = oracledb.connect(
            user=Config.ORACLE_USER,
            password=Config.ORACLE_PASSWORD,
            dsn=_dsn(),
        )
    except Exception as exc:
        raise DatabaseUnavailable(
            "Could not connect to Oracle Database. Confirm the listener is running, "
            "the HMS_APP user exists, and .env has the correct host, SID, and password. "
            f"Details: {exc}"
        ) from exc
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql, params=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        return _rows_to_dicts(cursor, cursor.fetchall())


def query_one(sql, params=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        return _row_to_dict(cursor, cursor.fetchone())


def execute(sql, params=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        return cursor.rowcount


def table_count(table_name):
    allowed = {"patients", "doctors", "appointments", "bills", "users"}
    key = table_name.lower()
    if key not in allowed:
        raise ValueError("Invalid table name")
    row = query_one(f"SELECT COUNT(*) AS total FROM {key}")
    return int(row["total"]) if row else 0


def seed_admin_if_needed():
    count = table_count("users")
    if count > 0:
        return False
    password_hash = generate_password_hash(Config.DEFAULT_ADMIN_PASSWORD)
    execute(
        """
        INSERT INTO users (username, password_hash, full_name, role)
        VALUES (:username, :password_hash, :full_name, 'Admin')
        """,
        {
            "username": Config.DEFAULT_ADMIN_USERNAME.strip().lower(),
            "password_hash": password_hash,
            "full_name": Config.DEFAULT_ADMIN_FULL_NAME,
        },
    )
    return True


def get_user_by_username(username):
    return query_one(
        "SELECT user_id, username, password_hash, full_name, role FROM users WHERE LOWER(username) = :username",
        {"username": username.strip().lower()},
    )


def verify_user(username, password):
    user = get_user_by_username(username)
    if not user:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return user


def _returning_id(var):
    value = var.getvalue()
    if isinstance(value, (list, tuple)):
        value = value[0]
    return int(value)


def dashboard_stats_xe11():
    stats = query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM patients) AS total_patients,
            (SELECT COUNT(*) FROM doctors) AS total_doctors,
            (SELECT COUNT(*) FROM appointments) AS total_appointments,
            (SELECT NVL(SUM(paid_amount), 0) FROM bills
              WHERE payment_status IN ('Paid', 'Partial')) AS total_revenue
        FROM dual
        """
    )
    recent_appointments = query_all(
        """
        SELECT * FROM (
            SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.status,
                   p.full_name AS patient_name, d.full_name AS doctor_name
            FROM appointments a
            JOIN patients p ON p.patient_id = a.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
            ORDER BY a.created_on DESC, a.appointment_id DESC
        ) WHERE ROWNUM <= 5
        """
    )
    recent_patients = query_all(
        """
        SELECT * FROM (
            SELECT patient_id, full_name, age, gender, phone, disease, registration_date
            FROM patients
            ORDER BY registration_date DESC, patient_id DESC
        ) WHERE ROWNUM <= 5
        """
    )
    return stats, recent_appointments, recent_patients


def list_patients(search=""):
    search = (search or "").strip()
    if not search:
        return query_all(
            """
            SELECT patient_id, full_name, age, gender, phone, address, disease, registration_date
            FROM patients
            ORDER BY patient_id DESC
            """
        )
    like = f"%{search.upper()}%"
    return query_all(
        """
        SELECT patient_id, full_name, age, gender, phone, address, disease, registration_date
        FROM patients
        WHERE TO_CHAR(patient_id) = :exact_id
           OR UPPER(full_name) LIKE :name_like
           OR phone LIKE :phone_like
        ORDER BY patient_id DESC
        """,
        {"exact_id": search, "name_like": like, "phone_like": f"%{search}%"},
    )


def get_patient(patient_id):
    return query_one(
        """
        SELECT patient_id, full_name, age, gender, phone, address, disease, registration_date
        FROM patients WHERE patient_id = :patient_id
        """,
        {"patient_id": patient_id},
    )


def create_patient(data):
    with get_connection() as conn:
        cursor = conn.cursor()
        new_id = cursor.var(oracledb.NUMBER)
        cursor.execute(
            """
            INSERT INTO patients (full_name, age, gender, phone, address, disease)
            VALUES (:full_name, :age, :gender, :phone, :address, :disease)
            RETURNING patient_id INTO :new_id
            """,
            {
                "full_name": data["full_name"],
                "age": data["age"],
                "gender": data["gender"],
                "phone": data["phone"],
                "address": data.get("address"),
                "disease": data.get("disease"),
                "new_id": new_id,
            },
        )
        return _returning_id(new_id)


def update_patient(patient_id, data):
    return execute(
        """
        UPDATE patients
        SET full_name = :full_name,
            age = :age,
            gender = :gender,
            phone = :phone,
            address = :address,
            disease = :disease
        WHERE patient_id = :patient_id
        """,
        {
            "full_name": data["full_name"],
            "age": data["age"],
            "gender": data["gender"],
            "phone": data["phone"],
            "address": data.get("address"),
            "disease": data.get("disease"),
            "patient_id": patient_id,
        },
    )


def patient_has_links(patient_id):
    row = query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM appointments WHERE patient_id = :id) AS appt_count,
            (SELECT COUNT(*) FROM bills WHERE patient_id = :id2) AS bill_count
        FROM dual
        """,
        {"id": patient_id, "id2": patient_id},
    )
    return int(row["appt_count"] or 0), int(row["bill_count"] or 0)


def delete_patient(patient_id):
    return execute("DELETE FROM patients WHERE patient_id = :patient_id", {"patient_id": patient_id})


def list_doctors(search=""):
    search = (search or "").strip()
    if not search:
        return query_all(
            """
            SELECT doctor_id, full_name, specialization, phone, consultation_fee
            FROM doctors
            ORDER BY doctor_id DESC
            """
        )
    like = f"%{search.upper()}%"
    return query_all(
        """
        SELECT doctor_id, full_name, specialization, phone, consultation_fee
        FROM doctors
        WHERE TO_CHAR(doctor_id) = :exact_id
           OR UPPER(full_name) LIKE :name_like
           OR UPPER(specialization) LIKE :spec_like
        ORDER BY doctor_id DESC
        """,
        {"exact_id": search, "name_like": like, "spec_like": like},
    )


def get_doctor(doctor_id):
    return query_one(
        """
        SELECT doctor_id, full_name, specialization, phone, consultation_fee
        FROM doctors WHERE doctor_id = :doctor_id
        """,
        {"doctor_id": doctor_id},
    )


def create_doctor(data):
    with get_connection() as conn:
        cursor = conn.cursor()
        new_id = cursor.var(oracledb.NUMBER)
        cursor.execute(
            """
            INSERT INTO doctors (full_name, specialization, phone, consultation_fee)
            VALUES (:full_name, :specialization, :phone, :consultation_fee)
            RETURNING doctor_id INTO :new_id
            """,
            {
                "full_name": data["full_name"],
                "specialization": data["specialization"],
                "phone": data["phone"],
                "consultation_fee": data["consultation_fee"],
                "new_id": new_id,
            },
        )
        return _returning_id(new_id)


def update_doctor(doctor_id, data):
    return execute(
        """
        UPDATE doctors
        SET full_name = :full_name,
            specialization = :specialization,
            phone = :phone,
            consultation_fee = :consultation_fee
        WHERE doctor_id = :doctor_id
        """,
        {
            "full_name": data["full_name"],
            "specialization": data["specialization"],
            "phone": data["phone"],
            "consultation_fee": data["consultation_fee"],
            "doctor_id": doctor_id,
        },
    )


def doctor_has_appointments(doctor_id):
    row = query_one(
        "SELECT COUNT(*) AS total FROM appointments WHERE doctor_id = :doctor_id",
        {"doctor_id": doctor_id},
    )
    return int(row["total"] or 0)


def delete_doctor(doctor_id):
    return execute("DELETE FROM doctors WHERE doctor_id = :doctor_id", {"doctor_id": doctor_id})


def doctor_appointments(doctor_id):
    return query_all(
        """
        SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.status, a.notes,
               p.patient_id, p.full_name AS patient_name, p.phone AS patient_phone
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        WHERE a.doctor_id = :doctor_id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """,
        {"doctor_id": doctor_id},
    )


def list_appointments(search=""):
    search = (search or "").strip()
    sql = """
        SELECT a.appointment_id, a.patient_id, a.doctor_id, a.appointment_date,
               a.appointment_time, a.status, a.notes,
               p.full_name AS patient_name, d.full_name AS doctor_name
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        JOIN doctors d ON d.doctor_id = a.doctor_id
    """
    if search:
        like = f"%{search.upper()}%"
        sql += """
        WHERE TO_CHAR(a.appointment_id) = :exact_id
           OR UPPER(p.full_name) LIKE :like_val
           OR UPPER(d.full_name) LIKE :like_val2
           OR UPPER(a.status) LIKE :like_val3
        """
        sql += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"
        return query_all(
            sql,
            {
                "exact_id": search,
                "like_val": like,
                "like_val2": like,
                "like_val3": like,
            },
        )
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"
    return query_all(sql)


def get_appointment(appointment_id):
    return query_one(
        """
        SELECT a.appointment_id, a.patient_id, a.doctor_id, a.appointment_date,
               a.appointment_time, a.status, a.notes,
               p.full_name AS patient_name, d.full_name AS doctor_name,
               d.consultation_fee
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.appointment_id = :appointment_id
        """,
        {"appointment_id": appointment_id},
    )


def slot_taken(doctor_id, appointment_date, appointment_time, exclude_id=None):
    sql = """
        SELECT COUNT(*) AS total
        FROM appointments
        WHERE doctor_id = :doctor_id
          AND TRUNC(appointment_date) = TRUNC(:appointment_date)
          AND appointment_time = :appointment_time
          AND status <> 'Cancelled'
    """
    params = {
        "doctor_id": doctor_id,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
    }
    if exclude_id:
        sql += " AND appointment_id <> :exclude_id"
        params["exclude_id"] = exclude_id
    row = query_one(sql, params)
    return int(row["total"] or 0) > 0


def create_appointment(data):
    with get_connection() as conn:
        cursor = conn.cursor()
        new_id = cursor.var(oracledb.NUMBER)
        cursor.execute(
            """
            INSERT INTO appointments
                (patient_id, doctor_id, appointment_date, appointment_time, status, notes)
            VALUES
                (:patient_id, :doctor_id, :appointment_date, :appointment_time, :status, :notes)
            RETURNING appointment_id INTO :new_id
            """,
            {
                "patient_id": data["patient_id"],
                "doctor_id": data["doctor_id"],
                "appointment_date": data["appointment_date"],
                "appointment_time": data["appointment_time"],
                "status": data.get("status", "Scheduled"),
                "notes": data.get("notes"),
                "new_id": new_id,
            },
        )
        return _returning_id(new_id)


def update_appointment(appointment_id, data):
    return execute(
        """
        UPDATE appointments
        SET patient_id = :patient_id,
            doctor_id = :doctor_id,
            appointment_date = :appointment_date,
            appointment_time = :appointment_time,
            status = :status,
            notes = :notes
        WHERE appointment_id = :appointment_id
        """,
        {
            "patient_id": data["patient_id"],
            "doctor_id": data["doctor_id"],
            "appointment_date": data["appointment_date"],
            "appointment_time": data["appointment_time"],
            "status": data["status"],
            "notes": data.get("notes"),
            "appointment_id": appointment_id,
        },
    )


def appointment_has_bills(appointment_id):
    row = query_one(
        "SELECT COUNT(*) AS total FROM bills WHERE appointment_id = :appointment_id",
        {"appointment_id": appointment_id},
    )
    return int(row["total"] or 0)


def delete_appointment(appointment_id):
    return execute(
        "DELETE FROM appointments WHERE appointment_id = :appointment_id",
        {"appointment_id": appointment_id},
    )


def list_bills(search=""):
    search = (search or "").strip()
    sql = """
        SELECT b.bill_id, b.patient_id, b.appointment_id, b.consultation_fee,
               b.additional_charges, b.total_amount, b.paid_amount, b.payment_status,
               b.bill_date, p.full_name AS patient_name
        FROM bills b
        JOIN patients p ON p.patient_id = b.patient_id
    """
    if search:
        like = f"%{search.upper()}%"
        sql += """
        WHERE TO_CHAR(b.bill_id) = :exact_id
           OR TO_CHAR(b.patient_id) = :exact_id2
           OR UPPER(p.full_name) LIKE :like_val
           OR UPPER(b.payment_status) LIKE :like_val2
        """
        sql += " ORDER BY b.bill_id DESC"
        return query_all(
            sql,
            {
                "exact_id": search,
                "exact_id2": search,
                "like_val": like,
                "like_val2": like,
            },
        )
    sql += " ORDER BY b.bill_id DESC"
    return query_all(sql)


def get_bill(bill_id):
    return query_one(
        """
        SELECT b.bill_id, b.patient_id, b.appointment_id, b.consultation_fee,
               b.additional_charges, b.total_amount, b.paid_amount, b.payment_status,
               b.bill_date, p.full_name AS patient_name, p.phone AS patient_phone,
               p.address AS patient_address, p.age, p.gender
        FROM bills b
        JOIN patients p ON p.patient_id = b.patient_id
        WHERE b.bill_id = :bill_id
        """,
        {"bill_id": bill_id},
    )


def payment_status_from_amounts(total_amount, paid_amount):
    total_amount = float(total_amount or 0)
    paid_amount = float(paid_amount or 0)
    if paid_amount <= 0:
        return "Unpaid"
    if paid_amount + 0.001 >= total_amount:
        return "Paid"
    return "Partial"


def create_bill(data):
    total = float(data["consultation_fee"]) + float(data["additional_charges"])
    paid = float(data.get("paid_amount") or 0)
    status = payment_status_from_amounts(total, paid)
    with get_connection() as conn:
        cursor = conn.cursor()
        new_id = cursor.var(oracledb.NUMBER)
        cursor.execute(
            """
            INSERT INTO bills
                (patient_id, appointment_id, consultation_fee, additional_charges,
                 total_amount, paid_amount, payment_status)
            VALUES
                (:patient_id, :appointment_id, :consultation_fee, :additional_charges,
                 :total_amount, :paid_amount, :payment_status)
            RETURNING bill_id INTO :new_id
            """,
            {
                "patient_id": data["patient_id"],
                "appointment_id": data.get("appointment_id"),
                "consultation_fee": data["consultation_fee"],
                "additional_charges": data["additional_charges"],
                "total_amount": total,
                "paid_amount": paid,
                "payment_status": status,
                "new_id": new_id,
            },
        )
        return _returning_id(new_id)


def update_bill(bill_id, data):
    total = float(data["consultation_fee"]) + float(data["additional_charges"])
    paid = float(data.get("paid_amount") or 0)
    status = payment_status_from_amounts(total, paid)
    return execute(
        """
        UPDATE bills
        SET patient_id = :patient_id,
            appointment_id = :appointment_id,
            consultation_fee = :consultation_fee,
            additional_charges = :additional_charges,
            total_amount = :total_amount,
            paid_amount = :paid_amount,
            payment_status = :payment_status
        WHERE bill_id = :bill_id
        """,
        {
            "patient_id": data["patient_id"],
            "appointment_id": data.get("appointment_id"),
            "consultation_fee": data["consultation_fee"],
            "additional_charges": data["additional_charges"],
            "total_amount": total,
            "paid_amount": paid,
            "payment_status": status,
            "bill_id": bill_id,
        },
    )


def delete_bill(bill_id):
    return execute("DELETE FROM bills WHERE bill_id = :bill_id", {"bill_id": bill_id})
