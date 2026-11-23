from ragdesk.core.schemas import CustomModel


class BotStats(CustomModel):
    conversations: int
    questions: int
    answered: int
    unanswered: int
    answer_rate: float
