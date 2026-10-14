from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import oracledb

import db
from config import Config
from validators import (
    APPT_STATUSES,
    first_error,
    parse_date,
    parse_int,
    parse_money,
    required,
    validate_gender,
    validate_name,
    validate_phone,
    validate_status,
    validate_time,
)

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def handle_db(action):
    try:
        return action()
    except ValueError:
        raise
    except db.DatabaseUnavailable as exc:
        flash(str(exc), "error")
        return None
    except oracledb.IntegrityError:
        flash(
            "This change was blocked by a database rule. The record may already exist, "
            "or related records may still be linked.",
            "error",
        )
        return None
    except Exception as exc:
        flash(f"An unexpected database error occurred: {exc}", "error")
        return None


@app.context_processor
def inject_globals():
    return {
        "hospital_name": "LifeLine General Hospital",
        "current_user": session.get("full_name"),
        "current_username": session.get("username"),
    }


@app.template_filter("inr")
def format_money(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


@app.template_filter("shortdate")
def format_date(value):
    if value is None:
        return "-"
    try:
        return value.strftime("%d %b %Y")
    except AttributeError:
        return str(value)


@app.template_filter("ymd")
def format_ymd(value):
    if not value:
        return ""
    try:
        return value.strftime("%Y-%m-%d")
    except AttributeError:
        return str(value)[:10]


def form_data():
    return request.form.to_dict(flat=True)


def ensure_admin():
    try:
        db.seed_admin_if_needed()
    except Exception:
        pass


@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_admin()
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter both username and password.", "error")
            return render_template("login.html")

        try:
            user = db.verify_user(username, password)
        except db.DatabaseUnavailable as exc:
            flash(str(exc), "error")
            return render_template("login.html")
        except Exception as exc:
            flash(f"An unexpected database error occurred: {exc}", "error")
            return render_template("login.html")
        if not user:
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = int(user["user_id"])
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        flash(f"Welcome back, {user['full_name']}.", "success")
        next_url = request.args.get("next") or url_for("dashboard")
        if not str(next_url).startswith("/"):
            next_url = url_for("dashboard")
        return redirect(next_url)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    ensure_admin()
    payload = handle_db(db.dashboard_stats_xe11)
    if payload is None:
        stats = {
            "total_patients": 0,
            "total_doctors": 0,
            "total_appointments": 0,
            "total_revenue": 0,
        }
        recent_appointments, recent_patients = [], []
    else:
        stats, recent_appointments, recent_patients = payload
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_appointments=recent_appointments,
        recent_patients=recent_patients,
    )


@app.route("/patients")
@login_required
def patients():
    search = request.args.get("q", "").strip()
    rows = handle_db(lambda: db.list_patients(search))
    return render_template("patients.html", patients=rows or [], search=search)


@app.route("/patients/new", methods=["GET", "POST"])
@login_required
def patient_new():
    if request.method == "POST":
        data, error = _patient_from_form()
        if error:
            flash(error, "error")
            return render_template("patient_form.html", mode="new", patient=form_data())
        new_id = handle_db(lambda: db.create_patient(data))
        if new_id:
            flash(f"Patient registered successfully. ID: {new_id}", "success")
            return redirect(url_for("patients"))
    return render_template("patient_form.html", mode="new", patient={})


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
def patient_edit(patient_id):
    patient = handle_db(lambda: db.get_patient(patient_id))
    if patient is None:
        flash("Patient not found or database is unavailable.", "error")
        return redirect(url_for("patients"))
    if request.method == "POST":
        data, error = _patient_from_form()
        if error:
            flash(error, "error")
            return render_template("patient_form.html", mode="edit", patient=form_data(), patient_id=patient_id)
        updated = handle_db(lambda: db.update_patient(patient_id, data))
        if updated is not None:
            flash("Patient details updated.", "success")
            return redirect(url_for("patients"))
    return render_template("patient_form.html", mode="edit", patient=patient, patient_id=patient_id)


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
@login_required
def patient_delete(patient_id):
    def action():
        appts, bills = db.patient_has_links(patient_id)
        if appts or bills:
            raise ValueError(
                f"Cannot delete this patient because {appts} appointment(s) and {bills} bill(s) still exist. "
                "Remove or reassign those records first."
            )
        return db.delete_patient(patient_id)

    try:
        result = handle_db(action)
        if result:
            flash("Patient deleted.", "success")
        elif result == 0:
            flash("Patient was not found.", "warning")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("patients"))


