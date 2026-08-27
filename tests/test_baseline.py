from src.chatbot import BVGAssistant

assistant = BVGAssistant()

result = assistant.ask(
    "Can I bring a bicycle on BVG transport?"
)

print("\nANSWER\n")
print(result.answer)

print("\nRETRIEVED\n")

for source in result.sources:
    print(
        source.source,
        round(source.score, 3),
    )

#PYTHONPATH=. python tests/test_baseline.py