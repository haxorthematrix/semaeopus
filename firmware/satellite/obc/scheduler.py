"""
Trivial cooperative scheduler. Each task is a (period_ms, callable) pair.

This isn't FreeRTOS — but it mirrors the way most real CubeSat OBCs
schedule housekeeping: a main loop dispatching periodic jobs. Perfect
for our purposes.
"""

from .compat import ticks_ms, ticks_diff, ticks_add


class Scheduler:
    def __init__(self):
        self._tasks = []  # list of [period_ms, next_due_ms, fn, name]

    def add(self, period_ms, fn, name=None):
        now = ticks_ms()
        self._tasks.append([period_ms, now, fn, name or fn.__name__])

    def tick(self):
        now = ticks_ms()
        for task in self._tasks:
            if ticks_diff(now, task[1]) >= 0:
                try:
                    task[2]()
                except Exception as e:
                    print("[sched] task", task[3], "raised:", e)
                task[1] = ticks_add(now, task[0])
