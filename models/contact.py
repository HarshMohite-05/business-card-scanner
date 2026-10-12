from dataclasses import dataclass
from utils.constants import FIELDS

@dataclass
class ContactDraft:
    values: dict
    image: bytes | None = None
    raw_text: str = ''

    @classmethod
    def empty(cls):
        return cls(dict.fromkeys(FIELDS, ''))
