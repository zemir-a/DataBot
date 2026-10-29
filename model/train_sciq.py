# Fine-tune Flan-T5 on SciQ to generate MCQs (question + answer + 3 distractors).
#   pip install transformers datasets accelerate sentencepiece

import re

from datasets import load_dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)

# ---------- 1. Load model and data ----------
MODEL = "google/flan-t5-small"  
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL)

ds = load_dataset("allenai/sciq")
# Some SciQ rows have no supporting passage; we need one as input
ds = ds.filter(lambda x: len(x["support"].strip()) > 0)
print(ds)


# ---------- 2. Format: passage in -> question, answer, 3 wrong options out ----------
def fmt(ex):
    src = "generate mcq: " + ex["support"].strip()
    tgt = (
        f"question: {ex['question']} "
        f"answer: {ex['correct_answer']} "
        f"wrong1: {ex['distractor1']} "
        f"wrong2: {ex['distractor2']} "
        f"wrong3: {ex['distractor3']}"
    )
    return {"src": src, "tgt": tgt}


def tokenize(batch):
    enc = tok(batch["src"], max_length=512, truncation=True)
    enc["labels"] = tok(text_target=batch["tgt"], max_length=128, truncation=True)["input_ids"]
    return enc


ds = ds.map(fmt)
cols = ds["train"].column_names
tokenized = ds.map(tokenize, batched=True, remove_columns=cols)

# ---------- 3. Train ----------
args = Seq2SeqTrainingArguments(
    output_dir="sciq-mcq-t5",
    learning_rate=3e-4,
    per_device_train_batch_size=8,
    per_device_eval_batch_size=16,
    gradient_accumulation_steps=2,
    num_train_epochs=3,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=1,
    logging_steps=100,
    report_to="none",
)

trainer = Seq2SeqTrainer(
    model=model,
    args=args,
    train_dataset=tokenized["train"],
    eval_dataset=tokenized["validation"],
    data_collator=DataCollatorForSeq2Seq(tok, model=model),
)

trainer.train()

trainer.save_model("sciq-mcq-t5-final")
tok.save_pretrained("sciq-mcq-t5-final")


# ---------- 4. Generate an MCQ from any passage ----------
def parse(text):
    m = re.match(
        r"question:(.*?)answer:(.*?)wrong1:(.*?)wrong2:(.*?)wrong3:(.*)", text, re.S
    )
    if not m:
        return None
    q, a, w1, w2, w3 = [s.strip() for s in m.groups()]
    return {"question": q, "answer": a, "distractors": [w1, w2, w3]}


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def make_mcq(passage, tries=8):
    inputs = tok("generate mcq: " + passage, return_tensors="pt", truncation=True, max_length=512)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}


    out = model.generate(**inputs, max_new_tokens=128, num_beams=4, repetition_penalty=1.3)
    best = parse(tok.decode(out[0], skip_special_tokens=True))
    if best is None:
        return None

    # 2) Keep only distractors that are unique and different from the answer
    seen = {norm(best["answer"])}
    pool = []
    for d in best["distractors"]:
        n = norm(d)
        if n and n not in seen:
            seen.add(n)
            pool.append(d)

    # 3) If duplicates were dropped, sample more outputs and borrow their distractors
    if len(pool) < 3:
        outs = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=True,
            top_p=0.95,
            temperature=1.0,
            num_return_sequences=tries,
        )
        for o in outs:
            p = parse(tok.decode(o, skip_special_tokens=True))
            if not p:
                continue
            for d in p["distractors"]:
                n = norm(d)
                if n and n not in seen:
                    seen.add(n)
                    pool.append(d)
                    if len(pool) == 3:
                        break
            if len(pool) == 3:
                break

    if len(pool) < 3:
        return None  # skip this passage rather than ship a bad question

    return {
        "question": best["question"],
        "answer": best["answer"],
        "distractors": pool[:3],
    }


# Try it on held-out SciQ passages first, then on text from your own PDFs
for ex in ds["test"].select(range(5)):
    print(make_mcq(ex["support"]))
    print("real answer:", ex["correct_answer"], "\n")

# ---------- 5. Publish to Hugging Face (already done) ----------
# from huggingface_hub import login
# login()  
# model.push_to_hub("banwaa/generator-mcq")
# tok.push_to_hub("banwaa/generator-mcq")