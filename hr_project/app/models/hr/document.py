from app import db


class EmployeeDocument(db.Model):
    __tablename__ = "employee_documents"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False, unique=True
    )

    fin_code = db.Column(db.String(7), unique=True)
    id_card_number = db.Column(db.String(30))
    social_insurance_number = db.Column(db.String(30))

    employee = db.relationship("Employee", back_populates="document")
