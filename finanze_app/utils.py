from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ValidationError


def today() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Rome")).date()
    except ZoneInfoNotFoundError:
        return date.today()


def timestamp() -> datetime:
    try:
        return datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None, microsecond=0)
    except ZoneInfoNotFoundError:
        return datetime.now().replace(microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def money(value, *, positive=False, nonnegative=False) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value).strip().replace(",", "."))
        if not amount.is_finite() or abs(amount) > Decimal("999999999999.99"):
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("L'importo può avere al massimo due decimali.")
        if positive and amount <= 0:
            raise ValidationError("Inserisci un importo maggiore di zero.")
        if nonnegative and amount < 0:
            raise ValidationError("Il compenso non può essere negativo.")
        return float(amount)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError("Inserisci un importo numerico valido.") from exc


def cents(value) -> int:
    return int(Decimal(str(value)) * 100)


def euro(value, signed=False) -> str:
    sign = "+" if signed and value > 0 else ""
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}{formatted} €"


def as_date(value, *, past_only=False) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(str(value), fmt).date()
                break
            except (ValueError, TypeError):
                continue
        if parsed is None:
            raise ValidationError("Inserisci una data valida (gg/mm/aaaa).")
        value = parsed
    if past_only and value > today():
        raise ValidationError("Registra solo movimenti e compensi già avvenuti, fino a oggi.")
    return value


def text(value, *, label="Il campo", required=False, limit=2000) -> str:
    value = "" if value is None else str(value).strip()
    if required and not value:
        raise ValidationError(f"{label} è obbligatorio.")
    if len(value) > limit:
        raise ValidationError(f"{label}: usa al massimo {limit} caratteri.")
    return value
