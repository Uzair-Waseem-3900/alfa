class ToolInputError(Exception):
    """Bad or unsupported input to an agent tool. The message is shown to the
    model verbatim, so it must be safe and helpful to read (never internals).
    Lives here (not in my_tool) so services can raise it without importing tools."""
