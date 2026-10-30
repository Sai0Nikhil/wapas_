from .models import Event


def log_event(s, kind: str, text: str, case_id: str = "") -> None:
    if case_id.startswith("eval-"):
        return  # evaluation cases are summarised once, not logged one by one
    s.add(Event(case_id=case_id, kind=kind, text=text))
