-- =============================================================================
-- LifeLine General Hospital — Oracle XE 11g schema
-- Database Systems (DBS) project
--
-- HOW TO RUN (beginner steps):
-- 1) Connect as SYSTEM (or another DBA user) in SQL*Plus or SQL Developer.
-- 2) Run SECTION A once to create the dedicated application user.
-- 3) Disconnect, then connect as HMS_APP.
-- 4) Run SECTION B to create tables, sequences, triggers, and indexes.
--
-- Do not use SYSTEM as the application login in Flask.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SECTION A — run as SYSTEM
-- -----------------------------------------------------------------------------
-- Change the password before running this in a shared lab.
--
-- CREATE USER hms_app IDENTIFIED BY hms_app_password
--   DEFAULT TABLESPACE USERS
--   TEMPORARY TABLESPACE TEMP
--   QUOTA UNLIMITED ON USERS;
--
-- GRANT CREATE SESSION TO hms_app;
-- GRANT CREATE TABLE TO hms_app;
-- GRANT CREATE SEQUENCE TO hms_app;
-- GRANT CREATE TRIGGER TO hms_app;
-- GRANT CREATE VIEW TO hms_app;

-- If you already created HMS_APP and need to rebuild objects, connect as
-- HMS_APP and drop objects first (order matters because of foreign keys):
--
-- DROP TABLE bills CASCADE CONSTRAINTS;
-- DROP TABLE appointments CASCADE CONSTRAINTS;
-- DROP TABLE patients CASCADE CONSTRAINTS;
-- DROP TABLE doctors CASCADE CONSTRAINTS;
-- DROP TABLE users CASCADE CONSTRAINTS;
-- DROP SEQUENCE seq_patient_id;
-- DROP SEQUENCE seq_doctor_id;
-- DROP SEQUENCE seq_appointment_id;
-- DROP SEQUENCE seq_bill_id;
-- DROP SEQUENCE seq_user_id;

-- -----------------------------------------------------------------------------
-- SECTION B — run as HMS_APP
-- -----------------------------------------------------------------------------

CREATE SEQUENCE seq_patient_id START WITH 1001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE seq_doctor_id START WITH 201 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE seq_appointment_id START WITH 5001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE seq_bill_id START WITH 9001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE seq_user_id START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

CREATE TABLE patients (
    patient_id          NUMBER          NOT NULL,
    full_name           VARCHAR2(100)   NOT NULL,
    age                 NUMBER(3)       NOT NULL,
    gender              VARCHAR2(10)    NOT NULL,
    phone               VARCHAR2(20)    NOT NULL,
    address             VARCHAR2(255),
    disease             VARCHAR2(150),
    registration_date   DATE            DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_patients PRIMARY KEY (patient_id),
    CONSTRAINT ck_patient_age CHECK (age BETWEEN 0 AND 150),
    CONSTRAINT ck_patient_gender CHECK (gender IN ('Male', 'Female', 'Other')),
    CONSTRAINT ck_patient_name CHECK (LENGTH(TRIM(full_name)) >= 2)
);

CREATE TABLE doctors (
    doctor_id           NUMBER          NOT NULL,
    full_name           VARCHAR2(100)   NOT NULL,
    specialization      VARCHAR2(100)   NOT NULL,
    phone               VARCHAR2(20)    NOT NULL,
    consultation_fee    NUMBER(10,2)    NOT NULL,
    CONSTRAINT pk_doctors PRIMARY KEY (doctor_id),
    CONSTRAINT ck_doctor_fee CHECK (consultation_fee >= 0),
    CONSTRAINT ck_doctor_name CHECK (LENGTH(TRIM(full_name)) >= 2)
);

CREATE TABLE appointments (
    appointment_id      NUMBER          NOT NULL,
    patient_id          NUMBER          NOT NULL,
    doctor_id           NUMBER          NOT NULL,
    appointment_date    DATE            NOT NULL,
    appointment_time    VARCHAR2(5)     NOT NULL,
    status              VARCHAR2(20)    DEFAULT 'Scheduled' NOT NULL,
    notes               VARCHAR2(255),
    created_on          DATE            DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_appointments PRIMARY KEY (appointment_id),
    CONSTRAINT fk_appt_patient FOREIGN KEY (patient_id)
        REFERENCES patients (patient_id),
    CONSTRAINT fk_appt_doctor FOREIGN KEY (doctor_id)
        REFERENCES doctors (doctor_id),
    CONSTRAINT ck_appt_status CHECK (status IN ('Scheduled', 'Completed', 'Cancelled')),
    CONSTRAINT ck_appt_time CHECK (REGEXP_LIKE(appointment_time, '^[0-2][0-9]:[0-5][0-9]$'))
);

