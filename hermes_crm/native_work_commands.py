"""Native explicit-user-command registration; never a model approval substitute."""
import json

from .domain import CRMError
from .native_work_operations import WorkOperationStore, command_name


def register_work_command(ctx, service):
    # Scope the routing name to existing high-entropy workspace identity. Do not
    # register a generic fallback that a user quick command could shadow.
    crm = None
    try:
        crm = service()
        registered_name = command_name(crm.workspace_token(), crm.profile)
    except Exception:
        raise CRMError('CRM command registration unavailable. Check this profile backend; no fallback was used.', 503) from None
    finally:
        if crm is not None: crm.close()

    def command(raw_args, *, source=None, session_id='', session_key='', platform=''):
        crm = None
        try:
            crm = service()
            if command_name(crm.workspace_token(), crm.profile) != registered_name:
                raise CRMError('CRM command workspace changed. Reload the profile before preparing another operation.', 409)
            result = WorkOperationStore(crm).execute(ctx, raw_args, source=source,
                session_id=session_id, session_key=session_key, platform=platform)
            return json.dumps({'schema_version': 1, 'ok': True, 'operation': result})
        except CRMError as exc:
            return json.dumps({'schema_version': 1, 'ok': False, 'error': exc.message, 'status': exc.status})
        except Exception:
            return json.dumps({'schema_version': 1, 'ok': False, 'error': 'Command outcome unavailable. Read operation status; do not redispatch.', 'status': 503})
        finally:
            if crm is not None: crm.close()
    ctx.register_command(registered_name, command,
        description='Perform one CRM-reviewed future assignment operation through this authenticated native session.',
        args_hint='<operation UUID>', argument_mode='text')
