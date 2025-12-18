from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a random secret key in production

# Database file located next to this file
DB_PATH = os.path.join(os.path.dirname(__file__), 'hotel.db')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    # Ensure additional requested user columns exist (migration-friendly)
    try:
        cur = db.execute("PRAGMA table_info(users)")
        existing = {r['name'] for r in cur.fetchall()}
        # columns to ensure: user_name, created_at, admin_id, manager_id, managing_floor, receptionist_id, admin_type
        if 'user_name' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN user_name TEXT')
        if 'created_at' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN created_at TEXT')
        if 'admin_id' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN admin_id INTEGER')
        if 'manager_id' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN manager_id INTEGER')
        if 'managing_floor' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN managing_floor INTEGER')
        if 'receptionist_id' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN receptionist_id INTEGER')
        if 'admin_type' not in existing:
            db.execute('ALTER TABLE users ADD COLUMN admin_type TEXT')
    except Exception:
        pass
    # rooms table
    db.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image TEXT
        )
    ''')

    # employees table
    db.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            position TEXT,
            hire_date TEXT,
            salary REAL
        )
    ''')

    # hired_as table: records roles/assignments for employees
    db.execute('''
        CREATE TABLE IF NOT EXISTS hired_as (
            hired_as_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            role TEXT,
            start_date TEXT,
            end_date TEXT,
            FOREIGN KEY(employee_id) REFERENCES employees(employee_id)
        )
    ''')

    # belong_to table: link bookings to specific room units
    db.execute('''
        CREATE TABLE IF NOT EXISTS belong_to (
            booking_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            PRIMARY KEY (booking_id, room_id),
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id),
            FOREIGN KEY(room_id) REFERENCES room_units(room_id)
        )
    ''')

    # room_units table (individual room instances)
    db.execute('''
        CREATE TABLE IF NOT EXISTS room_units (
            room_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id INTEGER,
            room_no TEXT,
            occupied INTEGER DEFAULT 0,
            available INTEGER DEFAULT 1,
            maintenance INTEGER DEFAULT 0,
            floor INTEGER,
            FOREIGN KEY(type_id) REFERENCES rooms(id)
        )
    ''')

    # services table
    db.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            description TEXT,
            unit_price REAL,
            booking_id INTEGER,
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id)
        )
    ''')

    # invoices table
    db.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_no INTEGER PRIMARY KEY AUTOINCREMENT,
            room_charge REAL,
            total_amount REAL,
            tax REAL,
            service_charge REAL,
            issue_date TEXT,
            booking_id INTEGER,
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id)
        )
    ''')

    # user_phones table: composite primary key (user_id, phone)
    db.execute('''
        CREATE TABLE IF NOT EXISTS user_phones (
            user_id INTEGER NOT NULL,
            phone TEXT NOT NULL,
            PRIMARY KEY(user_id, phone),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # guests table
    db.execute('''
        CREATE TABLE IF NOT EXISTS guests (
            invoice_no INTEGER,
            guest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            email TEXT,
            NID TEXT,
            phone TEXT,
            FOREIGN KEY(invoice_no) REFERENCES invoices(invoice_no)
        )
    ''')

    # bookings table (new schema requested)
    db.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
            checkin_date TEXT NOT NULL,
            checkout_date TEXT NOT NULL,
            room_id INTEGER NOT NULL,
            user_id INTEGER,
            guest_id INTEGER,
            checked_in INTEGER DEFAULT 0,
            checked_out INTEGER DEFAULT 0,
            reserved INTEGER DEFAULT 1,
            cancelled INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
    ''')

    # If an older bookings table exists with different columns (e.g., `id`, `check_in`), migrate it
    try:
        cur = db.execute("PRAGMA table_info(bookings)")
        cols = [r['name'] for r in cur.fetchall()]
        # detect legacy schema using 'id' or 'check_in' column
        if 'booking_id' not in cols and ('id' in cols or 'check_in' in cols):
            # rename legacy table, create new table (already created if not exists), copy data, drop old
            db.execute('ALTER TABLE bookings RENAME TO bookings_old')
            # recreate new table
            db.execute('''
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkin_date TEXT NOT NULL,
                    checkout_date TEXT NOT NULL,
                    room_id INTEGER NOT NULL,
                    user_id INTEGER,
                    guest_id INTEGER,
                    checked_in INTEGER DEFAULT 0,
                    checked_out INTEGER DEFAULT 0,
                    reserved INTEGER DEFAULT 1,
                    cancelled INTEGER DEFAULT 0,
                    created_at TEXT,
                    FOREIGN KEY(room_id) REFERENCES rooms(id)
                )
            ''')
            # copy mapping where possible
            db.execute('''
                INSERT INTO bookings (booking_id, checkin_date, checkout_date, room_id, created_at)
                SELECT id, check_in, check_out, room_id, created_at FROM bookings_old
            ''')
            db.execute('DROP TABLE IF EXISTS bookings_old')
    except Exception:
        # If anything goes wrong during migration, continue without crashing setup
        pass

    db.commit()


