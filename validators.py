import re
from datetime import datetime

GENDERS = {"Male", "Female", "Other"}
APPT_STATUSES = {"Scheduled", "Completed", "Cancelled"}
PAYMENT_STATUSES = {"Paid", "Unpaid", "Partial"}
PHONE_RE = re.compile(r"^[0-9+\-\s]{10,20}$")
TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,99}$")


def required(value, label):
    if value is None or str(value).strip() == "":
        return f"{label} is required."
    return None


def parse_int(value, label, minimum=None, maximum=None):
    err = required(value, label)
    if err:
        return None, err
    try:
        number = int(str(value).strip())
    except ValueError:
        return None, f"{label} must be a whole number."
    if minimum is not None and number < minimum:
        return None, f"{label} must be at least {minimum}."
    if maximum is not None and number > maximum:
        return None, f"{label} cannot be greater than {maximum}."
    return number, None


def parse_money(value, label, allow_empty=False):
    if value is None or str(value).strip() == "":
        if allow_empty:
            return 0.0, None
        return None, f"{label} is required."
    try:
        amount = round(float(str(value).strip()), 2)
    except ValueError:
        return None, f"{label} must be a number."
    if amount < 0:
        return None, f"{label} cannot be negative."
    return amount, None


def parse_date(value, label):
    err = required(value, label)
    if err:
        return None, err
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d"), None
    except ValueError:
        return None, f"{label} must be a valid date (YYYY-MM-DD)."


def validate_name(value, label="Name"):
    err = required(value, label)
    if err:
        return None, err
    name = " ".join(str(value).split())
    if not NAME_RE.match(name):
        return None, f"{label} should contain letters only (spaces and . ' - are allowed)."
    return name, None


def validate_phone(value):
    err = required(value, "Phone number")
    if err:
        return None, err
    phone = str(value).strip()
    if not PHONE_RE.match(phone):
        return None, "Enter a valid phone number (10 to 20 digits)."
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        return None, "Phone number must contain at least 10 digits."
    return phone, None


def validate_gender(value):
    err = required(value, "Gender")
    if err:
        return None, err
    if value not in GENDERS:
        return None, "Gender must be Male, Female, or Other."
    return value, None


def validate_time(value):
    err = required(value, "Appointment time")
    if err:
        return None, err
    time_value = str(value).strip()
    if len(time_value) >= 5:
        time_value = time_value[:5]
    if not TIME_RE.match(time_value):
        return None, "Time must be in 24-hour HH:MM format, for example 09:30 or 14:00."
    return time_value, None


def validate_status(value, allowed, label):
    err = required(value, label)
    if err:
        return None, err
    if value not in allowed:
        return None, f"{label} is not valid."
    return value, None


def first_error(*pairs):
    """pairs are (value, error) tuples. Returns (values_list, first_error)."""
    values = []
    for value, error in pairs:
        if error:
            return None, error
        values.append(value)
    return values, None
