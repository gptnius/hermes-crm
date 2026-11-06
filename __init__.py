"""Hermes native plugin entry point. No side effects at module import."""
def register(ctx):
    from .hermes_crm.plugin import register as register_crm
    register_crm(ctx)
