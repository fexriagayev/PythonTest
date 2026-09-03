from app import create_app
import click

app = create_app()


@app.cli.command("seed")
def seed_command():
    """Usage: flask --app run.py seed"""
    from app.seed import seed_data

    seed_data()


@app.cli.command("seed-demo")
@click.option("--count", default=100, help="Neçə test əməkdaş yaradılsın (default: 100)")
@click.option("--months-back", default=12, help="İşə qəbul tarixləri neçə ay geriyə yayılsın (default: 12)")
def seed_demo_command(count, months_back):
    """Usage: flask --app run.py seed-demo [--count 100] [--months-back 12]

    Testfor: N ədəd nümunə əməkdaş (tam iş tarixçəsi: əmrlər, bəzilərində
    vəzifə dəyişikliyi, bəzilərində işdən çıxma, tam doldurulmuş bildirişlər)
    + onların tarixçəsinə uyğun bütün aylar üçün generasiya olunmuş Tabel
    dövrləri yaradır. Əvvəlcə `flask --app run.py seed` işə salınmış olmalıdır.
    """
    from app.seed_demo import seed_demo_data

    n, period_count = seed_demo_data(employee_count=count, months_back=months_back)
    print(f"{n} test əməkdaş yaradıldı. {period_count} Tabel dövrü generasiya olundu.")


if __name__ == "__main__":
    with app.app_context():
        from app.seed import seed_data

        seed_data()
    app.run(host="0.0.0.0", port=5000, debug=True)
