from pydantic import BaseModel, Field, conint, conlist

class Question(BaseModel):
    question: str = Field(..., min_length=1)
    options: conlist(str, min_length=4, max_length=4)
    correct_index: conint(ge=0, le=3)


class Quiz(BaseModel):
    quiz_title: str = Field(..., min_length=1)
    questions: list[Question]
