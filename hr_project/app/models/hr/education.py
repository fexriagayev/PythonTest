from app import db

class EmployeeEducation(db.Model):
    __tablename__ = "employee_educations"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    education_level_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    institution_name = db.Column(db.String(255))
    faculty_name = db.Column(db.String(255))
    specialty_name = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    diploma_number = db.Column(db.String(50))
    diploma_issue_date = db.Column(db.Date)
    note = db.Column(db.Text)

    employee = db.relationship("Employee", backref=db.backref(
        "educations", cascade="all, delete-orphan", lazy="dynamic"))
    education_level = db.relationship("DictionaryItem", foreign_keys=[education_level_id])