import sys, time
print("Ouroboros mock interview started", flush=True)
questions = [
    "Question 1: 어떤 기능을 만들고 싶으신가요?",
    "Question 2: 성공 기준은 무엇인가요?",
    "Question 3: 결과물을 어디에 저장할까요?",
]
for q in questions:
    print(q, flush=True)
    ans = sys.stdin.readline()
    if not ans:
        break
    print(f"received: {ans.strip()}", flush=True)
print("Interview completed. Generate a Seed with session_id=mock", flush=True)
