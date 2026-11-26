"""Generate fake raw chat logs under <DATA_DIR>/raw/<dataset>/batch-NNN.jsonl.

Usage:
    python seed_data.py                      # dataset=demo, 7 batches x 30 rows
    python seed_data.py --dataset demo --batches 10 --rows 50

內容刻意包含：重複問題、壞評價、空問題、email/手機（測試去識別化與去重）。
"""
import argparse
import random

from common import storage

TEMPLATES = [
    ("How do I request a refund for invoice {n}?", ["billing"]),
    ("我的發票 {n} 要怎麼退款", ["billing"]),
    ("How many days of leave do I have left?", ["hr"]),
    ("請問薪資單什麼時候發", ["hr"]),
    ("VPN keeps disconnecting on my laptop", ["it-support"]),
    ("忘記密碼要怎麼重設", ["it-support"]),
    ("Where is the cafeteria?", ["general"]),
    ("Refund my invoice and reset my password, my email is {email}", ["billing", "it-support"]),
    ("請問付款失敗，我的電話 {phone}", ["billing"]),
]
EMAILS = ["alice@example.com", "bob.lee@corp.example.org", "carol+test@example.net"]
PHONES = ["0912-345-678", "0987654321", "0933-111-222"]


def seed(dataset: str = "demo", batches: int = 7, rows: int = 30, seed_value: int = 42) -> int:
    rng = random.Random(seed_value)
    for b in range(batches):
        batch_id = f"batch-{b:03d}"
        out = []
        for i in range(rows):
            template, agents = rng.choice(TEMPLATES)
            question = template.format(
                n=rng.randint(1000, 1005),  # 範圍小 => 容易產生重複
                email=rng.choice(EMAILS),
                phone=rng.choice(PHONES),
            )
            if rng.random() < 0.05:
                question = ""
            out.append(
                {
                    "id": f"{batch_id}-{i}",
                    "question": question,
                    "agents": agents,
                    "answer": "(omitted)",
                    "feedback": "good" if rng.random() < 0.8 else "bad",
                }
            )
        storage.write_jsonl(f"raw/{dataset}/{batch_id}.jsonl", out)
    return batches


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="demo")
    parser.add_argument("--batches", type=int, default=7)
    parser.add_argument("--rows", type=int, default=30)
    args = parser.parse_args()
    n = seed(args.dataset, args.batches, args.rows)
    print(f"wrote {n} batches to raw/{args.dataset}/ (under DEMO_DATA_DIR)")