@app.route("/doctors")
@login_required
def doctors():
    search = request.args.get("q", "").strip()
    rows = handle_db(lambda: db.list_doctors(search))
    return render_template("doctors.html", doctors=rows or [], search=search)


@app.route("/doctors/new", methods=["GET", "POST"])
@login_required
def doctor_new():
    if request.method == "POST":
        data, error = _doctor_from_form()
        if error:
            flash(error, "error")
            return render_template("doctor_form.html", mode="new", doctor=form_data())
        new_id = handle_db(lambda: db.create_doctor(data))
        if new_id:
            flash(f"Doctor added successfully. ID: {new_id}", "success")
            return redirect(url_for("doctors"))
    return render_template("doctor_form.html", mode="new", doctor={})


@app.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
@login_required
def doctor_edit(doctor_id):
    doctor = handle_db(lambda: db.get_doctor(doctor_id))
    if doctor is None:
        flash("Doctor not found or database is unavailable.", "error")
        return redirect(url_for("doctors"))
    if request.method == "POST":
        data, error = _doctor_from_form()
        if error:
            flash(error, "error")
            return render_template("doctor_form.html", mode="edit", doctor=form_data(), doctor_id=doctor_id)
        updated = handle_db(lambda: db.update_doctor(doctor_id, data))
        if updated is not None:
            flash("Doctor details updated.", "success")
            return redirect(url_for("doctors"))
    return render_template("doctor_form.html", mode="edit", doctor=doctor, doctor_id=doctor_id)


@app.route("/doctors/<int:doctor_id>/delete", methods=["POST"])
@login_required
def doctor_delete(doctor_id):
    def action():
        linked = db.doctor_has_appointments(doctor_id)
        if linked:
            raise ValueError(
                f"Cannot delete this doctor because {linked} appointment(s) still exist."
            )
        return db.delete_doctor(doctor_id)

    try:
        result = handle_db(action)
        if result:
            flash("Doctor deleted.", "success")
        elif result == 0:
            flash("Doctor was not found.", "warning")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("doctors"))


@app.route("/doctors/<int:doctor_id>/appointments")
@login_required
def doctor_appointments(doctor_id):
    doctor = handle_db(lambda: db.get_doctor(doctor_id))
    if not doctor:
        flash("Doctor not found.", "error")
        return redirect(url_for("doctors"))
    rows = handle_db(lambda: db.doctor_appointments(doctor_id)) or []
    return render_template("doctor_appointments.html", doctor=doctor, appointments=rows)


@app.route("/appointments")
@login_required
def appointments():
    search = request.args.get("q", "").strip()
    rows = handle_db(lambda: db.list_appointments(search))
    return render_template("appointments.html", appointments=rows or [], search=search)


