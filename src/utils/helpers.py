   
def translate_difficulty_pl_to_en(difficulty: str) -> str:
       
    difficulty_pl = str(difficulty)

    difficulty_map = {
        "Łatwy": "easy",
        "Średni": "medium",
        "Trudny": "hard"
    }

    difficulty_en = difficulty_map.get(difficulty_pl, difficulty_pl)
    return difficulty_en