"""
Test məlumat generatoru — İNTERFEYSİ YOXLAMAQ ÜÇÜN N ədəd nümunə əməkdaş
(tam iş yeri tarixçəsi: işə qəbul əmri, bəzilərində 1-2 vəzifə dəyişikliyi,
bəzilərində işdən çıxma — hamısı müvafiq Əmr (Order) və tam doldurulmuş
Bildiriş (EmploymentContractNotification, kateqoriya+maaş daxil) qeydləri
ilə dəstəklənir) və onların iş tarixçəsinə uyğun BÜTÜN aylar üçün
generasiya olunmuş Tabel dövrləri yaradır.

İşə salmaq üçün:
    flask --app run.py seed-demo
    flask --app run.py seed-demo --count 200 --months-back 18
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from app import db
from app.models import (
    Employee,
    EmploymentRecord,
    EmploymentContractNotification,
    Order,
    DictionaryItem,
    LeaveCategory,
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

ORDER_TYPE_HIRE = "İşə qəbul əmri"
ORDER_TYPE_TRANSFER = "Vəzifə dəyişikliyi əmri"
ORDER_TYPE_TERMINATION = "İşdən azad etmə əmri"


def _random_full_name():
    return f"{random.choice(LAST_NAMES)} {random.choice(FIRST_NAMES)} {random.choice(PATRONYMICS)}"


def _dict_items(category):
    items = DictionaryItem.query.filter_by(category=category).all()
    if not items:
        raise RuntimeError(
            f"'{category}' kitabçası boşdur — əvvəlcə əsas seed işə salınmalıdır "
            "(flask --app run.py seed)."
        )
    return items


class _DemoContext:
    """Bir dəfə yüklənən dictionary/kateqoriya siyahıları — hər əməkdaş
    üçün təkrar sorğu getməsin deyə."""

    def __init__(self):
        self.departments = _dict_items("department")
        self.positions = _dict_items("position")
        self.order_types = {o.name: o for o in _dict_items("order_type")}
        self.employment_classifications = _dict_items("employment_classification")
        self.employment_positions = _dict_items("employment_position")
        self.contract_types = _dict_items("contract_type")
        self.work_types = _dict_items("work_type")
        self.labor_types = _dict_items("labor_type")
        self.leave_categories = LeaveCategory.query.all()
        if not self.leave_categories:
            raise RuntimeError(
                "Kateqoriyalar boşdur — əvvəlcə əsas seed işə salınmalıdır "
                "(flask --app run.py seed)."
            )
        self._order_seq = 0
        self._notif_seq = 0

    def next_order_number(self):
        self._order_seq += 1
        return f"{self._order_seq:04d}"

    def next_notification_number(self):
        self._notif_seq += 1
        return f"BLD-{self._notif_seq:05d}"


def _make_order(ctx, order_type_name, event_date):
    order_type = ctx.order_types.get(order_type_name)
    order = Order(
        number=ctx.next_order_number(),
        order_date=event_date,
        effective_date=event_date,
        order_type_id=order_type.id if order_type else None,
    )
    db.session.add(order)
    db.session.flush()
    return order


def _make_notification(ctx, employee, order, event_date, hire_date, base_salary):
    """Bir 'Bildiriş' (DSMF) qeydi — bütün sahələr doldurulmuş: kateqoriya
    (leave_category_id) və maaş (salary) daxil olmaqla."""
    is_fixed_term = random.random() < 0.3
    notification = EmploymentContractNotification(
        employee_id=employee.id,
        number=ctx.next_notification_number(),
        start_date=event_date,
        order_id=order.id,
        employment_classification_id=random.choice(ctx.employment_classifications).id,
        employment_position_id=random.choice(ctx.employment_positions).id,
        contract_number=f"C-{employee.id:04d}-{event_date.year}",
        contract_type_id=random.choice(ctx.contract_types).id,
        contract_start_date=hire_date,
        contract_end_date=(
            hire_date + timedelta(days=random.randint(365, 3 * 365))
            if is_fixed_term
            else None
        ),
        work_type_id=random.choice(ctx.work_types).id,
        labor_type_id=random.choice(ctx.labor_types).id,
        leave_category_id=random.choice(ctx.leave_categories).id,
        salary=Decimal(base_salary).quantize(Decimal("0.01")),
    )
    db.session.add(notification)


def _build_employee_history(ctx, employee, hire_date, today):
    """Bir əməkdaş üçün: işə qəbul + (ehtimal) 1-2 vəzifə dəyişikliyi +
    (ehtimal) işdən çıxma — hər addımda müvafiq Order + tam Bildiriş."""
    salary = float(random.randint(400, 1800))

    hire_order = _make_order(ctx, ORDER_TYPE_HIRE, hire_date)
    db.session.add(
        EmploymentRecord(
            employee_id=employee.id,
            is_current_company=True,
            movement_type="hire",
            department_id=random.choice(ctx.departments).id,
            position_id=random.choice(ctx.positions).id,
            order_id=hire_order.id,
            date_from=hire_date,
        )
    )
    _make_notification(ctx, employee, hire_order, hire_date, hire_date, salary)

    # Bir hissəsində (~35%) 1-2 vəzifə dəyişikliyi (transfer) olsun.
    last_event_date = hire_date
    terminate = random.random() < 0.2
    # Son hadisə tarixi bu iki aralıqdan birində olmalıdır (ya bu gün, ya
    # da işdən çıxma tarixindən əvvəl) — transfer tarixlərini bunun
    # içində seçirik.
    latest_possible = today - timedelta(days=random.randint(0, 20)) if terminate else today

    if random.random() < 0.35 and (latest_possible - hire_date).days > 60:
        transfer_count = random.choice([1, 1, 2])
        for _ in range(transfer_count):
            remaining_days = (latest_possible - last_event_date).days
            if remaining_days <= 30:
                break
            transfer_date = last_event_date + timedelta(days=random.randint(30, remaining_days - 1))
            transfer_order = _make_order(ctx, ORDER_TYPE_TRANSFER, transfer_date)
            salary = salary * random.uniform(1.05, 1.25)  # vəzifə dəyişikliyi ilə maaş artımı
            db.session.add(
                EmploymentRecord(
                    employee_id=employee.id,
                    is_current_company=True,
                    movement_type="transfer",
                    department_id=random.choice(ctx.departments).id,
                    position_id=random.choice(ctx.positions).id,
                    order_id=transfer_order.id,
                    date_from=transfer_date,
                )
            )
            _make_notification(ctx, employee, transfer_order, transfer_date, hire_date, salary)
            last_event_date = transfer_date

    if terminate:
        remaining_days = (today - last_event_date).days
        if remaining_days > 5:
            termination_date = last_event_date + timedelta(days=random.randint(5, remaining_days))
            termination_order = _make_order(ctx, ORDER_TYPE_TERMINATION, termination_date)
            db.session.add(
                EmploymentRecord(
                    employee_id=employee.id,
                    is_current_company=True,
                    movement_type="termination",
                    order_id=termination_order.id,
                    date_from=termination_date,
                )
            )


def seed_demo_data(employee_count=100, months_back=12):
    """N ədəd nümunə əməkdaş (tam iş tarixçəsi ilə) yaradır, sonra ən erkən
    işə qəbul tarixindən bu günə qədər OLAN HƏR AY üçün bir Tabel dövrü
    yaradıb generasiya edir. Returns (created_employee_count, period_count)."""

    ctx = _DemoContext()
    today = date.today()
    earliest_hire = today - timedelta(days=30 * months_back)

    created = []
    for _ in range(employee_count):
        employee = Employee(full_name=_random_full_name())
        db.session.add(employee)
        db.session.flush()

        hire_date = earliest_hire + timedelta(
            days=random.randint(0, max((today - earliest_hire).days - 5, 1))
        )
        _build_employee_history(ctx, employee, hire_date, today)
        created.append(employee)

    db.session.flush()
    for employee in created:
        recompute_employee_from_history(employee)
    db.session.commit()

    # --- Qeydiyyata alınmış əməkdaşlara uyğun BÜTÜN dövrlər üçün Tabel ------
    period_count = 0
    cursor_year, cursor_month = earliest_hire.year, earliest_hire.month
    while (cursor_year, cursor_month) <= (today.year, today.month):
        period = TabelPeriod.query.filter_by(year=cursor_year, month=cursor_month).first()
        if not period:
            period = TabelPeriod(year=cursor_year, month=cursor_month)
            db.session.add(period)
            db.session.flush()
        if not period.is_approved:
            generate_period(period)
            period_count += 1

        cursor_month += 1
        if cursor_month > 12:
            cursor_month = 1
            cursor_year += 1

    db.session.commit()
    return len(created), period_count
