"""Regenerate synthetic SQLite report-review contracts; no host/provider access."""
import json
import tempfile
from pathlib import Path
from hermes_crm.domain import CRM
from test_report_reviews import make_setup, get, write


def generate():
    values = {}
    with tempfile.TemporaryDirectory(prefix='crm-review-ui-') as directory:
        for name in ('native', 'scheduled_research', 'scheduled_company', 'native_cancelled', 'native_superseded'):
            crm = CRM(f'sqlite:///{directory}/{name}.db', profile='synthetic')
            try:
                s = make_setup(crm, 'native' if name.startswith('native') else name)
                if name.startswith('native_'):
                    row = s['source'].get(s['assignment']['id'])
                    s['source'].invalidate(row['id'], version=row['version'], reason=name.removeprefix('native_'))
                preview = get(s)
                receipt = write(s)
                values[name] = dict(preview=preview, receipt=receipt, reviewed=get(s),
                                    assignment=s['source'].get(s['assignment']['id']))
            finally:
                crm.close()
    return values


if __name__ == '__main__':
    path = Path(__file__).parent / 'fixtures/report_review_backend.json'
    path.write_text(json.dumps(generate(), indent=2) + '\n')
