"""
"Obyektlər üzrə görülən işlər" matrisi — briqada üzvlərinin ay ərzində
hansı obyektdə gördükləri işə görə nə qədər pul aldıqlarını qeyd etmək
üçün. Ay ərzində İKİ DƏFƏ doldurulur (avans/yekun — bax:
BriqadaWorkPeriod) və hər dəfə AYRICA təsdiqlənir.

Struktur (bax: matrix_structure()):
  - SÜTUNLAR: hər ƏSAS obyekt (owner_id=None) öz qrupu — daxilində
    prioritet üzrə ALT obyektləri, sonda o qrupun "Cəmi" sütunu. Bütün
    qruplardan sonra ümumi "Yekun" sütunu.
  - SƏTİRLƏR: hər briqada (group_no üzrə qruplaşdırılıb) — daxilində
    üzvləri, sonda o briqadanın "Cəmi" sətri. Bütün briqadalardan sonra
    ümumi "Yekun" sətri.
  - XANALAR: YALNIZ (adi üzv sətri) x (yarpaq obyekt sütunu) xanaları
    əl ilə redaktə olunur — "Cəmi"/"Yekun" sətir və sütunları HƏMİŞƏ
    avtomatik hesablanır (bax: _compute_totals()).
"""

from app import db
from app.models import Obyekt, Briqada, BriqadaWorkEntry


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


def briqada_row_structure():
    """[{group_no, header, members: [briqada_row, ...]}, ...] — briqadalar
    prioritetə görə, hər birinin üzvləri (boş "yer tutucu" sətirlər
    xaric — bax: Briqada modeli). Yalnız aktiv (is_active=True)
    briqadalar."""
    rows = (
        Briqada.query.filter_by(is_active=True)
        .order_by(Briqada.priority.desc(), Briqada.group_no.desc(), Briqada.id)
        .all()
    )
    groups = {}
    order = []
    for r in rows:
        if not (r.member_id or r.member_name):
            continue  # boş yer tutucu — matriksdə sətir kimi görünmür
        if r.group_no not in groups:
            groups[r.group_no] = {"group_no": r.group_no, "header": r.header, "members": []}
            order.append(r.group_no)
        groups[r.group_no]["members"].append(r)
    return [groups[g] for g in order]


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


def matrix_data(period):
    """Bu dövr üçün TAM matris məlumatını (frontend-ə JSON kimi
    ötürüləcək formada) qaytarır: sütun/sətir strukturu + hər xananın
    dəyəri + avtomatik hesablanan Cəmi/Yekun."""
    columns = obyekt_column_structure()
    rows = briqada_row_structure()
    leaf_ids = leaf_obyekt_ids(columns)

    entries = (
        BriqadaWorkEntry.query.filter_by(period_id=period.id).all()
        if period.id else []
    )
    values = {(e.briqada_id, e.obyekt_id): float(e.amount or 0) for e in entries}

    def cell(briqada_id, obyekt_id):
        return values.get((briqada_id, obyekt_id), 0.0)

    def row_cemi(briqada_id):
        return round(sum(cell(briqada_id, oid) for oid in leaf_ids), 2)

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
    for grp in rows:
        member_rows = []
        group_totals_by_obyekt = {oid: 0.0 for oid in leaf_ids}
        for m in grp["members"]:
            row_cells = {oid: cell(m.id, oid) for oid in leaf_ids}
            for oid, v in row_cells.items():
                group_totals_by_obyekt[oid] += v
                yekun_by_obyekt[oid] += v
            row_total = round(sum(row_cells.values()), 2)
            yekun_total += row_total
            member_rows.append({
                "briqada_id": m.id,
                "name": m.member_display_name(),
                "cells": row_cells,
                "row_total": row_total,
            })
        out_rows.append({
            "group_no": grp["group_no"],
            "header_name": grp["header"].full_name if grp["header"] else None,
            "members": member_rows,
            "group_totals": {oid: round(v, 2) for oid, v in group_totals_by_obyekt.items()},
            "group_total": round(sum(group_totals_by_obyekt.values()), 2),
        })

    return {
        "columns": out_columns,
        "rows": out_rows,
        "yekun_by_obyekt": {oid: round(v, 2) for oid, v in yekun_by_obyekt.items()},
        "yekun_total": round(yekun_total, 2),
        "is_approved": period.is_approved,
    }


def set_cell(period, briqada_id, obyekt_id, amount):
    """Bu dövrdə (briqada_id, obyekt_id) xanasının dəyərini yazır (upsert).
    Dövr təsdiqlənibsə, çağıran tərəf (route) bunu ƏVVƏLCƏDƏN yoxlamalıdır
    — bu funksiya özü təsdiq statusunu yoxlamır (test/skript istifadəsi
    üçün sərbəst saxlanılıb, HTTP-səviyyəli qorunma routes.py-dədir)."""
    entry = BriqadaWorkEntry.query.filter_by(
        period_id=period.id, briqada_id=briqada_id, obyekt_id=obyekt_id
    ).first()
    amount = round(float(amount or 0), 2)
    if entry:
        entry.amount = amount
    else:
        db.session.add(BriqadaWorkEntry(
            period_id=period.id, briqada_id=briqada_id, obyekt_id=obyekt_id, amount=amount,
        ))
