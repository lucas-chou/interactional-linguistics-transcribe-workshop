from .models import TranscribeRequest


_OPENCC_T2S = None


def to_simplified_chinese(text: str) -> str:
    global _OPENCC_T2S
    if not text:
        return text
    if _OPENCC_T2S is None:
        from opencc import OpenCC

        _OPENCC_T2S = OpenCC("t2s")
    return _OPENCC_T2S.convert(text)


def should_force_simplified(request: TranscribeRequest, result_language: str | None = None) -> bool:
    language = (request.language if request.language != "auto" else result_language or "").lower()
    return language.startswith("zh") or language in {"chinese", "cn"}
