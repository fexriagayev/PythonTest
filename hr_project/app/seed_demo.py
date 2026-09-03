"""
Test məlumat generatoru — İNTERFEYSİ YOXLAMAQ ÜÇÜN 100 nümunə əməkdaş
(iş yeri qeydi + müqavilə bildirişi ilə) və onlar üçün generasiya olunmuş
bir Tabel dövrü yaradır.

İşə salmaq üçün:
    flask --app run.py seed-demo
    flask --app run.py seed-demo --count 200 --year 2026 --month 8
"""

import random
from datetime import date, timedelta

from app import db
from app.models import (
    Employee,
    EmploymentRecord,
    EmploymentContractNotification,
    DictionaryItem,
    TabelPeriod,
)
from app.services.hr_service import recompute_employee_from_history
from app.services.tabel_service import generate_period

FIRST_NAMES = [
    "Elvin", "Rəşad", "Tural", "Kamran", "Nicat", "Orxan", "Vüqar", "Elşən",
    "Fərid", "Anar", "Emin", "Rüfət", "Samir", "Ceyhun", "Elnur", "Kənan",
    "Aynur", "Günel", "Leyla", "Nərmin", "Sevinc", "Türkan", "Zeynəb",
    "Fidan", "Gülnar", "Xatirə", "Lalə", "Məlahət", "Nigar", "Rəna",
]
LAST_NAMES = [
    "Məmmədov", "Əliyev", "Hüseynov", "Quliyev", "İsmayılov", "Həsənov",
    "Rəhimov", "Kərimov", "Vəliyev", "Abbasov", "Cəfərov", "Nəbiyev",
    "Sadıqov", "Babayev", "Orucov", "Əhmədov", "Ağayev", "Yusifov",
]
PATRONYMICS = [
    "Elman oğlu", "Rasim oğlu", "Vaqif oğlu", "Fikrət oğlu", "Ceyhun oğlu",
    "Səməd oğlu", "Elman qızı", "Vaqif qızı", "Fikrət qızı", "Rasim qızı",
]


def _random_full_name():
    return f"{random.choice(LAST_NAMES)} {random.choice(FIRST_NAMES)} {random.choice(PATRONYMICS)}"


def seed_demo_data(employee_count=100, period_year=None, period_month=None):
    """Creates `employee_count` sample employees (each with one current-
    company EmploymentRecord + one EmploymentContractNotification, hire
    dates spread over the last ~3 years so some employees are active for
    only part of the target period), then generates a Tabel period for
    period_year/period_month (defaults to the current month). Returns
    (created_employee_count, period)."""

    departments = DictionaryItem.query.filter_by(category="department").all()
    positions = DictionaryItem.query.filter_by(category="position").all()
    if not departments or not positions:
        raise RuntimeError(
            "Əvvəlcə əsas seed işə salınmalıdır (flask --app run.py seed)."
        )

    today = date.today()
    period_year = period_year or today.year
    period_month = period_month or today.month
    period_first_day = date(period_year, period_month, 1)

    created = []
    for i in range(employee_count):
        employee = Employee(full_name=_random_full_name())
        db.session.add(employee)
        db.session.flush()

        # Hire dates spread from ~3 years ago up to a few days into the
        # target period, so the generated Tabel has a realistic mix of
        # full-month and partial-month (mid-period hire) employees.
        hire_date = period_first_day - timedelta(days=random.randint(-5, 3 * 365))

        db.session.add(
            EmploymentRecord(
                employee_id=employee.id,
                is_current_company=True,
                movement_type="hire",
                department_id=random.choice(departments).id,
                position_id=random.choice(positions).id,
                date_from=hire_date,
            )
        )
        db.session.add(
            EmploymentContractNotification(
                employee_id=employee.id,
                number=str(1000 + i),
                start_date=hire_date,
                contract_number=str(100 + i),
            )
        )
        created.append(employee)

    db.session.flush()
    for employee in created:
        recompute_employee_from_history(employee)

    period = TabelPeriod.query.filter_by(year=period_year, month=period_month).first()
    if not period:
        period = TabelPeriod(year=period_year, month=period_month)
        db.session.add(period)
        db.session.flush()
    if not period.is_approved:
        generate_period(period)

    db.session.commit()
    return len(created), period
