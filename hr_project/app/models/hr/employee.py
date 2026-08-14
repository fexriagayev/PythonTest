from app import db
from app.models.dictionaries.dictionary import DictionaryItem


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)

    # --- S.A.A. (Soyadı, Adı, Atasının adı) ---------------------------------
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    father_name = db.Column(db.String(80))

    # --- Şəxsi məlumatlar — all combo fields point to DictionaryItem -------
    gender_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    family_status_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    education_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    birth_date = db.Column(db.Date)

    gender = db.relationship("DictionaryItem", foreign_keys=[gender_id])
    family_status = db.relationship("DictionaryItem", foreign_keys=[family_status_id])
    education_type = db.relationship("DictionaryItem", foreign_keys=[education_type_id])

    # Güzəşt — single-select dictionary (one benefit per employee)
    benefit_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    benefit = db.relationship("DictionaryItem", foreign_keys=[benefit_id])

    # --- Sənəd məlumatları ---------------------------------------------------
    fin_code = db.Column(db.String(20))  # S/V FİN nömrəsi
    id_card_number = db.Column(db.String(30))  # S/V seriya və nömrəsi
    social_insurance_number = db.Column(db.String(30))

    # --- İş məlumatları -------------------------------------------------------
    # NOTE: department, position, hire_date, termination_date, is_active,
    # total_experience, company_experience, other_experience are NO LONGER
    # manually edited on the employee form — they are auto-computed from the
    # employee's "İş yerləri" (əmək kitabçası) records. See
    # app/services/hr_service.py:recompute_employee_from_history().
    department = db.Column(db.String(120))
    position = db.Column(db.String(120))
    salary = db.Column(db.Numeric(12, 2))

    hire_date = db.Column(db.Date)  # İşə başlama tarixi (auto)
    termination_date = db.Column(db.Date)  # İşdən çıxma tarixi (auto)
    contract_start_date = db.Column(db.Date)  # Müqavilənin başlama tarixi
    contract_end_date = db.Column(db.Date)  # Müqavilənin bitmə tarixi

    total_experience = db.Column(db.String(50))  # Ümumi staj (auto)
    company_experience = db.Column(db.String(50))  # Şirkətdə staj (auto)
    other_experience = db.Column(db.String(50))  # Digər iş yerlərində staj (auto)
    remaining_vacation_days = db.Column(db.Integer)  # Qalan məzuniyyət günü

    # --- Əlaqə / digər ------------------------------------------------------
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    note = db.Column(db.Text)  # Qeyd
    photo_path = db.Column(db.String(255))  # Şəkil (foto)

    is_active = db.Column(db.Boolean, default=True)

    document = db.relationship(
        "Document",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    educations = db.relationship(
        "EmployeeEducation", back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"
