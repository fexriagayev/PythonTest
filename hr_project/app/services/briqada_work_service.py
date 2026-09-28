"""
"Obyektlər üzrə görülən işlər" matrisi — briqada üzvlərinin ay ərzində
hansı obyektdə gördükləri işə görə nə qədər pul aldıqlarını qeyd etmək
üçün. Ay ərzində İKİ DƏFƏ doldurulur (avans/yekun — bax:
BriqadaWorkPeriod) və hər dəfə AYRICA təsdiqlənir.

Struktur (bax: matrix_data()):
  - SÜTUNLAR: hər ƏSAS obyekt (owner_id=None) öz qrupu — daxilində
    prioritet üzrə ALT obyektləri, sonda o qrupun "Cəmi" sütunu. Bütün
    qruplardan sonra ümumi "Yekun" sütunu.
  - SƏTİRLƏR: dövrün ili/ayında AKTİV olan HƏR ƏMƏKDAŞ öz sətri, Müqavilə
    N-ə görə sıralanıb (bax: matrix_row_structure() / _contract_sort_key
    — bu, tabel_service-in "aktiv əməkdaş" təyinatı ilə EYNİDİR).
    Əgər həmin əməkdaş bir briqadanın RƏHBƏRİDİRSƏ (bax:
    Briqada.header_id), onun sətri bir BLOKA çevrilir: öz adı/müqavilə
    N-i o blokun bütün sətirləri boyunca (vizual olaraq) yayılır;
    blokun İLK sətri RƏHBƏRİN ÖZÜNÜN (redaktə oluna bilən) sətridir,
    sonra komandasının HƏR ÜZVÜ (yenə Müqavilə N-ə görə sıralanıb) öz
    sətrində, ən sonda "Cəmi" sətri.
  - XANALAR: YALNIZ (adi əməkdaş sətri) VƏ YA (komanda üzvü sətri) x
    (yarpaq obyekt sütunu) xanaları əl ilə redaktə olunur — "Cəmi"/
    "Yekun" sətir və sütunları HƏMİŞƏ avtomatik hesablanır.

Xananın "sahibi" iki cür ola bilər (bax: BriqadaWorkEntry):
  - bir komanda üzvü sətri  -> ("briqada", Briqada.id)
  - heç bir komandaya daxil olmayan, sadəcə aktiv bir əməkdaş sətri
    -> ("employee", Employee.id)
"""

from app import db
from app.models import Obyekt, Briqada, BriqadaWorkEntry
from app.services.tabel_service import (
    month_bounds,
    _employees_with_current_stint,
    _active_days,
    _contract_number_at,
)


def obyekt_column_structure():
    """[{obyekt, sub: [obyekt, ...]}, ...] — əsas obyektlər (owner_id
    yoxdur) prioritetə görə, hər birinin öz alt-obyektləri (prioritetə
    görə) daxilində. Yalnız aktiv (is_active=True) obyektlər."""
    mains = (
        Obyekt.query.filter_by(is_active=True, owner_id=None)
        .order_by(Obyekt.priority.desc(), Obyekt.name)
        .all()
    )
    result = []
    for main in mains:
        subs = sorted(
            [o for o in main.sub_obyekts if o.is_active],
            key=lambda o: (-o.priority, o.name),
        )
        result.append({"obyekt": main, "sub": subs})
    return result


def leaf_obyekt_ids(columns):
    """Sütun strukturundakı BÜTÜN yarpaq (redaktə olunan) obyekt ID-lərini
    düz siyahı kimi qaytarır (əsas obyektin özü DƏ yarpaqdır — alt-
    obyekti olmasa belə ora birbaşa iş yazıla bilər)."""
    ids = []
    for col in columns:
        ids.append(col["obyekt"].id)
        for sub in col["sub"]:
            ids.append(sub.id)
    return ids


def _contract_sort_key(contract_number):
    """Müqavilə N-ə görə sıralama açarı — RƏQƏMSƏ (məs. "845") ədəd kimi
    düzgün sıralansın deyə sıfırla soldan doldurulur (yoxsa "9" > "10"
    kimi mətn-sıralama səhvi olardı); mətn-qarışıq dəyərlər olduğu kimi
    saxlanılır. Müqavilə N-i olmayanlar (None) siyahının SONUNA düşür."""
    if not contract_number:
        return "\uffff"  # ən sona düşsün
    s = str(contract_number).strip()
    return s.zfill(12) if s.isdigit() else s


