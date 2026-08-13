# HR / Tabel / Salary Sistemi

Python + Flask + Bootstrap/Tabulator (100% pulsuz, DevExpress əvəzinə) + PostgreSQL
əsasında çoxistifadəçili
korporativ idarəetmə sistemi. Bu ilkin versiyadır — arxitektura, admin panel,
access-nəzarəti, loglama və 3 baza modul (HR, Tabel, Salary) hazırdır.

## Xüsusiyyətlər

1. **Çoxistifadəçili iş** — Flask-Login sessiyaları ilə eyni vaxtda bir neçə
   istifadəçi paralel işləyə bilər (production-da `gunicorn -w 4` kimi bir
   neçə worker ilə işə salınmalıdır).
2. **Modul üzrə access idarəetməsi** — Admin panel üzərindən hər istifadəçiyə
   hər modul üzrə ayrıca icazələr verilir.
3. **Şərti loglama** — Admin bir istifadəçi üçün "log flag" aktivləşdirdikdə,
   o istifadəçinin bütün əməliyyatları DB-yə (`activity_logs` cədvəli) və
   `logs/{username}.log` faylına yazılır. Flag söndürüldükdə yazılma dərhal
   dayanır.
4. **Admin panel** — yeni istifadəçi yaratmaq, parolu standarta ("test")
   sıfırlamaq, access vermək, bloklamaq, log flag qoymaq/götürmək, log
   fayllarını əldə etmək.
5. **3 ilkin modul** — HR (əməkdaşlar), Tabel (davamiyyət), Salary (əməkhaqqı).
6. **Modul üzrə icazə sahələri** — əlavə et, dəyiş, sil, yalnız baxış,
   hesabat, və modulun məlumat kitabçası (dictionary) üzrə əlavə/dəyiş/sil/baxış.
7. **Əsas menyu** — Dashboard, Əməkdaşların siyahısı, Tabellərin siyahısı,
   Əməkhaqların siyahısı, Məlumat kitabçaları, Hesabatlar, Tools (istifadəçini
   dəyişmək / profil, proqramın stili (Bootstrap/Bootswatch), parolu dəyişmək, şrift
   ölçüsü və dil).

## UI texnologiyası (pulsuz alternativ)

DevExpress/DevExtreme kommersiya lisenziyası tələb etdiyi üçün (yalnız 30 günlük
pulsuz trial) layihədə onun əvəzinə **tam pulsuz, MIT lisenziyalı** aşağıdakı
kitabxanalar istifadə olunur:

