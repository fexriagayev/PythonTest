TRANSLATIONS = {
    "dashboard": {"az": "Dashboard", "en": "Dashboard"},
    "employees": {"az": "Əməkdaşların siyahısı", "en": "Employee List"},
    "tabel": {"az": "Tabellərin siyahısı", "en": "Timesheets"},
    "salary": {"az": "Əməkhaqların siyahısı", "en": "Salary List"},
    "dictionaries": {"az": "Məlumat kitabçaları", "en": "Dictionaries"},
    "reports": {"az": "Hesabatlar", "en": "Reports"},
    "tools": {"az": "Tools", "en": "Tools"},
    "logout": {"az": "Çıxış", "en": "Logout"},
    "login": {"az": "Daxil ol", "en": "Login"},
    "username": {"az": "İstifadəçi adı", "en": "Username"},
    "password": {"az": "Parol", "en": "Password"},
    "admin_panel": {"az": "Admin Panel", "en": "Admin Panel"},
    "users": {"az": "İstifadəçilər", "en": "Users"},
    "change_user": {"az": "İstifadəçini dəyişmək", "en": "User Profile"},
    "style": {"az": "Proqramın stili", "en": "Application Style"},
    "change_password": {"az": "Parolu dəyişmək", "en": "Change Password"},
    "settings": {"az": "Şrift / Dil", "en": "Font / Language"},
    "add": {"az": "Əlavə et", "en": "Add"},
    "edit": {"az": "Dəyiş", "en": "Edit"},
    "delete": {"az": "Sil", "en": "Delete"},
    "save": {"az": "Yadda saxla", "en": "Save"},
    "cancel": {"az": "Ləğv et", "en": "Cancel"},
    "actions": {"az": "Əməliyyatlar", "en": "Actions"},
}


def translate(key, lang="az"):
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("az", key))
