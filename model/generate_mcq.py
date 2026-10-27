"""PDF -> MCQs. This is the one function the app calls.

Returns a list of dicts:
    {"question": str, "options": [4 strings], "answer_index": int}
"""
import random
import re

import torch
from pypdf import PdfReader
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# The fine-tuned model published on Hugging Face (trained with train_sciq.py).
# While testing locally you can point it at a saved folder instead, e.g. "sciq-mcq-t5-final".
MODEL_ID = "banwaa/mcq-generator"

device = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID).to(device)
model.eval()

# Each passage gets a random length between these two values, so questions vary.
MIN_WORDS = 100
MAX_WORDS = 200


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def parse(text):
    m = re.match(
        r"question:(.*?)answer:(.*?)wrong1:(.*?)wrong2:(.*?)wrong3:(.*)", text, re.S
    )
    if not m:
        return None
    q, a, w1, w2, w3 = [s.strip() for s in m.groups()]
    return {"question": q, "answer": a, "distractors": [w1, w2, w3]}


def make_mcq(passage, tries=8):
    inputs = tok("generate mcq: " + passage, return_tensors="pt", truncation=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=128, num_beams=4, repetition_penalty=1.3)
    best = parse(tok.decode(out[0], skip_special_tokens=True))
    if best is None or not best["question"] or not best["answer"]:
        return None

    seen = {norm(best["answer"])}
    pool = []
    for d in best["distractors"]:
        n = norm(d)
        if n and n not in seen:
            seen.add(n)
            pool.append(d)

    if len(pool) < 3:
        with torch.no_grad():
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
        return None
    return {"question": best["question"], "answer": best["answer"], "distractors": pool[:3]}


def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    return " ".join((page.extract_text() or "") for page in reader.pages)


def generate_mcqs(pdf_path, num_questions=5):
    text = extract_text(pdf_path)
    words = text.split()
    if len(words) < 50:
        raise ValueError("Not enough text in this PDF. If it's scanned, it needs OCR first.")

    chunks = []
    i = 0
    while i < len(words):
        size = random.randint(MIN_WORDS, MAX_WORDS)  # a new random length each time
        chunks.append(" ".join(words[i:i + size]))
        i += size
    chunks = [c for c in chunks if len(c.split()) >= 50]  # drop tiny leftovers

    # Spread questions across the whole document, not just the first pages
    order = list(range(len(chunks)))
    random.shuffle(order)

    results, used_questions = [], set()
    for idx in order:
        if len(results) >= int(num_questions):
            break
        mcq = make_mcq(chunks[idx])
        if mcq is None or norm(mcq["question"]) in used_questions:
            continue
        used_questions.add(norm(mcq["question"]))

        options = [mcq["answer"]] + mcq["distractors"]
        random.shuffle(options)
        results.append(
            {
                "question": mcq["question"],
                "options": options,
                "answer_index": options.index(mcq["answer"]),
            }
        )
    return results