from groq import Groq

client = Groq()

print("Czat z Grokiem (xAI) przez Groq API. 'koniec' = wyjście\n")

while True:
    user_input = input("Ty: ")
    
    if user_input.lower() in ["koniec", "exit", "q"]:
        print("Do zobaczenia!")
        break
    
    try:
        response = client.chat.completions.create(
            messages=[
                # <-- tu dodajemy kontekst
                {"role": "system", "content": "Jesteś Grok 3 zbudowany przez xAI. Odpowiadasz szczerze, z humorem, bez korporacyjnej sztywności. Nie myl się z narzędziami explainable AI o podobnej nazwie."},
                {"role": "user",   "content": user_input}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.8,          # lekko wyższa = więcej osobowości
            max_tokens=400,
        )
        
        print("Grok:", response.choices[0].message.content.strip())
        print()
    
    except Exception as e:
        print("Błąd:", str(e))