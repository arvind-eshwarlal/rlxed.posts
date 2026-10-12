"""
Token expiry check. Runs as the LAST step of every workflow run, so it never blocks a post.

Reads content/token_dates.json. If any token is within warn_days of expiring (or already past),
it prints what to do and exits with an error, which turns the run red -> GitHub emails you.
To avoid two emails a day, scheduled runs only fail on the morning slot; manual runs always fail.
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
PATH = os.path.join(ROOT, "content", "token_dates.json")


def expiry(info):
    if "expires" in info:
        return dt.date.fromisoformat(info["expires"])
    return dt.date.fromisoformat(info["issued"]) + dt.timedelta(days=int(info["lifetime_days"]))


def main():
    if not os.path.exists(PATH):
        print("No content/token_dates.json - nothing to check.")
        return 0
    try:
        cfg = json.load(open(PATH))
        warn = int(cfg.get("warn_days", 10))
        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()
        due, lines = [], []
        for name, info in cfg["tokens"].items():
            exp = expiry(info)
            left = (exp - today).days
            status = "EXPIRED" if left < 0 else ("RENEW NOW" if left <= warn else "ok")
            lines.append(f"{name:14} expires {exp}  ({left} days left)  {status}")
            if left <= warn:
                due.append((name, left, info.get("renew", "")))
    except Exception as e:  # noqa: BLE001 - a broken file should be noticed, not ignored
        print(f"PROBLEM reading content/token_dates.json: {e}")
        return 1

    print("Token expiry check")
    print(*lines, sep="\n")
    if not due:
        return 0

    print("\nACTION NEEDED:")
    for name, left, renew in due:
        when = f"expired {-left} days ago" if left < 0 else f"expires in {left} days"
        print(f"- {name} token {when}. {renew}")
    print("After renewing, update its date in content/token_dates.json so this warning stops.")

    quiet = os.environ.get("GITHUB_EVENT_NAME") == "schedule" and now.hour >= 12
    if quiet:
        print("(evening scheduled run: warning only, to limit emails to one a day)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
