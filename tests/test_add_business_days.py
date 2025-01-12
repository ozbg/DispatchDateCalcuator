from datetime import date, timedelta
from app.schedule_logic import add_business_days

def test_add_business_days_no_weekends_no_closed_dates():
        start_date = date(2023, 10, 2)  # Monday
        days_to_add = 5
        closed_dates = []
        adjusted_start_date, end_date = add_business_days(start_date, days_to_add, closed_dates)
        assert adjusted_start_date == start_date
        print(f"End date: {end_date}")

        assert end_date == start_date + timedelta(days=7)  # 5 business days later, skipping no weekends


def test_add_business_days_with_weekends():
        start_date = date(2023, 10, 6)  # Friday
        days_to_add = 5
        closed_dates = []
        adjusted_start_date, end_date = add_business_days(start_date, days_to_add, closed_dates)
        assert adjusted_start_date == start_date
        print(f"End date: {end_date}")
        assert end_date == start_date + timedelta(days=7)   # 5 business days later, skipping weekends


def test_add_business_days_with_closed_dates():
        start_date = date(2023, 10, 2)  # Monday
        days_to_add = 5
        closed_dates = ["2023-10-04", "2023-10-05"]  # Wednesday and Thursday are closed
        adjusted_start_date, end_date = add_business_days(start_date, days_to_add, closed_dates)
        assert adjusted_start_date == start_date
        assert end_date == start_date + timedelta(days=7) + timedelta(days=2)  # 5 business days later, skipping closed dates

    
def test_add_business_days_start_on_weekend():
        start_date = date(2023, 10, 7)  # Saturday
        days_to_add = 5
        closed_dates = []
        adjusted_start_date, end_date = add_business_days(start_date, days_to_add, closed_dates)
        assert adjusted_start_date == start_date + timedelta(days=2)  # Adjusted to Monday
        assert end_date == adjusted_start_date + timedelta(days=7)  # 5 business days later, skipping weekends


def test_add_business_days_start_on_closed_date():
        start_date = date(2023, 10, 4)  # Wednesday
        days_to_add = 5
        closed_dates = ["2023-10-04"]  # Wednesday is closed
        adjusted_start_date, end_date = add_business_days(start_date, days_to_add, closed_dates)
        assert adjusted_start_date == start_date + timedelta(days=1)  # Adjusted to Thursday
        assert end_date == adjusted_start_date + timedelta(days=7)  # 5 business days later, skipping closed dates


