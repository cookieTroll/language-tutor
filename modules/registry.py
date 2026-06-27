from modules.writing.agent import WritingModule

# Registy of all middle-grain module agents available to the orchestrator
MODULE_REGISTRY = {
    "writing": WritingModule(),
}

def get_registry_description() -> str:
    """Returns a description of all registered modules for the LLM prompts."""
    return "\n".join(
        f"- {name}: {module.description}"
        for name, module in MODULE_REGISTRY.items()
    )
