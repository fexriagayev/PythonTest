from app import db
from app.models import Module, User, Permission, DictionaryItem, LeaveCategory, LeaveReason

MODULES = [
    ("HR", "HR", "HR"),
    ("TABEL", "Tabel", "Timesheet"),
    ("SALARY", "Salary", "Salary"),
]

# Initial HR dictionary values — these power every combobox on the
# "Yeni əməkdaş" (add employee) form. Admin can add/edit/delete more of
# these later from Məlumat kitabçaları → HR.
HR_DICTIONARIES = {
    "gender": ["Kişi", "Qadın"],
    "family_status": ["Subay", "Evli", "Boşanmış", "Dul"],
    "education_type": ["Orta", "Orta-ixtisas", "Natamam ali", "Ali", "Elmi dərəcə"],
    "benefits": [
        "Əlillik üzrə güzəşt",
        "Çoxuşaqlı ailə",
        "Veteran",
        "Çernobıl AES qəzası iştirakçısı",
        "Şəhid ailəsi üzvü",
    ],
    "department": [
        "Baş direktor aparatı",
        "Maliyyə şöbəsi",
        "Kadrlar şöbəsi",
        "İT şöbəsi",
        "Satış şöbəsi",
        "Anbar",
    ],
    "position": [
        "Baş direktor",
        "Şöbə müdiri",
        "Mühasib",
        "İT mütəxəssisi",
        "Satış meneceri",
        "Anbardar",
    ],
    "order_type": [
        "İşə qəbul əmri",
        "Vəzifə dəyişikliyi əmri",
        "Struktur dəyişikliyi əmri",
        "İşdən azad etmə əmri",
        "Ezamiyyət əmri",
    ],
    # --- Bildirişlər (DSMF) dictionaries -----------------------------------
    "employment_classification": [
        "Əsas iş yeri",
        "Əvəzçilik",
        "Müvəqqəti əvəzetmə",
    ],
    "employment_position": [
        "Baş direktor",
        "Şöbə müdiri",
        "Mühasib",
        "Mütəxəssis",
        "Fəhlə",
    ],
    "contract_type": [
        "Müddətsiz əmək müqaviləsi",
        "Müddətli əmək müqaviləsi",
        "Mülki-hüquqi müqavilə",
    ],
    "work_type": [
        "Əsas iş",
        "Əlavə iş (əvəzçilik)",
    ],
    "labor_type": [
        "Tam ştat",
        "Yarım ştat",
        "Uzaqdan iş",
    ],
    "insurance_company": [
        "PAŞA Sığorta",
        "AtaSığorta",
        "Azərbaycan Sənaye Sığorta",
    ],
    "insurance_type": [
        "Tibbi sığorta",
        "Həyat sığortası",
        "Bədən xəsarəti sığortası",
    ],
    "bank": [
        "Kapital Bank",
        "PAŞA Bank",
        "ABB",
    ],
    "document_type": [
        "Şəxsiyyət vəsiqəsi",
        "Sürücülük vəsiqəsi",
        "Diplom",
        "Digər",
    ],
}

# Sample vacation-day categories (Bildirişlər → Hissə 5). Admin can add
# more from the "Kateqoriyalar" menu item.
LEAVE_CATEGORIES = [
    # name, base_days, years_per_bonus, bonus_days, max_bonus_days
    ("Dövlət qulluqçusu", 30, 5, 2, 6),
    ("Veteran", 46, 0, 0, 0),
    ("Ümumi qayda", 21, 0, 0, 0),
]

# name, counting_method, is_annual_leave
LEAVE_REASONS = [
    ("Növbəti məzuniyyət", "calendar", True),
    ("Xəstəlik", "calendar", False),
    ("Ödənişsiz icazə", "calendar", False),
    ("Ezamiyyət", "workdays", False),
    ("Ailə hallarına görə icazə", "workdays_no_holidays", False),
]


def seed_data():
    """Creates the 3 base modules, HR dictionaries and a default admin account (idempotent)."""
    db.create_all()

    modules = {}
    for code, name_az, name_en in MODULES:
        m = Module.query.filter_by(code=code).first()
        if not m:
            m = Module(code=code, name=name_az, name_en=name_en)
            db.session.add(m)
            db.session.flush()
        modules[code] = m

    for category, names in HR_DICTIONARIES.items():
        for name in names:
            exists = DictionaryItem.query.filter_by(
                module_code="HR", category=category, name=name
            ).first()
            if not exists:
                db.session.add(DictionaryItem(module_code="HR", category=category, name=name))

    for name, base_days, years_per_bonus, bonus_days, max_bonus in LEAVE_CATEGORIES:
        exists = LeaveCategory.query.filter_by(name=name).first()
        if not exists:
            db.session.add(LeaveCategory(
                name=name, base_vacation_days=base_days,
                seniority_years_per_bonus=years_per_bonus,
                bonus_days_per_interval=bonus_days,
                max_bonus_days=max_bonus,
            ))

    for name, counting_method, is_annual in LEAVE_REASONS:
        exists = LeaveReason.query.filter_by(name=name).first()
        if not exists:
            db.session.add(LeaveReason(name=name, counting_method=counting_method, is_annual_leave=is_annual))

    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            full_name="Sistem Administratoru",
            is_admin=True,
            must_change_password=False,
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.flush()
        for module in modules.values():
            db.session.add(Permission(
                user_id=admin.id, module_id=module.id,
                can_add=True, can_edit=True, can_delete=True,
                can_view=True, can_report=True,
                dict_add=True, dict_edit=True, dict_delete=True, dict_view=True,
            ))

    db.session.commit()
    print("Seed tamamlandı: modullar (HR, TABEL, SALARY), HR kitabçaları, kateqoriyalar və admin/admin123 hazırdır.")