def _active_employees_for_period(period):
    """Dövrün ili/ayında ən azı bir aktiv günü olan bütün əməkdaşlar,
    Müqavilə N-ə görə sıralanıb (bax: _contract_sort_key) — tabel_service-
    dəki "aktiv əməkdaş" məntiqi ilə EYNİ (bax:
    app.services.tabel_service._employees_with_current_stint /
    _active_days), ki, hər iki modulda "aktiv" eyni şey demək olsun."""
    period_start, period_end, _ = month_bounds(period.year, period.month)
    employees = [
        e for e in _employees_with_current_stint()
        if _active_days(e, period_start, period_end)
    ]
    return sorted(
        employees,
        key=lambda e: _contract_sort_key(_contract_number_at(e, period_end)),
    )


def _leader_groups(active_employee_ids, period_end):
    """{header_id: [Briqada üzv sətri, ...]} — YALNIZ aktiv briqadalar,
    boş "yer tutucu" sətirlər xaric (bax: Briqada modeli), HƏR QRUPUN
    daxilində Müqavilə N-ə görə sıralanıb (bax: _contract_sort_key —
    sistemdə qeydiyyatı olmayan sərbəst/mətn üzvlər, müqavilə N-i
    olmadığı üçün, siyahının sonuna düşür). `member_id`-si olan
    (sistemdəki əməkdaşa bağlı) bir üzv bu dövrdə AKTİV DEYİLSƏ (işdən
    çıxıb və s. — bax: _active_employees_for_period), SİYAHIDAN
    ÇIXARILIR ki, təsadüfən işdən çıxmış əməkdaşa iş/maya yazılmasın."""
    rows = Briqada.query.filter_by(is_active=True).all()
    groups = {}
    for r in rows:
        if not (r.member_id or r.member_name):
            continue  # boş yer tutucu — matriksdə sətir kimi görünmür
        if r.member_id is not None and r.member_id not in active_employee_ids:
            continue  # işdən çıxmış/bu dövrdə aktiv olmayan əməkdaş — göstərilmir
        groups.setdefault(r.header_id, []).append(r)
    for header_id, members in groups.items():
        members.sort(
            key=lambda r: _contract_sort_key(
                _contract_number_at(r.member, period_end) if r.member else None
            )
        )
    return groups


def matrix_row_structure(period):
    """Dövr üçün sətir strukturu: hər aktiv əməkdaş üçün bir "blok":
      {"employee": Employee, "members": None}                — adi sətir
      {"employee": Employee, "members": [Briqada üzv sətri, ...]} — rəhbər bloku
    """
    _, period_end, _ = month_bounds(period.year, period.month)
    employees = _active_employees_for_period(period)
    active_ids = {e.id for e in employees}
    leader_groups = _leader_groups(active_ids, period_end)
    return [
        {"employee": emp, "members": leader_groups.get(emp.id) or None}
        for emp in employees
    ]


def _leaf_row_keys(rows):
    """Bütün redaktə oluna bilən sətir açarlarını ("briqada"|"employee", id)
    düz siyahı kimi qaytarır — Cəmi/Yekun hesablamaları üçün."""
    keys = []
    for row in rows:
        if row["members"]:
            keys.extend(("briqada", m.id) for m in row["members"])
        else:
            keys.append(("employee", row["employee"].id))
    return keys


