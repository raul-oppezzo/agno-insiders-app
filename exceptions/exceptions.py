class WorkflowException(Exception):
    """Eccezione sollevata per errori durante l'esecuzione del workflow."""
    pass

class AgentException(Exception):
    """Eccezione sollevata per errori all'interno di un agente."""
    pass