- **[Bootstrap 5](https://getbootstrap.com/) + [Bootswatch](https://bootswatch.com/)** —
  ümumi tətbiq dizaynı və Tools → Style bölməsindəki tema dəyişdirmə funksiyası
  (Cosmo, Flatly, Darkly, Slate və s. — 8 hazır tema).
- **[Tabulator.js](https://tabulator.info/)** — bütün cədvəllər (əməkdaşlar,
  tabel, əməkhaqqı, kitabçalar) bu kitabxana ilə qurulub və dəstəklənir:
  - sütun üzrə filter (`headerFilter`)
  - sıralama (sorting)
  - ümumi axtarış qutusu (bütün sahələr üzrə)
  - qruplaşdırma (məs. şöbəyə, statusa, dövrə görə) açılan siyahı ilə
  - **qrup üzrə cəmi (group footer)** və **cədvəlin ümumi cəmi (bottom totals)**
    — məs. Salary cədvəlində hər dövr üzrə avtomatik cəm, həmçinin bütün
    cədvəlin ümumi cəmi.

Bu kitabxanaların heç biri şirkət ölçüsü, gəlir və ya istifadəçi sayına görə
lisenziya ödənişi tələb etmir.



### 1. Virtual mühit və paketlər

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. PostgreSQL bazasını hazırlayın

```sql
CREATE DATABASE hr_db;
CREATE USER hr_user WITH PASSWORD 'hr_pass';
GRANT ALL PRIVILEGES ON DATABASE hr_db TO hr_user;
```

`.env.example` faylını `.env` adı ilə köçürün və `DATABASE_URL` dəyərini öz
PostgreSQL məlumatlarınıza uyğun tənzimləyin:

```bash
cp .env.example .env
```

> Qeyd: `.env` faylı olmadıqda layihə avtomatik olaraq lokal SQLite
> (`app.db`) ilə işə düşür — bu, PostgreSQL server olmadan sürətli test üçün
> nəzərdə tutulub. Real istifadə üçün mütləq PostgreSQL-ə keçin.

### 3. Bazanı hazırlamaq və ilkin datanı yükləmək (seed)

```bash
python run.py
```

İlk işə salınmada `run.py` avtomatik olaraq cədvəlləri yaradır və aşağıdakı
ilkin datanı əlavə edir:

- Modullar: `HR`, `TABEL`, `SALARY`
- Admin istifadəçi: **admin / admin123** (tam icazələrlə)

Server `http://localhost:5000` ünvanında açılacaq.

Alternativ olaraq seed əməliyyatını ayrıca da işə sala bilərsiniz:

```bash
flask --app run.py seed
```

### 4. Production üçün işə salma (çoxistifadəçili rejim)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

## Arxitektura: vahid modal-forma bazası və "core" hissə

- **`app/templates/modal_form_base.html`** — bütün Add/Edit formaları (Əməkdaş,
  İş yeri, Bildiriş, Əmr, Kateqoriya, Sığorta, Kart, Sənəd, Tabel, Salary,
  Kitabça və s. — 16 forma) indi bu **tək bazadan həqiqi Jinja inheritance**
  ilə miras alır. Hər forma sadəcə `form_title`, `form_action`, `cancel_url`
  dəyişənlərini təyin edir və `form_fields` blokunu doldurur — `<form>`,
  Ok/İmtina düymələri, modal-uyğunluğu bir yerdə saxlanılır. Çox-kartlı
  formalar (Əməkdaş kimi) `form_no_wrapper_card = true` təyin edir.
- **`app/templates/_sidebar_menu.html`** — əsas menyu linkləri `base.html`-dən
  ayrılıb. `base.html` artıq tam **generic tətbiq skeleti**dir (tema/JS
  sistemi, modal, xəta hesabatı, flash mesajları) — başqa layihədə yalnız bu
  bir faylı dəyişməklə yenidən istifadə oluna bilər.
- **`app/core/`** — layihədən asılı olmayan API-lar: grid tənzimləmələri
  (database-də saxlanılır), dictionary tez-əlavə, xəta hesabatı email/screenshot.
- **`app/static/js/{modal,context-menu,advanced-grid,error-report}.js`** —
  heç bir HR-specific koda bağlı deyil, URL-ləri parametr kimi qəbul edir.

Bütün 48 şablon real Jinja2 mühərriki ilə tam render testindən keçirilib
(parse + inheritance zənciri + real data ilə render) — sınaq nəticələri
təmizdir.



Hər əməkdaşın kartında **"İş yerləri"** bölməsi var (əməkdaşı redaktə et → İş yerləri
tab-ı). Hər qeyd bir "ticket" ilə iki cürdən biri olur:

- **Cari şirkət** — Struktur (dictionary), Vəzifə (dictionary) və mütləq bir
  **Əmr** seçilir (İşə qəbul / Daxili keçid / İşdən çıxma). Əmrlər öz
  strukturlu dictionary-sindədir (nömrə, tarix, qüvvəyə minmə tarixi, növ,
  qeyd) — bax **HR → Əmrlər**.
- **Kənar iş yeri** — Struktur/Vəzifə sərbəst mətn, başlama/bitmə tarixləri
  mütləqdir, əmr sahəsi lazım deyil (deaktivdir).

Əməkdaşın əsas kartındakı **Şöbə, Vəzifə, İşə qəbul/çıxma tarixi, Status və
bütün stajlar** artıq bu qeydlərə əsasən **avtomatik hesablanır** və formada
redaktə olunmur (yalnız oxumaq üçündür).

## Gridlərin fərdi tənzimlənməsi

Bütün cədvəllərdə (Əməkdaşlar, Tabel, Salary, Kitabçalar, Əmrlər, İş yerləri)
sütunları sürükləyib yerini dəyişmək, "⚙ Sütunlar" düyməsindən gizlətmək/
göstərmək, başlığa iki dəfə klikləyib adını dəyişmək və sıralamaq mümkündür —
bu tənzimləmələr brauzerdə (hər istifadəçi üçün ayrıca) yadda saxlanılır və
növbəti daxilolmada avtomatik tətbiq olunur.

## Sağ-klik menyuları və modal pəncərələr — yeni

DevExpress-ə uyğun təcrübə üçün bütün gridlərdə:

- **Sütun başlığına sağ-klik** → Artan/Azalan sırala, Sıralamanı təmizlə,
  **Footer** (cəmi sətri üçün Sum/Avg/Min/Max/Count seçimi), **Qrup footer**
  (qruplaşdırılmış görünüşdə hər qrupun yanında göstərilən aqreqat, footer-dən
  müstəqil seçilir), bu sütuna görə qruplaşdırmaq, sütunun adını dəyişmək,
  dəyişiklikləri yadda saxlamaq.
- **Sətirə sağ-klik** → Yeni / Dəyiş / Sil (Add/Edit avtomatik olaraq **modal
  pəncərədə** açılır — arxada siyahı görünür; Ok basanda yadda saxlanıb
  pəncərə bağlanır və siyahı yenilənir, İmtina isə sadəcə bağlayır).
- **İlk sütundakı ☰ işarəsi** → sütunları göstər/gizlət checklist-i.

Bütün bu tənzimləmələr (sütun sırası, gizli sütunlar, adlar, footer/qrup-footer
seçimləri, qruplaşdırma) brauzerdə istifadəçi üzrə yadda saxlanılır.



Brauzerdə `http://localhost:5000/login` açın:

- İstifadəçi adı: `admin`
- Parol: `admin123`

Admin panelindən yeni istifadəçilər yarada, onlara modul üzrə icazələr verə
və loglama flag-larını idarə edə bilərsiniz. Yeni yaradılan istənilən
istifadəçinin ilkin parolu **`test`**-dir.

## Layihə strukturu

```
hr_project/
  app/
    __init__.py          # Flask app factory
    models.py             # SQLAlchemy modelləri
    dashboard.py           # Dashboard route-u
    i18n.py                 # AZ/EN tərcümə lüğəti
    seed.py                  # İlkin data (modullar + admin)
    utils/
      decorators.py          # permission_required, admin_required, log_action
      logger.py                # DB + fayl loglama
    modules/
      auth/                     # login/logout
      admin/                     # admin panel
      hr/                         # HR modulu
      tabel/                      # Tabel modulu
      salary/                     # Salary modulu
      dictionaries/               # Modul üzrə məlumat kitabçaları
      reports/                    # Hesabatlar (CSV export daxil)
      tools/                       # profil / stil / parol / tənzimləmələr
    templates/                # Jinja2 şablonları (Bootstrap + Tabulator.js UI)
    static/                    # CSS
  logs/                    # Hər istifadəçi üçün .log faylları (log_flag=ON olanda)
  requirements.txt
  run.py
  config.py
```

## Növbəti addımlar

Bu, ilkin skeletdir. Hər modul (HR, Tabel, Salary) üzrə detallı biznes-məntiq
(sahələr, hesablama qaydaları, hesabat formatları, kitabça kateqoriyaları və s.)
ayrıca tələblərə əsasən genişləndiriləcək.
