from decimal import localcontext
import json
from pathlib import Path
from cn_contract.domain import ProfileMoneyValue

rows = []
for precision in (28, 3):
    for value in ('1.123456789', '9999999999999999.99999999'):
        with localcontext() as ctx:
            ctx.prec = precision
            try:
                result = ProfileMoneyValue(kind='money', value=value, unit='CNY')
                rows.append({'precision': precision, 'input': value, 'accepted': True,
                             'stored': str(result.value)})
            except ValueError as error:
                rows.append({'precision': precision, 'input': value, 'accepted': False,
                             'error_type': type(error).__name__})
print(json.dumps(rows, ensure_ascii=False, indent=2))
