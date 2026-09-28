"""
Əməkdaşların MÜQAVİLƏ NÖMRƏSİNƏ (M/n) görə RƏQƏM kimi (mətn kimi yox)
sıralanması üçün ortaq köməkçilər — bütün siyahılar (əməkdaşlar, tabel,
əməkhaqqı, hesabatlar, briqada və s.) EYNİ qaydanı istifadə etsin deyə bir
yerdə saxlanılır.

Qayda (bax: contract_sort_key):
  1. Rəqəmlə başlayan nömrələr (\"9\", \"10\", \"845\", \"845/1\") — əvvəlcə,
     ƏDƏD kimi: 9 < 10 < 845 (mətn kimi \"10\" < \"9\" olardı). Eyni ədəddə
     qalan hissə (\"845\" < \"845/1\") ikinci meyar.
  2. Rəqəmlə başlamayan mətn nömrələri (\"C-0001-2026\") — sonra, əlifba
     sırası ilə.
  3. Müqavilə nömrəsi olmayanlar — ən sonda.
Eyni nömrəli əməkdaşlar arasında sıra ad-soyada görə (sabit nəticə üçün).
"""

import re
from datetime import date

_LEADING_NUMBER = re.compile(r"^(\d+)(.*)$")


def contract_sort_key(contract_number):
    """Müqavilə N-i üçün sıralama açarı (bax: modul docstring-i)."""
    if contract_number is None:
        return (2, 0, "")
    s = str(contract_number).strip()
    if not s:
        return (2, 0, "")
    m = _LEADING_NUMBER.match(s)
    if m:
        return (0, int(m.group(1)), m.group(2).strip().casefold())
    return (1, 0, s.casefold())


def contract_numbers_by_employee(employee_ids, as_of_date=None):
    """`{employee_id: müqavilə N}` — HƏR əməkdaş üçün `as_of_date`-də
    (defolt: bu gün) qüvvədə olan Bildirişin müqavilə nömrəsi (başlama
    tarixi ən yaxın olan, ondan kiçik/bərabər). Belə Bildiriş yoxdursa
    (məs. yalnız gələcək tarixli varsa) — ən erkən olan götürülür ki,
    əməkdaş \"nömrəsiz\" sayılmasın. Bütün əməkdaşlar üçün TƏK sorğu."""
    from app.models import EmploymentContractNotification

    as_of_date = as_of_date or date.today()
    ids = [i for i in employee_ids if i is not None]
    if not ids:
        return {}
    rows = (
        EmploymentContractNotification.query
        .filter(EmploymentContractNotification.employee_id.in_(ids))
        .order_by(
            EmploymentContractNotification.start_date.asc(),
            EmploymentContractNotification.created_at.asc(),
            EmploymentContractNotification.id.asc(),
        )
        .all()
    )
    result = {}
    earliest = {}
    for n in rows:
        if n.contract_number is None or not str(n.contract_number).strip():
            continue  # nömrəsiz bildiriş qüvvədə olan nömrəni pozmasın
        earliest.setdefault(n.employee_id, n.contract_number)
        if n.start_date is not None and n.start_date <= as_of_date:
            result[n.employee_id] = n.contract_number  # ən son (ən yeni) qalır
    for emp_id, number in earliest.items():
        result.setdefault(emp_id, number)
    return result


def sort_employees_by_contract(employees, as_of_date=None, numbers=None):
    """Əməkdaş obyektlərini müqavilə N-ə (ədəd kimi) görə düzür. `numbers`
    (contract_numbers_by_employee nəticəsi) verilməyibsə özü tapır."""
    employees = list(employees)
    if numbers is None:
        numbers = contract_numbers_by_employee([e.id for e in employees], as_of_date)
    return sorted(
        employees,
        key=lambda e: (contract_sort_key(numbers.get(e.id)), (e.full_name or "").casefold(), e.id or 0),
    )


def sort_rows_by_contract(rows, number_getter, name_getter=None):
    """Ümumi variant: sətirləri `number_getter(row)` (müqavilə N) ədəd kimi,
    sonra `name_getter(row)` (ad) görə düzür."""
    return sorted(
        rows,
        key=lambda r: (
            contract_sort_key(number_getter(r)),
            ((name_getter(r) if name_getter else "") or "").casefold(),
        ),
    )
