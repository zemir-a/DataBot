"""Notes -> MCQs. The app calls generate_mcqs (file) or generate_from_text (pasted text).

Each result: {"question": str, "options": [4 strings], "answer_index": int}
"""
import random
import re

from pypdf import PdfReader

MODEL_ID = "banwaa/generator-mcq"
MIN_WORDS = 100
MAX_WORDS = 200

_tok = None
_model = None
_device = None


def _load():
    """Load the model the first time it is needed, not when the app starts."""
    global _tok, _model, _device
    if _model is None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _tok = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID).to(_device)
        _model.eval()
    return _tok, _model, _device


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
    import torch

    tok, model, device = _load()
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


def extract_text(path):
    path = str(path)
    if path.lower().endswith(".txt"):
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    reader = PdfReader(path)
    return " ".join((page.extract_text() or "") for page in reader.pages)


def generate_from_text(text, num_questions=5):
    words = text.split()
    if len(words) < 50:
        raise ValueError(
            "Not enough text to make questions. If this is a scanned PDF, it needs OCR first."
        )

    chunks = []
    i = 0
    while i < len(words):
        size = random.randint(MIN_WORDS, MAX_WORDS)
        chunks.append(" ".join(words[i:i + size]))
        i += size
    chunks = [c for c in chunks if len(c.split()) >= 50]

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


def generate_mcqs(path, num_questions=5):
    """Works for .pdf and .txt files."""
    return generate_from_text(extract_text(path), num_questions)