def matrix_data(period):
    """Bu dövr üçün TAM matris məlumatını (frontend-ə JSON kimi
    ötürüləcək formada) qaytarır: sütun/sətir strukturu + hər xananın
    dəyəri + avtomatik hesablanan Cəmi/Yekun."""
    columns = obyekt_column_structure()
    leaf_ids = leaf_obyekt_ids(columns)
    rows = matrix_row_structure(period)

    _, period_end, _ = month_bounds(period.year, period.month)

    entries = (
        BriqadaWorkEntry.query.filter_by(period_id=period.id).all()
        if period.id else []
    )
    values = {}
    for e in entries:
        if e.briqada_id is not None:
            values[("briqada", e.briqada_id, e.obyekt_id)] = float(e.amount or 0)
        elif e.employee_id is not None:
            values[("employee", e.employee_id, e.obyekt_id)] = float(e.amount or 0)

    def cell(kind, key_id, obyekt_id):
        return values.get((kind, key_id, obyekt_id), 0.0)

    out_columns = []
    for col in columns:
        main = col["obyekt"]
        out_columns.append({
            "obyekt_id": main.id,
            "name": main.name,
            "sub": [{"obyekt_id": s.id, "name": s.name} for s in col["sub"]],
        })

    out_rows = []
    yekun_by_obyekt = {oid: 0.0 for oid in leaf_ids}
    yekun_total = 0.0
    for row in rows:
        emp = row["employee"]
        contract_number = _contract_number_at(emp, period_end)
        if row["members"]:
            member_rows = []
            group_totals = {oid: 0.0 for oid in leaf_ids}

            # Rəhbərin ÖZ sətri — siyahının BİRİNCİ sətri. Onun heç bir
            # Briqada üzv sətri (Briqada.id) yoxdur, ona görə "employee"
            # açarı ilə saxlanılır (bax: standalone əməkdaş sətirləri
            # ilə EYNİ mexanizm — set_cell(..., "employee", emp.id, ...)).
            leader_cells = {oid: cell("employee", emp.id, oid) for oid in leaf_ids}
            for oid, v in leader_cells.items():
                group_totals[oid] += v
                yekun_by_obyekt[oid] += v
            leader_row_total = round(sum(leader_cells.values()), 2)
            yekun_total += leader_row_total
            member_rows.append({
                "briqada_id": None,
                "employee_id": emp.id,
                "name": emp.full_name,
                "is_freeform": False,
                "is_leader_self": True,
                "cells": leader_cells,
                "row_total": leader_row_total,
            })

            for m in row["members"]:
                row_cells = {oid: cell("briqada", m.id, oid) for oid in leaf_ids}
                for oid, v in row_cells.items():
                    group_totals[oid] += v
                    yekun_by_obyekt[oid] += v
                row_total = round(sum(row_cells.values()), 2)
                yekun_total += row_total
                member_rows.append({
                    "briqada_id": m.id,
                    "employee_id": None,
                    "name": m.member_display_name(),
                    "is_freeform": m.member_id is None,
                    "is_leader_self": False,
                    "cells": row_cells,
                    "row_total": row_total,
                })
            out_rows.append({
                "employee_id": emp.id,
                "contract_number": contract_number,
                "full_name": emp.full_name,
                "is_leader": True,
                "members": member_rows,
                "group_totals": {oid: round(v, 2) for oid, v in group_totals.items()},
                "group_total": round(sum(group_totals.values()), 2),
            })
        else:
            row_cells = {oid: cell("employee", emp.id, oid) for oid in leaf_ids}
            for oid, v in row_cells.items():
                yekun_by_obyekt[oid] += v
            row_total = round(sum(row_cells.values()), 2)
            yekun_total += row_total
            out_rows.append({
                "employee_id": emp.id,
                "contract_number": contract_number,
                "full_name": emp.full_name,
                "is_leader": False,
                "cells": row_cells,
                "row_total": row_total,
            })

    return {
        "columns": out_columns,
        "rows": out_rows,
        "yekun_by_obyekt": {oid: round(v, 2) for oid, v in yekun_by_obyekt.items()},
        "yekun_total": round(yekun_total, 2),
        "is_approved": period.is_approved,
    }


def set_cell(period, key_type, key_id, obyekt_id, amount):
    """Bu dövrdə (key_type, key_id, obyekt_id) xanasının dəyərini yazır
    (upsert). `key_type` "briqada" (komanda üzvü — Briqada.id) VƏ YA
    "employee" (heç bir komandaya daxil olmayan aktiv əməkdaş —
    Employee.id) ola bilər. Dövr təsdiqlənibsə, çağıran tərəf (route)
    bunu ƏVVƏLCƏDƏN yoxlamalıdır — bu funksiya özü təsdiq statusunu
    yoxlamır (test/skript istifadəsi üçün sərbəst saxlanılıb,
    HTTP-səviyyəli qorunma routes.py-dədir)."""
    filters = {"period_id": period.id, "obyekt_id": obyekt_id}
    if key_type == "briqada":
        filters["briqada_id"] = key_id
    else:
        filters["employee_id"] = key_id
    entry = BriqadaWorkEntry.query.filter_by(**filters).first()
    amount = round(float(amount or 0), 2)
    if entry:
        entry.amount = amount
    else:
        db.session.add(BriqadaWorkEntry(amount=amount, **filters))
