class FinanceError(Exception):
    """Errore leggibile dall'utente, senza dettagli tecnici sensibili."""


class ValidationError(FinanceError):
    pass


class StorageError(FinanceError):
    pass


class ConflictError(FinanceError):
    pass
