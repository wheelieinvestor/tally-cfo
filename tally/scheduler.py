import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler


def run_scheduler() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start()
    print("Scheduler running (no jobs yet)", flush=True)

    keep_running = True

    def stop(signum: int, frame: object) -> None:
        nonlocal keep_running
        keep_running = False

    previous_handler = signal.signal(signal.SIGINT, stop)
    try:
        while keep_running:
            time.sleep(0.2)
    finally:
        scheduler.shutdown(wait=False)
        signal.signal(signal.SIGINT, previous_handler)
