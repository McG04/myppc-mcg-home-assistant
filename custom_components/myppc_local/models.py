"""Pure accounting mappings, matching the portal frontend fields."""
import hashlib
import json
from datetime import datetime
from .finance import money, summary


def rows(data):
    container = data.get('Rows') or {}
    value = container.get('Row', [])
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def iso_date(value):
    return datetime.fromisoformat(str(value).replace('Z','+00:00')).date().isoformat()


def normalize(invoices_data, payments_data, outstanding_data, balance_data, code):
    documents = []
    for group in rows(outstanding_data):
        doc_rows = group.get('documentList', {}).get('Row', [])
        documents += doc_rows if isinstance(doc_rows, list) else [doc_rows] if isinstance(doc_rows, dict) else []
    due = {}
    for doc in documents:
        if str(doc.get('paymentCode')) == code and doc.get('de_platit') is True:
            key = (str(doc['documentId']), iso_date(doc['maturity']))
            # The same document must not be counted twice through duplicate groups.
            due[key] = str(money(str(doc['balance'])))
    invoices = []
    for record in rows(invoices_data):
        if str(record.get('paymentCode')) != code:
            continue
        ident, maturity = str(record['idInvoiceBill']), iso_date(record['maturity'])
        remaining = due.get((ident, maturity), '0.00')
        invoices.append(dict(id=f'{ident}|{maturity}|{record.get("tip_document", "")}',
            document_id=ident, number=str(record['bill']), issued=iso_date(record['date']),
            due=maturity, amount=str(money(str(record['currentAmount']))),
            total_at_issue=str(money(str(record['amount']))), remaining_amount=remaining,
            paid=money(remaining) <= 0, remaining_source='portal_document_balance'))
    payments, counts = [], {}
    for record in rows(payments_data):
        method = {'Ordin de plata':'OP', 'Plata online':'APP'}.get(record['mode'],record['mode'])
        item = dict(date=iso_date(record['date']), amount=str(money(str(record['total']))), method=method)
        digest = hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
        counts[digest] = counts.get(digest, 0) + 1
        item['id'] = f'{digest}:{counts[digest]}'
        payments.append(item)
    # Never silently replace a missing signed balance with zero.
    return dict(**summary(balance_data['balance']), invoices=invoices, payments=payments)

