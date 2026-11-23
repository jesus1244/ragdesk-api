"""Fixed visitor-facing messages per assistant language (model answers follow the question)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Messages:
    no_answer: str
    refused: str
    failed: str


MESSAGES: dict[str, Messages] = {
    "en": Messages(
        no_answer=(
            "I could not find that in the documentation. "
            "Try asking about something the documents cover, or contact the team directly."
        ),
        refused="Sorry, I cannot help with that request.",
        failed="Sorry, something went wrong. Please try again in a moment.",
    ),
    "es": Messages(
        no_answer=(
            "No encontré eso en la documentación. "
            "Prueba con otra pregunta sobre los temas de los documentos o escribe al equipo."
        ),
        refused="Lo siento, no puedo ayudarte con esa solicitud.",
        failed="Lo siento, algo salió mal. Inténtalo de nuevo en un momento.",
    ),
}


def messages_for(language: str) -> Messages:
    return MESSAGES.get(language, MESSAGES["en"])
