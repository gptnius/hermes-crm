"""Opt-in, synthetic-only demo. Never reads external accounts or user files."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from copy import copy
from sqlalchemy import select
from .domain import CRMError, contacts, deals, tasks, settings

class _TransactionEngine:
    """Expose the already-owned transaction to the ordinary domain methods."""
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def connect(self):
        yield self.connection

    begin = connect


def seed(crm):
    """Seed all-or-nothing, while excluding concurrent writes during emptiness check."""
    with crm.engine.begin() as connection:
        if crm.backend == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        # Match relationship/core writers: catalog row before table/entity locks.
        # On refusal this revision increment is rolled back with the transaction.
        crm._catalog_lock(connection)
        if crm.backend != 'sqlite':
            # Table names and schema are application-owned and identifier-quoted.
            schema = crm.engine.get_execution_options()['schema_translate_map'][None]
            preparer = connection.dialect.identifier_preparer
            names = ', '.join(preparer.quote_schema(schema) + '.' + preparer.quote(t.name)
                              for t in (contacts, deals, tasks))
            connection.exec_driver_sql('LOCK TABLE ' + names + ' IN EXCLUSIVE MODE')
        from .relationship_schema import check_schema, companies, events
        # Check with the original engine (which retains schema translation). Reads
        # never initialize relationship storage. Count all profiles in this physical
        # workspace, matching the legacy core-record emptiness check.
        if check_schema(crm, connection) and any(
                connection.execute(select(table.c.id).limit(1)).first() is not None
                for table in (companies, events)):
            raise CRMError('Demo seed refuses a non-empty workspace', 409)
        scoped = copy(crm)
        scoped.engine = _TransactionEngine(connection)
        _seed(scoped)


def _seed(crm):
    with crm.engine.connect() as conn:
        if any(conn.execute(select(t.c.id).limit(1)).first() is not None for t in (contacts,deals,tasks)):
            raise CRMError('Demo seed refuses a non-empty workspace', 409)
    people = [
        ('Maya Chen','maya','Northstar Studio','Founder','lead'),
        ('Alex Morgan','alex','Orbit Works','Head of Operations','lead'),
        ('Jordan Ellis','jordan','Cedar & Coast','Creative Director','customer'),
        ('Sam Rivera','sam','Fieldwork Labs','Partnerships Lead','partner'),
        ('Taylor Brooks','taylor','Common Ground','Chief Executive','lead'),
        ('Riley Park','riley','Daybreak Digital','Product Lead','lead'),
        ('Avery Quinn','avery','Forma Collective','Managing Director','customer'),
        ('Casey Lane','casey','Lumen Systems','VP of Growth','lead')]
    created=[]
    for name,email,company,title,lifecycle in people:
        created.append(crm.create('contacts',dict(name=name,email=f'{email}@example.com',company=company,title=title,lifecycle=lifecycle,
            notes='Synthetic demo contact. No real person or organization is represented.'),actor='demo'))
    deals_created=[]
    for title,i,value,stage,days in [
        ('Brand platform partnership',0,2400000,'proposal',21),('Operations workspace',1,1800000,'qualified',30),
        ('Creative growth program',2,3200000,'won',-5),('Partner launch program',3,1200000,'negotiation',14),
        ('Team enablement sprint',4,850000,'lead',35),('Product strategy retainer',5,3600000,'proposal',20),
        ('Design systems rollout',6,2100000,'won',-8),('Customer intelligence pilot',7,1500000,'qualified',28)]:
        deals_created.append(crm.create('deals',dict(title=title,contact_id=created[i]['id'],value=value,stage=stage,
            close_date=(datetime.now(timezone.utc)+timedelta(days=days)).date().isoformat(),notes='Synthetic opportunity for demonstration.'),actor='demo'))
    for title,i,hours,priority in [
        ('Send the proposal outline',0,3,'high'),('Review discovery notes',1,9,'normal'),
        ('Prepare the partner check-in',3,25,'normal'),('Confirm the workshop agenda',5,-8,'high'),
        ('Map the pilot milestones',7,48,'normal')]:
        crm.create('tasks',dict(title=title,contact_id=created[i]['id'],deal_id=deals_created[i]['id'],
            due_at=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat(),priority=priority,
            notes='Internal demo reminder only. No email or message will be sent.'),actor='demo')
    with crm.engine.begin() as conn: conn.execute(settings.insert().values(key='demo',value='true'))