def create_default_rooms():
    db = get_db()
    cur = db.execute('SELECT COUNT(*) as cnt FROM rooms')
    if cur.fetchone()['cnt'] == 0:
        rooms = [
            ('Super wiz Room', 'Spacious room with a king-size bed and city view.', 150, 'hotel-booking-flask-main/static/images/abc.jpg'),
            ('Executive Suite', 'Luxury suite with separate living area and panoramic views.', 250, 'https://cdn.pixabay.com/photo/2020/10/18/09/16/bedroom-5664221_1280.jpg'),
            ('Family Room', 'Perfect for families with two queen beds and extra space.', 200, 'https://cdn.pixabay.com/photo/2018/02/24/17/17/window-3178666_1280.jpg')
        ]
        db.executemany('INSERT INTO rooms (name, description, price, image) VALUES (?, ?, ?, ?)', rooms)
        db.commit()


def create_first_admin():
    db = get_db()
    cur = db.execute('SELECT COUNT(*) as cnt FROM users')
    row = cur.fetchone()
    if row['cnt'] == 0:
        # Create default admin: username=admin password=admin
        pw_hash = generate_password_hash('admin')
        from datetime import datetime
        created_at = datetime.utcnow().isoformat()
        db.execute('INSERT INTO users (username, password, user_name, email, phone, is_admin, created_at, admin_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   ('admin', pw_hash, 'Administrator', 'admin@example.com', '', 1, created_at, 'super'))
        db.commit()


def create_booking(db, checkin_date, checkout_date, room_id, user_id=None, guest_id=None, reserved=1):
    from datetime import datetime
    created_at = datetime.utcnow().isoformat()
    db.execute(
        'INSERT INTO bookings (checkin_date, checkout_date, room_id, user_id, guest_id, reserved, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (checkin_date, checkout_date, room_id, user_id, guest_id, reserved, created_at)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def mark_checked_in(db, booking_id):
    db.execute('UPDATE bookings SET checked_in = 1 WHERE booking_id = ?', (booking_id,))
    db.commit()


def mark_checked_out(db, booking_id):
    db.execute('UPDATE bookings SET checked_out = 1 WHERE booking_id = ?', (booking_id,))
    db.commit()


def cancel_booking(db, booking_id):
    db.execute('UPDATE bookings SET cancelled = 1, reserved = 0 WHERE booking_id = ?', (booking_id,))
    db.commit()


### Employees helpers and admin routes ###

def create_employee(db, name, phone=None, position=None, hire_date=None, salary=None):
    db.execute(
        'INSERT INTO employees (name, phone, position, hire_date, salary) VALUES (?, ?, ?, ?, ?)',
        (name, phone, position, hire_date, salary)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_employee(db, employee_id, name, phone=None, position=None, hire_date=None, salary=None):
    db.execute(
        'UPDATE employees SET name = ?, phone = ?, position = ?, hire_date = ?, salary = ? WHERE employee_id = ?',
        (name, phone, position, hire_date, salary, employee_id)
    )
    db.commit()


def delete_employee(db, employee_id):
    db.execute('DELETE FROM employees WHERE employee_id = ?', (employee_id,))
    db.commit()


def admin_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get('admin_id'):
            flash('Admin login required', 'danger')
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route('/admin/employees')
@admin_required
def admin_employees():
    db = get_db()
    emps = db.execute('SELECT employee_id, name, phone, position, hire_date, salary FROM employees').fetchall()
    return render_template('admin_employees.html', title='Employees', employees=emps)


@app.route('/admin/employees/create', methods=['GET', 'POST'])
@admin_required
def admin_employee_create():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        position = request.form.get('position')
        hire_date = request.form.get('hire_date')
        salary = request.form.get('salary') or None
        db = get_db()
        create_employee(db, name, phone, position, hire_date, salary)
        flash('Employee created', 'success')
        return redirect(url_for('admin_employees'))
    return render_template('edit_employee.html', title='Create Employee', employee=None)


@app.route('/admin/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_employee_edit(employee_id):
    db = get_db()
    cur = db.execute('SELECT employee_id, name, phone, position, hire_date, salary FROM employees WHERE employee_id = ?', (employee_id,))
    emp = cur.fetchone()
    if not emp:
        flash('Employee not found', 'danger')
        return redirect(url_for('admin_employees'))
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        position = request.form.get('position')
        hire_date = request.form.get('hire_date')
        salary = request.form.get('salary') or None
        update_employee(db, employee_id, name, phone, position, hire_date, salary)
        flash('Employee updated', 'success')
        return redirect(url_for('admin_employees'))
    return render_template('edit_employee.html', title='Edit Employee', employee=emp)


@app.route('/admin/employees/<int:employee_id>/delete', methods=['POST'])
@admin_required
def admin_employee_delete(employee_id):
    db = get_db()
    delete_employee(db, employee_id)
    flash('Employee deleted', 'success')
    return redirect(url_for('admin_employees'))


### Room units (individual rooms) helpers and admin routes ###


def create_room_unit(db, type_id, room_no=None, floor=None, occupied=0, available=1, maintenance=0):
    db.execute(
        'INSERT INTO room_units (type_id, room_no, floor, occupied, available, maintenance) VALUES (?, ?, ?, ?, ?, ?)',
        (type_id, room_no, floor, occupied, available, maintenance)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_room_unit(db, room_id, type_id, room_no=None, floor=None, occupied=0, available=1, maintenance=0):
    db.execute(
        'UPDATE room_units SET type_id = ?, room_no = ?, floor = ?, occupied = ?, available = ?, maintenance = ? WHERE room_id = ?',
        (type_id, room_no, floor, occupied, available, maintenance, room_id)
    )
    db.commit()


def delete_room_unit(db, room_id):
    db.execute('DELETE FROM room_units WHERE room_id = ?', (room_id,))
    db.commit()


@app.route('/admin/room_units')
@admin_required
def admin_room_units():
    db = get_db()
    units = db.execute('SELECT r.room_id, r.type_id, r.room_no, r.occupied, r.available, r.maintenance, r.floor, rm.name as type_name FROM room_units r LEFT JOIN rooms rm ON rm.id = r.type_id').fetchall()
    return render_template('admin_room_units.html', title='Rooms', units=units)


@app.route('/admin/room_units/create', methods=['GET', 'POST'])
@admin_required
def admin_room_unit_create():
    db = get_db()
    types = db.execute('SELECT id, name FROM rooms').fetchall()
    if request.method == 'POST':
        type_id = request.form.get('type_id') or None
        room_no = request.form.get('room_no')
        floor = request.form.get('floor') or None
        occupied = 1 if request.form.get('occupied') == 'on' else 0
        available = 1 if request.form.get('available') == 'on' else 0
        maintenance = 1 if request.form.get('maintenance') == 'on' else 0
        create_room_unit(db, type_id, room_no, floor, occupied, available, maintenance)
        flash('Room unit created', 'success')
        return redirect(url_for('admin_room_units'))
    return render_template('edit_room_unit.html', title='Create Room', unit=None, types=types)


@app.route('/admin/room_units/<int:room_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_room_unit_edit(room_id):
    db = get_db()
    cur = db.execute('SELECT room_id, type_id, room_no, floor, occupied, available, maintenance FROM room_units WHERE room_id = ?', (room_id,))
    unit = cur.fetchone()
    if not unit:
        flash('Room not found', 'danger')
        return redirect(url_for('admin_room_units'))
    types = db.execute('SELECT id, name FROM rooms').fetchall()
    if request.method == 'POST':
        type_id = request.form.get('type_id') or None
        room_no = request.form.get('room_no')
        floor = request.form.get('floor') or None
        occupied = 1 if request.form.get('occupied') == 'on' else 0
        available = 1 if request.form.get('available') == 'on' else 0
        maintenance = 1 if request.form.get('maintenance') == 'on' else 0
        update_room_unit(db, room_id, type_id, room_no, floor, occupied, available, maintenance)
        flash('Room unit updated', 'success')
        return redirect(url_for('admin_room_units'))
    return render_template('edit_room_unit.html', title='Edit Room', unit=unit, types=types)


@app.route('/admin/room_units/<int:room_id>/delete', methods=['POST'])
@admin_required
def admin_room_unit_delete(room_id):
    db = get_db()
    delete_room_unit(db, room_id)
    flash('Room unit deleted', 'success')
    return redirect(url_for('admin_room_units'))


### Services helpers and admin routes ###


def create_service(db, service_name, description=None, unit_price=None, booking_id=None):
    db.execute(
        'INSERT INTO services (service_name, description, unit_price, booking_id) VALUES (?, ?, ?, ?)',
        (service_name, description, unit_price, booking_id)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_service(db, service_id, service_name, description=None, unit_price=None, booking_id=None):
    db.execute(
        'UPDATE services SET service_name = ?, description = ?, unit_price = ?, booking_id = ? WHERE service_id = ?',
        (service_name, description, unit_price, booking_id, service_id)
    )
    db.commit()


def delete_service(db, service_id):
    db.execute('DELETE FROM services WHERE service_id = ?', (service_id,))
    db.commit()


@app.route('/admin/services')
@admin_required
def admin_services():
    db = get_db()
    services = db.execute('SELECT s.service_id, s.service_name, s.description, s.unit_price, s.booking_id FROM services s').fetchall()
    return render_template('admin_services.html', title='Services', services=services)


@app.route('/admin/services/create', methods=['GET', 'POST'])
@admin_required
def admin_service_create():
    if request.method == 'POST':
        name = request.form.get('service_name')
        desc = request.form.get('description')
        price = request.form.get('unit_price') or None
        booking_id = request.form.get('booking_id') or None
        db = get_db()
        create_service(db, name, desc, price, booking_id)
        flash('Service created', 'success')
        return redirect(url_for('admin_services'))
    return render_template('edit_service.html', title='Create Service', service=None)


@app.route('/admin/services/<int:service_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_service_edit(service_id):
    db = get_db()
    cur = db.execute('SELECT service_id, service_name, description, unit_price, booking_id FROM services WHERE service_id = ?', (service_id,))
    svc = cur.fetchone()
    if not svc:
        flash('Service not found', 'danger')
        return redirect(url_for('admin_services'))
    if request.method == 'POST':
        name = request.form.get('service_name')
        desc = request.form.get('description')
        price = request.form.get('unit_price') or None
        booking_id = request.form.get('booking_id') or None
        update_service(db, service_id, name, desc, price, booking_id)
        flash('Service updated', 'success')
        return redirect(url_for('admin_services'))
    return render_template('edit_service.html', title='Edit Service', service=svc)


@app.route('/admin/services/<int:service_id>/delete', methods=['POST'])
@admin_required
def admin_service_delete(service_id):
    db = get_db()
    delete_service(db, service_id)
    flash('Service deleted', 'success')
    return redirect(url_for('admin_services'))


### Invoices helpers and admin routes ###


def create_invoice(db, room_charge=None, total_amount=None, tax=None, service_charge=None, issue_date=None, booking_id=None):
    db.execute(
        'INSERT INTO invoices (room_charge, total_amount, tax, service_charge, issue_date, booking_id) VALUES (?, ?, ?, ?, ?, ?)',
        (room_charge, total_amount, tax, service_charge, issue_date, booking_id)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_invoice(db, invoice_no, room_charge=None, total_amount=None, tax=None, service_charge=None, issue_date=None, booking_id=None):
    db.execute(
        'UPDATE invoices SET room_charge = ?, total_amount = ?, tax = ?, service_charge = ?, issue_date = ?, booking_id = ? WHERE invoice_no = ?',
        (room_charge, total_amount, tax, service_charge, issue_date, booking_id, invoice_no)
    )
    db.commit()


def delete_invoice(db, invoice_no):
    db.execute('DELETE FROM invoices WHERE invoice_no = ?', (invoice_no,))
    db.commit()


@app.route('/admin/invoices')
@admin_required
def admin_invoices():
    db = get_db()
    invs = db.execute('SELECT invoice_no, room_charge, total_amount, tax, service_charge, issue_date, booking_id FROM invoices ORDER BY issue_date DESC').fetchall()
    return render_template('admin_invoices.html', title='Invoices', invoices=invs)


@app.route('/admin/invoices/create', methods=['GET', 'POST'])
@admin_required
def admin_invoice_create():
    if request.method == 'POST':
        room_charge = request.form.get('room_charge') or None
        total_amount = request.form.get('total_amount') or None
        tax = request.form.get('tax') or None
        service_charge = request.form.get('service_charge') or None
        issue_date = request.form.get('issue_date') or None
        booking_id = request.form.get('booking_id') or None
        db = get_db()
        create_invoice(db, room_charge, total_amount, tax, service_charge, issue_date, booking_id)
        flash('Invoice created', 'success')
        return redirect(url_for('admin_invoices'))
    return render_template('edit_invoice.html', title='Create Invoice', invoice=None)


@app.route('/admin/invoices/<int:invoice_no>/edit', methods=['GET', 'POST'])
@admin_required
def admin_invoice_edit(invoice_no):
    db = get_db()
    cur = db.execute('SELECT invoice_no, room_charge, total_amount, tax, service_charge, issue_date, booking_id FROM invoices WHERE invoice_no = ?', (invoice_no,))
    inv = cur.fetchone()
    if not inv:
        flash('Invoice not found', 'danger')
        return redirect(url_for('admin_invoices'))
    if request.method == 'POST':
        room_charge = request.form.get('room_charge') or None
        total_amount = request.form.get('total_amount') or None
        tax = request.form.get('tax') or None
        service_charge = request.form.get('service_charge') or None
        issue_date = request.form.get('issue_date') or None
        booking_id = request.form.get('booking_id') or None
        update_invoice(db, invoice_no, room_charge, total_amount, tax, service_charge, issue_date, booking_id)
        flash('Invoice updated', 'success')
        return redirect(url_for('admin_invoices'))
    return render_template('edit_invoice.html', title='Edit Invoice', invoice=inv)


@app.route('/admin/invoices/<int:invoice_no>/delete', methods=['POST'])
@admin_required
def admin_invoice_delete(invoice_no):
    db = get_db()
    delete_invoice(db, invoice_no)
    flash('Invoice deleted', 'success')
    return redirect(url_for('admin_invoices'))


### User phones helpers and admin routes ###


def add_user_phone(db, user_id, phone):
    db.execute('INSERT OR IGNORE INTO user_phones (user_id, phone) VALUES (?, ?)', (user_id, phone))
    db.commit()


def delete_user_phone(db, user_id, phone):
    db.execute('DELETE FROM user_phones WHERE user_id = ? AND phone = ?', (user_id, phone))
    db.commit()


def get_user_phones(db, user_id):
    return db.execute('SELECT phone FROM user_phones WHERE user_id = ?', (user_id,)).fetchall()


@app.route('/admin/user_phones')
@admin_required
def admin_user_phones():
    db = get_db()
    phones = db.execute('''
        SELECT up.user_id, up.phone, u.username
        FROM user_phones up
        LEFT JOIN users u ON u.id = up.user_id
        ORDER BY up.user_id
    ''').fetchall()
    return render_template('admin_user_phones.html', title='User Phones', phones=phones)


@app.route('/admin/user_phones/create', methods=['GET', 'POST'])
@admin_required
def admin_user_phone_create():
    db = get_db()
    users = db.execute('SELECT id, username FROM users').fetchall()
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        phone = request.form.get('phone')
        if not user_id or not phone:
            flash('User and phone are required', 'danger')
            return redirect(url_for('admin_user_phone_create'))
        add_user_phone(db, user_id, phone)
        flash('Phone added for user', 'success')
        return redirect(url_for('admin_user_phones'))
    return render_template('edit_user_phone.html', title='Add User Phone', users=users)


@app.route('/admin/user_phones/delete', methods=['POST'])
@admin_required
def admin_user_phone_delete():
    db = get_db()
    user_id = request.form.get('user_id')
    phone = request.form.get('phone')
    if not user_id or not phone:
        flash('Missing parameters', 'danger')
        return redirect(url_for('admin_user_phones'))
    delete_user_phone(db, user_id, phone)
    flash('Phone deleted', 'success')
    return redirect(url_for('admin_user_phones'))


### Hired-as helpers and admin routes ###


def create_hired_as(db, employee_id, role=None, start_date=None, end_date=None):
    db.execute(
        'INSERT INTO hired_as (employee_id, role, start_date, end_date) VALUES (?, ?, ?, ?)',
        (employee_id, role, start_date, end_date)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_hired_as(db, hired_as_id, employee_id, role=None, start_date=None, end_date=None):
    db.execute(
        'UPDATE hired_as SET employee_id = ?, role = ?, start_date = ?, end_date = ? WHERE hired_as_id = ?',
        (employee_id, role, start_date, end_date, hired_as_id)
    )
    db.commit()


def delete_hired_as(db, hired_as_id):
    db.execute('DELETE FROM hired_as WHERE hired_as_id = ?', (hired_as_id,))
    db.commit()


@app.route('/admin/hired_as')
@admin_required
def admin_hired_as():
    db = get_db()
    rows = db.execute('''
        SELECT h.hired_as_id, h.employee_id, h.role, h.start_date, h.end_date, e.name as employee_name
        FROM hired_as h
        LEFT JOIN employees e ON e.employee_id = h.employee_id
        ORDER BY h.start_date DESC
    ''').fetchall()
    return render_template('admin_hired_as.html', title='Hired As', records=rows)


@app.route('/admin/hired_as/create', methods=['GET', 'POST'])
@admin_required
def admin_hired_as_create():
    db = get_db()
    emps = db.execute('SELECT employee_id, name FROM employees').fetchall()
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        role = request.form.get('role')
        start_date = request.form.get('start_date') or None
        end_date = request.form.get('end_date') or None
        create_hired_as(db, employee_id, role, start_date, end_date)
        flash('Hired-as record created', 'success')
        return redirect(url_for('admin_hired_as'))
    return render_template('edit_hired_as.html', title='Create Hired As', emps=emps, record=None)


@app.route('/admin/hired_as/<int:hired_as_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_hired_as_edit(hired_as_id):
    db = get_db()
    cur = db.execute('SELECT hired_as_id, employee_id, role, start_date, end_date FROM hired_as WHERE hired_as_id = ?', (hired_as_id,))
    rec = cur.fetchone()
    if not rec:
        flash('Record not found', 'danger')
        return redirect(url_for('admin_hired_as'))
    emps = db.execute('SELECT employee_id, name FROM employees').fetchall()
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        role = request.form.get('role')
        start_date = request.form.get('start_date') or None
        end_date = request.form.get('end_date') or None
        update_hired_as(db, hired_as_id, employee_id, role, start_date, end_date)
        flash('Hired-as record updated', 'success')
        return redirect(url_for('admin_hired_as'))
    return render_template('edit_hired_as.html', title='Edit Hired As', emps=emps, record=rec)


@app.route('/admin/hired_as/<int:hired_as_id>/delete', methods=['POST'])
@admin_required
def admin_hired_as_delete(hired_as_id):
    db = get_db()
    delete_hired_as(db, hired_as_id)
    flash('Hired-as record deleted', 'success')
    return redirect(url_for('admin_hired_as'))


### Belong-to helpers and admin routes ###


def add_belong_to(db, booking_id, room_id):
    db.execute('INSERT OR IGNORE INTO belong_to (booking_id, room_id) VALUES (?, ?)', (booking_id, room_id))
    db.commit()


def delete_belong_to(db, booking_id, room_id):
    db.execute('DELETE FROM belong_to WHERE booking_id = ? AND room_id = ?', (booking_id, room_id))
    db.commit()


def get_rooms_for_booking(db, booking_id):
    return db.execute('SELECT r.room_id, r.room_no, rm.name as room_type FROM belong_to b JOIN room_units r ON r.room_id = b.room_id LEFT JOIN rooms rm ON rm.id = r.type_id WHERE b.booking_id = ?', (booking_id,)).fetchall()


@app.route('/admin/belong_to')
@admin_required
def admin_belong_to():
    db = get_db()
    rows = db.execute('''
        SELECT b.booking_id, b.room_id, r.room_no, rm.name as room_type
        FROM belong_to b
        LEFT JOIN room_units r ON r.room_id = b.room_id
        LEFT JOIN rooms rm ON rm.id = r.type_id
        ORDER BY b.booking_id DESC
    ''').fetchall()
    return render_template('admin_belong_to.html', title='Belong To', rows=rows)


@app.route('/admin/belong_to/create', methods=['GET', 'POST'])
@admin_required
def admin_belong_to_create():
    db = get_db()
    bookings = db.execute('SELECT booking_id, checkin_date, checkout_date, room_id FROM bookings ORDER BY created_at DESC').fetchall()
    units = db.execute('SELECT room_id, room_no, floor FROM room_units').fetchall()
    if request.method == 'POST':
        booking_id = request.form.get('booking_id')
        room_id = request.form.get('room_id')
        if not booking_id or not room_id:
            flash('Booking and room are required', 'danger')
            return redirect(url_for('admin_belong_to_create'))
        add_belong_to(db, booking_id, room_id)
        flash('Assigned room to booking', 'success')
        return redirect(url_for('admin_belong_to'))
    return render_template('edit_belong_to.html', title='Assign Room to Booking', bookings=bookings, units=units)


@app.route('/admin/belong_to/delete', methods=['POST'])
@admin_required
def admin_belong_to_delete():
    db = get_db()
    booking_id = request.form.get('booking_id')
    room_id = request.form.get('room_id')
    if not booking_id or not room_id:
        flash('Missing parameters', 'danger')
        return redirect(url_for('admin_belong_to'))
    delete_belong_to(db, booking_id, room_id)
    flash('Assignment removed', 'success')
    return redirect(url_for('admin_belong_to'))


### Guests helpers and admin routes ###


def create_guest(db, invoice_no=None, name=None, address=None, email=None, NID=None, phone=None):
    db.execute(
        'INSERT INTO guests (invoice_no, name, address, email, NID, phone) VALUES (?, ?, ?, ?, ?, ?)',
        (invoice_no, name, address, email, NID, phone)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid() as id').fetchone()['id']


def update_guest(db, guest_id, invoice_no=None, name=None, address=None, email=None, NID=None, phone=None):
    db.execute(
        'UPDATE guests SET invoice_no = ?, name = ?, address = ?, email = ?, NID = ?, phone = ? WHERE guest_id = ?',
        (invoice_no, name, address, email, NID, phone, guest_id)
    )
    db.commit()


def delete_guest(db, guest_id):
    db.execute('DELETE FROM guests WHERE guest_id = ?', (guest_id,))
    db.commit()


@app.route('/admin/guests')
@admin_required
def admin_guests():
    db = get_db()
    guests = db.execute('SELECT guest_id, invoice_no, name, address, email, NID, phone FROM guests ORDER BY guest_id DESC').fetchall()
    return render_template('admin_guests.html', title='Guests', guests=guests)


@app.route('/admin/guests/create', methods=['GET', 'POST'])
@admin_required
def admin_guest_create():
    db = get_db()
    invoices = db.execute('SELECT invoice_no FROM invoices ORDER BY issue_date DESC').fetchall()
    if request.method == 'POST':
        invoice_no = request.form.get('invoice_no') or None
        name = request.form.get('name')
        address = request.form.get('address')
        email = request.form.get('email')
        NID = request.form.get('NID')
        phone = request.form.get('phone')
        create_guest(db, invoice_no, name, address, email, NID, phone)
        flash('Guest created', 'success')
        return redirect(url_for('admin_guests'))
    return render_template('edit_guest.html', title='Create Guest', guest=None, invoices=invoices)


@app.route('/admin/guests/<int:guest_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_guest_edit(guest_id):
    db = get_db()
    cur = db.execute('SELECT guest_id, invoice_no, name, address, email, NID, phone FROM guests WHERE guest_id = ?', (guest_id,))
    g = cur.fetchone()
    if not g:
        flash('Guest not found', 'danger')
        return redirect(url_for('admin_guests'))
    invoices = db.execute('SELECT invoice_no FROM invoices ORDER BY issue_date DESC').fetchall()
    if request.method == 'POST':
        invoice_no = request.form.get('invoice_no') or None
        name = request.form.get('name')
        address = request.form.get('address')
        email = request.form.get('email')
        NID = request.form.get('NID')
        phone = request.form.get('phone')
        update_guest(db, guest_id, invoice_no, name, address, email, NID, phone)
        flash('Guest updated', 'success')
        return redirect(url_for('admin_guests'))
    return render_template('edit_guest.html', title='Edit Guest', guest=g, invoices=invoices)


@app.route('/admin/guests/<int:guest_id>/delete', methods=['POST'])
@admin_required
def admin_guest_delete(guest_id):
    db = get_db()
    delete_guest(db, guest_id)
    flash('Guest deleted', 'success')
    return redirect(url_for('admin_guests'))


def setup_db():
    # Initialize database and seed defaults. Not using
    # @app.before_first_request for compatibility with
    # older Flask versions/environments. Use an application
    # context so `g` and `get_db()` work during init.
    with app.app_context():
        init_db()
        create_first_admin()
        create_default_rooms()


# Run setup immediately so the DB exists whether the app is
# started directly or imported by a WSGI server.
setup_db()


@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)


def admin_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get('admin_id'):
            flash('Admin login required', 'danger')
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

@app.route('/')
def index():
    return render_template('index.html', title='Home')

@app.route('/about')
def about():
    return render_template('about.html', title='About')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # Here you would typically save this to a database or send an email
        # For now, we'll just flash a message
        flash(f'Thank you {name}, your message has been received!', 'success')
        return redirect(url_for('index'))
    
    return render_template('contact.html', title='Contact')

@app.route('/rooms')
def rooms():
    db = get_db()
    rooms = db.execute('SELECT id, name, description, price, image FROM rooms').fetchall()
    return render_template('rooms.html', title='Our Rooms', rooms=rooms)

@app.route('/booking/<int:room_id>', methods=['GET', 'POST'])
def booking(room_id):
    db = get_db()
    room = db.execute('SELECT id, name, description, price, image FROM rooms WHERE id = ?', (room_id,)).fetchone()
    if not room:
        flash('Room not found', 'danger')
        return redirect(url_for('rooms'))

    if request.method == 'POST':
        check_in = request.form.get('check_in_date')
        check_out = request.form.get('check_out_date')
        # If your app supports logged-in users, set `user_id` in session; otherwise leave NULL
        user_id = session.get('user_id') if session.get('user_id') else None
        guest_id = None

        from datetime import datetime
        created_at = datetime.utcnow().isoformat()

        db.execute(
            'INSERT INTO bookings (checkin_date, checkout_date, room_id, user_id, guest_id, reserved, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (check_in, check_out, room_id, user_id, guest_id, 1, created_at)
        )
        db.commit()
        flash(f'Your booking for {room["name"]} has been received!', 'success')
        return redirect(url_for('index'))

    return render_template('booking.html', title='Book a Room', room=room, room_id=room_id)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        cur = db.execute('SELECT * FROM users WHERE username = ? AND is_admin = 1', (username,))
        user = cur.fetchone()
        if user and check_password_hash(user['password'], password):
            session['admin_id'] = user['id']
            session['admin_username'] = user['username']
            flash('Logged in as admin', 'success')
            return redirect(url_for('admin_panel'))
        flash('Invalid credentials', 'danger')
    return render_template('admin_login.html', title='Admin Login')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out', 'success')
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    users = db.execute('''SELECT id, username, user_name, created_at, email, phone,
                                 admin_id, manager_id, managing_floor, receptionist_id, admin_type, is_admin
                          FROM users''').fetchall()
    return render_template('admin_panel.html', title='Admin Panel', users=users)


@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    db = get_db()
    bookings = db.execute('''
        SELECT b.booking_id, b.room_id, r.name as room_name, b.user_id, b.guest_id,
               b.checkin_date, b.checkout_date, b.checked_in, b.checked_out, b.reserved, b.cancelled, b.created_at
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        ORDER BY b.created_at DESC
    ''').fetchall()
    return render_template('admin_bookings.html', title='Bookings', bookings=bookings)


@app.route('/admin/bookings/<int:booking_id>/checkin', methods=['POST'])
@admin_required
def admin_booking_checkin(booking_id):
    db = get_db()
    mark_checked_in(db, booking_id)
    flash('Booking marked as checked in', 'success')
    return redirect(url_for('admin_bookings'))


@app.route('/admin/bookings/<int:booking_id>/checkout', methods=['POST'])
@admin_required
def admin_booking_checkout(booking_id):
    db = get_db()
    mark_checked_out(db, booking_id)
    flash('Booking marked as checked out', 'success')
    return redirect(url_for('admin_bookings'))


@app.route('/admin/bookings/<int:booking_id>/cancel', methods=['POST'])
@admin_required
def admin_booking_cancel(booking_id):
    db = get_db()
    cancel_booking(db, booking_id)
    flash('Booking cancelled', 'warning')
    return redirect(url_for('admin_bookings'))


@app.route('/admin/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_name = request.form.get('user_name') or None
        admin_id = request.form.get('admin_id') or None
        manager_id = request.form.get('manager_id') or None
        managing_floor = request.form.get('managing_floor') or None
        receptionist_id = request.form.get('receptionist_id') or None
        admin_type = request.form.get('admin_type') or None
        email = request.form.get('email')
        phone = request.form.get('phone')
        is_admin = 1 if request.form.get('is_admin') == 'on' else 0
        db = get_db()
        try:
            pw_hash = generate_password_hash(password)
            from datetime import datetime
            created_at = datetime.utcnow().isoformat()
            db.execute('INSERT INTO users (username, password, user_name, email, phone, is_admin, created_at, admin_id, manager_id, managing_floor, receptionist_id, admin_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (username, pw_hash, user_name, email, phone, is_admin, created_at, admin_id, manager_id, managing_floor, receptionist_id, admin_type))
            db.commit()
            flash('User created', 'success')
            return redirect(url_for('admin_panel'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'danger')
    return render_template('edit_user.html', title='Create User', user=None)


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    db = get_db()
    cur = db.execute('SELECT id, username, user_name, created_at, email, phone, admin_id, manager_id, managing_floor, receptionist_id, admin_type, is_admin FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('admin_panel'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_name = request.form.get('user_name') or None
        admin_id = request.form.get('admin_id') or None
        manager_id = request.form.get('manager_id') or None
        managing_floor = request.form.get('managing_floor') or None
        receptionist_id = request.form.get('receptionist_id') or None
        admin_type = request.form.get('admin_type') or None
        email = request.form.get('email')
        phone = request.form.get('phone')
        is_admin = 1 if request.form.get('is_admin') == 'on' else 0
        try:
            if password:
                pw_hash = generate_password_hash(password)
                db.execute('UPDATE users SET username = ?, password = ?, user_name = ?, email = ?, phone = ?, is_admin = ?, admin_id = ?, manager_id = ?, managing_floor = ?, receptionist_id = ?, admin_type = ? WHERE id = ?',
                           (username, pw_hash, user_name, email, phone, is_admin, admin_id, manager_id, managing_floor, receptionist_id, admin_type, user_id))
            else:
                db.execute('UPDATE users SET username = ?, user_name = ?, email = ?, phone = ?, is_admin = ?, admin_id = ?, manager_id = ?, managing_floor = ?, receptionist_id = ?, admin_type = ? WHERE id = ?',
                           (username, user_name, email, phone, is_admin, admin_id, manager_id, managing_floor, receptionist_id, admin_type, user_id))
            db.commit()
            flash('User updated', 'success')
            return redirect(url_for('admin_panel'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'danger')

    return render_template('edit_user.html', title='Edit User', user=user)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    db = get_db()
    # Prevent admin from deleting themselves
    if session.get('admin_id') == user_id:
        flash('You cannot delete the logged-in admin', 'danger')
        return redirect(url_for('admin_panel'))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash('User deleted', 'success')
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True)