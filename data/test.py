from bus_delay import get_waiting_times

times = get_waiting_times("STIF:StopPoint:Q:29631:", limit=3)

for t in times:
    print(f"{t['wait_minutes']} min – {t['expected_departure_utc']}")
