"""Explicit Company identities and reviewed primary contact associations."""
import uuid
from contextlib import nullcontext
from pydantic import Field, field_validator
from sqlalchemy import select, update, delete, or_
from .domain import CRMError, StrictModel, ContactInput, contacts, now
from .report_store import scope_for
from .relationship_schema import companies,contact_companies,check_schema
from .relationship_store import RelationshipStore

class CompanyInput(StrictModel):
    name: str = Field(min_length=1,max_length=160)
    domain: str | None = Field(default=None,max_length=254)
    notes: str = Field(default='',max_length=10000)
    @field_validator('name')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Name must not be blank')
        return value.strip()

class CompanyStore(RelationshipStore):
    table=companies
    def list(self,q='',include_archived=False,limit=50,offset=0,*,conn=None):
        self.crm._integer(limit,'limit',1,100); self.crm._integer(offset,'offset'); q=self.crm._text_filter(q,'q')
        if type(include_archived) is not bool: raise CRMError('include_archived must be boolean')
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            if not check_schema(self.crm,c): return dict(items=[],total=0,limit=limit,offset=offset)
            stmt=select(companies).where(companies.c.scope==scope_for(self.crm,connection=c))
            if not include_archived: stmt=stmt.where(companies.c.archived_at.is_(None))
            if q: stmt=stmt.where(or_(companies.c.name.ilike('%'+q+'%',escape='\\'),companies.c.domain.ilike('%'+q+'%',escape='\\')))
            return self._page(c,stmt.order_by(companies.c.name,companies.c.id),limit,offset)
    def create(self,data,*,actor,key):
        values=CompanyInput.model_validate(data).model_dump(); actor=self._actor(actor)
        def action(conn,scope):
            stamp=now(); result=dict(id=str(uuid.uuid4()),version=1,created_at=stamp,updated_at=stamp,archived_at=None,**values)
            conn.execute(companies.insert().values(scope=scope,**result)); self.crm._audit(conn,'companies',result,'created',actor)
            return result
        return self._write(key,['company_create',values,actor],action)
    def create_contact(self,data,company_id=None,expected_company_version=None,*,actor,key):
        """Atomically create a contact with an optional reviewed explicit Company.

        Separate receipts preserve CRM.create semantics. Legacy company text is
        independent; no name matching or implicit overwrite is performed.
        """
        if not isinstance(data,dict): raise CRMError('Contact data must be an object')
        data=dict(data)
        custom=data.pop('custom_fields',{})
        if not isinstance(custom,dict): raise CRMError('custom_fields must be an object')
        values=ContactInput.model_validate(data).model_dump()
        actor=self._actor(actor)
        if company_id is None:
            if expected_company_version is not None: raise CRMError('Company version requires a Company ID')
        else:
            try:
                if not isinstance(company_id,str) or str(uuid.UUID(company_id))!=company_id:
                    raise ValueError()
            except (ValueError,AttributeError):
                raise CRMError('Company ID must be an exact canonical UUID or null')
            self._version(expected_company_version)
        def action(conn,scope):
            if company_id is not None:
                company=self._get(conn,scope,company_id)
                if company['version']!=expected_company_version:
                    raise CRMError('Company changed; refresh before creating a contact',409)
                if company['archived_at'] is not None:
                    raise CRMError('Archived Company cannot receive links',409)
            contact=self.crm._insert_created(conn,'contacts',values,custom,actor)
            if company_id is not None:
                stamp=now()
                conn.execute(contact_companies.insert().values(scope=scope,contact_id=contact['id'],company_id=company_id,created_at=stamp,updated_at=stamp))
            return dict(contact=contact,company_link=self.get_contact_company(contact['id'],conn=conn))
        return self._write(key,['contact_create_with_company',values,custom,company_id,expected_company_version,actor],action)

    def _change(self,record_id,data,expected_version,actor,key,operation):
        self._version(expected_version);actor=self._actor(actor)
        if not isinstance(data,dict) or set(data)-{'name','domain','notes'}: raise CRMError('Unknown Company fields')
        def action(conn,scope):
            old=self._get(conn,scope,record_id)
            if old['version']!=expected_version: raise CRMError('Company changed; refresh before editing',409)
            fields=CompanyInput.model_validate({k:old[k] for k in ('name','domain','notes')} | data).model_dump()
            result=dict(old,**fields);result.update(version=expected_version+1,updated_at=now())
            if operation=='archive': result['archived_at']=now()
            if operation=='restore': result['archived_at']=None
            changed=conn.execute(update(companies).where(companies.c.scope==scope,companies.c.id==record_id,companies.c.version==expected_version).values(**result))
            if changed.rowcount!=1: raise CRMError('Company changed; refresh before editing',409)
            self.crm._audit(conn,'companies',result,operation,actor);return result
        return self._write(key,['company_'+operation,record_id,data,expected_version,actor],action)
    def update(self,company_id,data,*,expected_version,actor,key): return self._change(company_id,data,expected_version,actor,key,'updated')
    def archive(self,company_id,*,expected_version,actor,key): return self._change(company_id,{},expected_version,actor,key,'archive')
    def restore(self,company_id,*,expected_version,actor,key): return self._change(company_id,{},expected_version,actor,key,'restore')
    def get_contact_company(self,contact_id,*,conn=None):
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            contact=self.crm._get(c,'contacts',contact_id)
            result=dict(contact_id=contact_id,contact_version=contact['version'],company_id=None,company_name=None,company_archived=None,company_link_basis='unlinked')
            if not check_schema(self.crm,c): return result
            scope=scope_for(self.crm,connection=c)
            row=c.execute(select(companies).join(contact_companies,(companies.c.scope==contact_companies.c.scope)&(companies.c.id==contact_companies.c.company_id)).where(contact_companies.c.scope==scope,contact_companies.c.contact_id==contact_id)).mappings().first()
            if row: result.update(company_id=row['id'],company_name=row['name'],company_archived=row['archived_at'] is not None,company_link_basis='explicit')
            return result
    def set_contact_company(self,contact_id,company_id,*,expected_contact_version,actor,key):
        self._version(expected_contact_version); actor=self._actor(actor)
        if company_id is not None and (not isinstance(company_id,str) or not company_id): raise CRMError('Company ID must be an exact ID or null')
        def action(conn,scope):
            contact=self.crm._get(conn,'contacts',contact_id)
            if contact['version']!=expected_contact_version: raise CRMError('Contact changed; refresh before linking',409)
            company=self._get(conn,scope,company_id) if company_id is not None else None
            if company and company['archived_at']: raise CRMError('Archived Company cannot receive links',409)
            clause=(contact_companies.c.scope==scope,contact_companies.c.contact_id==contact_id)
            old=conn.execute(select(contact_companies).where(*clause)).mappings().first()
            if (old['company_id'] if old else None)!=company_id:
                stamp=now()
                if old: conn.execute(delete(contact_companies).where(*clause))
                if company_id: conn.execute(contact_companies.insert().values(scope=scope,contact_id=contact_id,company_id=company_id,created_at=stamp,updated_at=stamp))
                changed=conn.execute(update(contacts).where(contacts.c.id==contact_id,contacts.c.version==expected_contact_version).values(version=expected_contact_version+1,updated_at=stamp))
                if changed.rowcount!=1: raise CRMError('Contact changed; refresh before linking',409)
                self.crm._audit(conn,'contacts',contact,'company_link_changed',actor)
            return self.get_contact_company(contact_id,conn=conn)
        return self._write(key,['contact_company',contact_id,company_id,expected_contact_version,actor],action)

Companies=CompanyStore
