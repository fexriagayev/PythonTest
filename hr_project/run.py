from app import create_app
import click

app = create_app()


@app.cli.command("seed")
def seed_command():
    """Usage: flask --app run.py seed"""
    from app.seed import seed_data
from datetime import datetime

def get_current_date():
    """Returns the current date as a string in the format 'YYYY-MM-DD'"""
    return datetime.now().strftime("%Y-%m-%d")
    seed_data()


if __name__ == "__main__":
    with app.app_context():
        from app.seed import seed_data

        seed_data()
    app.run(host="0.0.0.0", port=5000, debug=True)