@app.route("/appointments/new", methods=["GET", "POST"])
@login_required
def appointment_new():
    patients = handle_db(lambda: db.list_patients()) or []
    doctors = handle_db(lambda: db.list_doctors()) or []
    if request.method == "POST":
        data, error = _appointment_from_form()
        if error:
            flash(error, "error")
            return render_template(
                "appointment_form.html",
                mode="new",
                appointment=form_data(),
                patients=patients,
                doctors=doctors,
            )
        def action():
            if not db.get_patient(data["patient_id"]):
                raise ValueError("Selected patient does not exist.")
            if not db.get_doctor(data["doctor_id"]):
                raise ValueError("Selected doctor does not exist.")
            if db.slot_taken(data["doctor_id"], data["appointment_date"], data["appointment_time"]):
                raise ValueError("This doctor already has an appointment at that date and time.")
            return db.create_appointment(data)

        try:
            new_id = handle_db(action)
            if new_id:
                flash(f"Appointment booked. ID: {new_id}", "success")
                return redirect(url_for("appointments"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template(
        "appointment_form.html",
        mode="new",
        appointment={"status": "Scheduled"},
        patients=patients,
        doctors=doctors,
    )


@app.route("/appointments/<int:appointment_id>/edit", methods=["GET", "POST"])
@login_required
def appointment_edit(appointment_id):
    appointment = handle_db(lambda: db.get_appointment(appointment_id))
    patients = handle_db(lambda: db.list_patients()) or []
    doctors = handle_db(lambda: db.list_doctors()) or []
    if not appointment:
        flash("Appointment not found.", "error")
        return redirect(url_for("appointments"))
    if request.method == "POST":
        data, error = _appointment_from_form()
        if error:
            flash(error, "error")
            return render_template(
                "appointment_form.html",
                mode="edit",
                appointment=form_data(),
                appointment_id=appointment_id,
                patients=patients,
                doctors=doctors,
            )

        def action():
            if not db.get_patient(data["patient_id"]):
                raise ValueError("Selected patient does not exist.")
            if not db.get_doctor(data["doctor_id"]):
                raise ValueError("Selected doctor does not exist.")
            if db.slot_taken(
                data["doctor_id"],
                data["appointment_date"],
                data["appointment_time"],
                exclude_id=appointment_id,
            ):
                raise ValueError("This doctor already has an appointment at that date and time.")
            return db.update_appointment(appointment_id, data)

        try:
            updated = handle_db(action)
            if updated is not None:
                flash("Appointment updated.", "success")
                return redirect(url_for("appointments"))
        except ValueError as exc:
            flash(str(exc), "error")
    # Normalize date for HTML date input
    if appointment.get("appointment_date"):
        appointment["appointment_date_input"] = appointment["appointment_date"].strftime("%Y-%m-%d")
    return render_template(
        "appointment_form.html",
        mode="edit",
        appointment=appointment,
        appointment_id=appointment_id,
        patients=patients,
        doctors=doctors,
    )


@app.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def appointment_cancel(appointment_id):
    appointment = handle_db(lambda: db.get_appointment(appointment_id))
    if not appointment:
        flash("Appointment not found.", "error")
        return redirect(url_for("appointments"))
    payload = {
        "patient_id": int(appointment["patient_id"]),
        "doctor_id": int(appointment["doctor_id"]),
        "appointment_date": appointment["appointment_date"],
        "appointment_time": str(appointment["appointment_time"])[:5],
        "status": "Cancelled",
        "notes": appointment.get("notes"),
    }
    handle_db(lambda: db.update_appointment(appointment_id, payload))
    flash("Appointment cancelled.", "success")
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@login_required
def appointment_delete(appointment_id):
    def action():
        if db.appointment_has_bills(appointment_id):
            raise ValueError("Cannot delete this appointment because a bill is linked to it.")
        return db.delete_appointment(appointment_id)

    try:
        result = handle_db(action)
        if result:
            flash("Appointment deleted.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("appointments"))


@app.route("/bills")
@login_required
def bills():
    search = request.args.get("q", "").strip()
    rows = handle_db(lambda: db.list_bills(search))
    return render_template("bills.html", bills=rows or [], search=search)


@app.route("/bills/new", methods=["GET", "POST"])
@login_required
def bill_new():
    patients = handle_db(lambda: db.list_patients()) or []
    appointments = handle_db(lambda: db.list_appointments()) or []
    prefill = {}
    appt_id = request.args.get("appointment_id", type=int)
    if appt_id:
        appt = handle_db(lambda: db.get_appointment(appt_id)) or {}
        if appt:
            prefill = {
                "patient_id": appt["patient_id"],
                "appointment_id": appt["appointment_id"],
                "consultation_fee": appt.get("consultation_fee") or 0,
                "additional_charges": 0,
                "paid_amount": 0,
            }
    if request.method == "POST":
        data, error = _bill_from_form()
        if error:
            flash(error, "error")
            return render_template(
                "bill_form.html",
                mode="new",
                bill=form_data(),
                patients=patients,
                appointments=appointments,
            )
        def action():
            if not db.get_patient(data["patient_id"]):
                raise ValueError("Selected patient does not exist.")
            if data.get("appointment_id") and not db.get_appointment(data["appointment_id"]):
                raise ValueError("Selected appointment does not exist.")
            return db.create_bill(data)

        try:
            new_id = handle_db(action)
            if new_id:
                flash(f"Bill generated. ID: {new_id}", "success")
                return redirect(url_for("bill_print", bill_id=new_id))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template(
        "bill_form.html",
        mode="new",
        bill=prefill,
        patients=patients,
        appointments=appointments,
    )


@app.route("/bills/<int:bill_id>/edit", methods=["GET", "POST"])
@login_required
def bill_edit(bill_id):
    bill = handle_db(lambda: db.get_bill(bill_id))
    patients = handle_db(lambda: db.list_patients()) or []
    appointments = handle_db(lambda: db.list_appointments()) or []
    if not bill:
        flash("Bill not found.", "error")
        return redirect(url_for("bills"))
    if request.method == "POST":
        data, error = _bill_from_form()
        if error:
            flash(error, "error")
            return render_template(
                "bill_form.html",
                mode="edit",
                bill=form_data(),
                bill_id=bill_id,
                patients=patients,
                appointments=appointments,
            )

        def action():
            if not db.get_patient(data["patient_id"]):
                raise ValueError("Selected patient does not exist.")
            if data.get("appointment_id") and not db.get_appointment(data["appointment_id"]):
                raise ValueError("Selected appointment does not exist.")
            return db.update_bill(bill_id, data)

        try:
            updated = handle_db(action)
            if updated is not None:
                flash("Bill updated.", "success")
                return redirect(url_for("bills"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template(
        "bill_form.html",
        mode="edit",
        bill=bill,
        bill_id=bill_id,
        patients=patients,
        appointments=appointments,
    )


@app.route("/bills/<int:bill_id>/print")
@login_required
def bill_print(bill_id):
    bill = handle_db(lambda: db.get_bill(bill_id))
    if not bill:
        flash("Bill not found.", "error")
        return redirect(url_for("bills"))
    return render_template("bill_print.html", bill=bill)


@app.route("/bills/<int:bill_id>/delete", methods=["POST"])
@login_required
def bill_delete(bill_id):
    result = handle_db(lambda: db.delete_bill(bill_id))
    if result:
        flash("Bill deleted.", "success")
    return redirect(url_for("bills"))


def _patient_from_form():
    values, error = first_error(
        validate_name(request.form.get("full_name"), "Patient name"),
        parse_int(request.form.get("age"), "Age", 0, 150),
        validate_gender(request.form.get("gender")),
        validate_phone(request.form.get("phone")),
    )
    if error:
        return None, error
    name, age, gender, phone = values
    return {
        "full_name": name,
        "age": age,
        "gender": gender,
        "phone": phone,
        "address": (request.form.get("address") or "").strip() or None,
        "disease": (request.form.get("disease") or "").strip() or None,
    }, None


def _doctor_from_form():
    spec_error = required(request.form.get("specialization"), "Specialization")
    specialization = " ".join((request.form.get("specialization") or "").split())
    values, error = first_error(
        validate_name(request.form.get("full_name"), "Doctor name"),
        (None, spec_error) if spec_error else (specialization, None),
        validate_phone(request.form.get("phone")),
        parse_money(request.form.get("consultation_fee"), "Consultation fee"),
    )
    if error:
        return None, error
    name, specialization, phone, fee = values
    return {
        "full_name": name,
        "specialization": specialization,
        "phone": phone,
        "consultation_fee": fee,
    }, None


def _appointment_from_form():
    values, error = first_error(
        parse_int(request.form.get("patient_id"), "Patient", 1),
        parse_int(request.form.get("doctor_id"), "Doctor", 1),
        parse_date(request.form.get("appointment_date"), "Appointment date"),
        validate_time(request.form.get("appointment_time")),
        validate_status(request.form.get("status") or "Scheduled", APPT_STATUSES, "Status"),
    )
    if error:
        return None, error
    patient_id, doctor_id, appt_date, appt_time, status = values
    return {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "appointment_date": appt_date,
        "appointment_time": appt_time,
        "status": status,
        "notes": (request.form.get("notes") or "").strip() or None,
    }, None


def _bill_from_form():
    values, error = first_error(
        parse_int(request.form.get("patient_id"), "Patient", 1),
        parse_money(request.form.get("consultation_fee"), "Consultation fee"),
        parse_money(request.form.get("additional_charges"), "Additional charges", allow_empty=True),
        parse_money(request.form.get("paid_amount"), "Paid amount", allow_empty=True),
    )
    if error:
        return None, error
    patient_id, consultation_fee, additional_charges, paid_amount = values
    appointment_raw = (request.form.get("appointment_id") or "").strip()
    appointment_id = None
    if appointment_raw:
        appointment_id, err = parse_int(appointment_raw, "Appointment", 1)
        if err:
            return None, err
    total = consultation_fee + additional_charges
    if paid_amount > total:
        return None, "Paid amount cannot be greater than the total bill."
    return {
        "patient_id": patient_id,
        "appointment_id": appointment_id,
        "consultation_fee": consultation_fee,
        "additional_charges": additional_charges,
        "paid_amount": paid_amount,
    }, None


def _bootstrap_admin():
    try:
        created = db.seed_admin_if_needed()
        if created:
            app.logger.info("Default administrator account created.")
    except db.DatabaseUnavailable as exc:
        app.logger.warning("Could not seed admin user: %s", exc)
    except Exception as exc:
        app.logger.warning("Could not seed admin user: %s", exc)


_bootstrap_admin()


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, host="127.0.0.1", port=5000)
