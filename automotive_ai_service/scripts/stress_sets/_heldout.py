"""Shared builder for the held-out question sets: expected answers come from the fixture, never from AI code."""
import json
from pathlib import Path

OOS = "I can only answer from this system's data"
SMALLTALK = ["greeting", "goodbye", "acknowledgement"]
FAMILY_INTENT = {"vehicles.quote": "vehicles", "vehicles.search": "vehicles", "bookings.mine": "own_bookings", "reservations.summary": "reservation_summary",
                 "fleet.status_counts": "fleet_status", "maintenance.due": "maintenance_due", "maintenance.records": "maintenance_records",
                 "maintenance.costs": "maintenance_costs", "vehicles.status": "vehicle_status", "reservations.revenue": "revenue",
                 "maintenance.inspections": "maintenance_inspections", "fleet.utilization": "utilization"}
TAGALOG = {"magkano", "ano", "anong", "ba", "po", "ilan", "ilang", "kasya", "sa", "ng", "ang", "yung", "kayo", "kailan", "sino", "mga", "pwede", "paano", "pano", "kulay", "araw",
           "linggo", "naka", "meron", "may", "lahat", "kami", "ko", "natin", "kanino", "sasakyan", "kotse", "salamat", "sige", "hindi", "ayaw", "makina", "bukas", "nyo", "inyo", "lang"}


def money(value):
    return f"PHP {float(value):,.2f}"


def is_taglish(message):
    return any(word.strip("?,.!") in TAGALOG for word in message.casefold().split())


def label(car):
    return f"{car['make']} {car['model']}"


def aliases(car):
    """How people name a car: model alone, then make and model."""
    return [car["model"].casefold(), f"{car['make']} {car['model']}".casefold()]


class QuestionSet:
    def __init__(self, fixture_path, prefix):
        self.db = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self.prefix, self.rows, self.seen = prefix, [], set()
        self.cars = self.db["cars"]
        self.rentable = [car for car in self.cars if car["status"] == "available"]

    def car(self, model):
        return next(car for car in self.cars if car["model"].casefold() == model.casefold())

    def q(self, category, family, role, message, must=(), must_not=(), kind="answer", tool=None, intents=None, intent_in=None,
          template=None, history=None, scope=True):
        key = (role, message.casefold(), tuple(history or ()))
        if key in self.seen:
            return
        self.seen.add(key)
        expect = {"kind": kind}
        if tool is not None:
            expect["tools"] = [tool] if tool else []
            if tool and not intents:
                intents = [FAMILY_INTENT[tool]]
        if intents:
            expect["intents"] = list(intents)
        groups = [list(group) if isinstance(group, (list, tuple)) else [group] for group in must]
        self.rows.append({"family": family, "category": category, "style": "taglish" if is_taglish(message) else "english",
                          "template": template or message, "split": self.prefix, "role": role, "message": message, "history": list(history) if history else None,
                          "check": {"must": groups, "must_not": list(must_not) + ([OOS] if scope else []), "intent_in": intent_in}, "expect": expect})

    def many(self, category, family, role, messages, *args, **kwargs):
        for message in messages:
            self.q(category, family, role, message, *args, **kwargs)

    def per_car(self, category, family, templates, cars, must_of, role="customer", days=(None,), **kwargs):
        """Each template with each car (both ways of naming it), and each number of days when the template has {n}."""
        for template in templates:
            for car in cars:
                for alias in aliases(car):
                    for n in (days if "{n}" in template else (None,)):
                        if n is not None and n < int(car.get("minimum_rental_duration") or 1):
                            continue
                        message = template.format(car=alias, n=n)
                        self.q(category, family, role, message, must_of(car, n) if n is not None else must_of(car), template=template, **kwargs)

    def write(self, out):
        with open(out, "w", encoding="utf-8") as handle:
            for index, row in enumerate(self.rows, 1):
                handle.write(json.dumps({"id": f"{self.prefix}{index:05d}", **row}, ensure_ascii=False) + "\n")
        print(len(self.rows), "questions,", len({row["template"] for row in self.rows}), "distinct wordings ->", out)
