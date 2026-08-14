from app import db


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)  # HR / TABEL / SALARY
    name = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))

    def __repr__(self):
        return f"<Module {self.code}>"