-- Allows the same doctor/time slot to be reused after an appointment is cancelled.
CREATE UNIQUE INDEX ux_appt_active_slot ON appointments (
    CASE WHEN status <> 'Cancelled' THEN doctor_id END,
    CASE WHEN status <> 'Cancelled' THEN TRUNC(appointment_date) END,
    CASE WHEN status <> 'Cancelled' THEN appointment_time END
);

CREATE TABLE bills (
    bill_id             NUMBER          NOT NULL,
    patient_id          NUMBER          NOT NULL,
    appointment_id      NUMBER,
    consultation_fee    NUMBER(10,2)    DEFAULT 0 NOT NULL,
    additional_charges  NUMBER(10,2)    DEFAULT 0 NOT NULL,
    total_amount        NUMBER(10,2)    NOT NULL,
    paid_amount         NUMBER(10,2)    DEFAULT 0 NOT NULL,
    payment_status      VARCHAR2(20)    DEFAULT 'Unpaid' NOT NULL,
    bill_date           DATE            DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_bills PRIMARY KEY (bill_id),
    CONSTRAINT fk_bill_patient FOREIGN KEY (patient_id)
        REFERENCES patients (patient_id),
    CONSTRAINT fk_bill_appointment FOREIGN KEY (appointment_id)
        REFERENCES appointments (appointment_id),
    CONSTRAINT ck_bill_status CHECK (payment_status IN ('Paid', 'Unpaid', 'Partial')),
    CONSTRAINT ck_bill_amounts CHECK (
        consultation_fee >= 0
        AND additional_charges >= 0
        AND total_amount >= 0
        AND paid_amount >= 0
        AND paid_amount <= total_amount
    )
);

CREATE TABLE users (
    user_id             NUMBER          NOT NULL,
    username            VARCHAR2(50)    NOT NULL,
    password_hash       VARCHAR2(255)   NOT NULL,
    full_name           VARCHAR2(100)   NOT NULL,
    role                VARCHAR2(20)    DEFAULT 'Admin' NOT NULL,
    created_on          DATE            DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_users PRIMARY KEY (user_id),
    CONSTRAINT uk_users_username UNIQUE (username),
    CONSTRAINT ck_users_role CHECK (role IN ('Admin'))
);

CREATE INDEX ix_patients_name ON patients (UPPER(full_name));
CREATE INDEX ix_doctors_name ON doctors (UPPER(full_name));
CREATE INDEX ix_appt_patient ON appointments (patient_id);
CREATE INDEX ix_appt_doctor ON appointments (doctor_id);
CREATE INDEX ix_bills_patient ON bills (patient_id);

CREATE OR REPLACE TRIGGER trg_patients_bi
BEFORE INSERT ON patients
FOR EACH ROW
BEGIN
    IF :NEW.patient_id IS NULL THEN
        SELECT seq_patient_id.NEXTVAL INTO :NEW.patient_id FROM dual;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_doctors_bi
BEFORE INSERT ON doctors
FOR EACH ROW
BEGIN
    IF :NEW.doctor_id IS NULL THEN
        SELECT seq_doctor_id.NEXTVAL INTO :NEW.doctor_id FROM dual;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_appointments_bi
BEFORE INSERT ON appointments
FOR EACH ROW
BEGIN
    IF :NEW.appointment_id IS NULL THEN
        SELECT seq_appointment_id.NEXTVAL INTO :NEW.appointment_id FROM dual;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_bills_bi
BEFORE INSERT ON bills
FOR EACH ROW
BEGIN
    IF :NEW.bill_id IS NULL THEN
        SELECT seq_bill_id.NEXTVAL INTO :NEW.bill_id FROM dual;
    END IF;
    :NEW.total_amount := NVL(:NEW.consultation_fee, 0) + NVL(:NEW.additional_charges, 0);
END;
/

CREATE OR REPLACE TRIGGER trg_bills_bu
BEFORE UPDATE ON bills
FOR EACH ROW
BEGIN
    :NEW.total_amount := NVL(:NEW.consultation_fee, 0) + NVL(:NEW.additional_charges, 0);
END;
/

CREATE OR REPLACE TRIGGER trg_users_bi
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    IF :NEW.user_id IS NULL THEN
        SELECT seq_user_id.NEXTVAL INTO :NEW.user_id FROM dual;
    END IF;
END;
/

COMMIT;

-- Optional sample data (uncomment after the schema is created if you want demo rows).
-- The Flask app will still create the admin user automatically on first start.
--
-- INSERT INTO patients (full_name, age, gender, phone, address, disease)
-- VALUES ('Ayesha Khan', 29, 'Female', '03001234567', 'Lahore', 'Fever');
-- INSERT INTO doctors (full_name, specialization, phone, consultation_fee)
-- VALUES ('Dr. Ahmed Raza', 'Cardiology', '03007654321', 2500);
-- COMMIT;
