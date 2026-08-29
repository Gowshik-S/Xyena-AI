from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "demos" / "business-registry" / "frontend"


class _BusinessFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_business_form = False
        self.field_ids: set[str] = set()
        self.autofill_button: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "businessForm":
            self.in_business_form = True
        if not self.in_business_form:
            return
        if tag in {"input", "select", "textarea"} and values.get("id"):
            self.field_ids.add(str(values["id"]))
        if tag == "button" and values.get("id") == "autoFillBusinessButton":
            self.autofill_button = values

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_business_form:
            self.in_business_form = False


def test_autofill_covers_every_business_entry_field() -> None:
    parser = _BusinessFormParser()
    parser.feed((FRONTEND / "business-new.html").read_text(encoding="utf-8"))
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    demo_values = re.search(
        r"const demoValues = \{(?P<body>.*?)\n\s*\};",
        script,
        flags=re.DOTALL,
    )
    assert demo_values, "The business Auto-fill data map is missing."
    autofilled_ids = set(re.findall(r"^\s{6}([A-Za-z][A-Za-z0-9]*):", demo_values["body"], re.MULTILINE))

    assert parser.autofill_button is not None
    assert parser.autofill_button.get("type") == "button"
    assert autofilled_ids == parser.field_ids
