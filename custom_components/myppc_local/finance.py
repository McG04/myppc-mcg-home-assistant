"""Parse visible myPPC text. All accounting uses Decimal, never binary floats."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def money(value):
    s = re.sub(r'\s|Lei|lei|RON', '', value).replace('−', '-')
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    if not re.fullmatch(r'-?\d+(?:\.\d{1,2})?', s):
        raise ValueError('Unrecognized amount')
    try:
        return Decimal(s).quantize(Decimal('0.01'))
    except InvalidOperation as exc:
        raise ValueError('Invalid amount') from exc


def lines(text):
    return [x.strip() for x in text.splitlines() if x.strip()]


def field(text, name):
    parts = lines(text)
    try:
        i = parts.index(name)
        return parts[i + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError('Missing field: ' + name) from exc


def date(value):
    return datetime.strptime(value, '%d.%m.%Y').date().isoformat()


def invoice(text):
    return dict(id=field(text, 'Factură'), issued=date(field(text, 'Dată emitere')),
                due=date(field(text, 'Dată scadentă')),
                amount=str(money(field(text, 'Valoare'))),
                paid='Achitat' in lines(text))


def merge_records(previous, current):
    """Keep records which disappeared from the portal's limited window."""
    result = {item['id']: item for item in previous}
    for item in current:
        result[item['id']] = {**result.get(item['id'], {}), **item}
    return list(result.values())


def payment(text):
    raw_method = field(text, 'Tip / Mod')
    method = {'Ordin de plata': 'OP', 'Plata online': 'APP'}.get(raw_method, raw_method)
    return dict(date=date(field(text, 'Dată plată')),
                method=method,
                amount=str(money(field(text, 'Valoare'))))


def balance(text):
    # The site renders -100,00 as separate DOM fragments/lines.
    parts = lines(text)
    if parts[0] != 'Sold la zi' or parts[-1] != 'lei':
        raise ValueError('Missing signed balance')
    return money(''.join(parts[1:-1]))


def summary(signed):
    amount = money(str(signed))
    return dict(balance=str(amount), amount_due=str(max(amount, Decimal('0.00'))),
                credit=str(max(-amount, Decimal('0.00'))))
