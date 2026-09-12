from app.schemas.documents import DocumentInfo

_documents: dict[str, DocumentInfo] = {}


def add(document: DocumentInfo) -> DocumentInfo:
    _documents[document.id] = document
    return document


def list_all() -> list[DocumentInfo]:
    return list(_documents.values())


def get(doc_id: str) -> DocumentInfo | None:
    return _documents.get(doc_id)


def delete(doc_id: str) -> bool:
    return _documents.pop(doc_id, None) is not None


def clear() -> None:
    _documents.clear()
