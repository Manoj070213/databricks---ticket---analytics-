from fastapi import FastAPI, HTTPException, Depends, Header, Request
from pydantic import BaseModel
import pandas as pd
import os
import time
import logging
from dotenv import load_dotenv
from google import genai

# ---------- LOGGING SETUP ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("api.log"),   # writes to api.log file
        logging.StreamHandler(),          # also prints to console
    ],
)
logger = logging.getLogger("ticket_api")

# Load environment variables (your Gemini key from .env)
load_dotenv()
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Load the tagged tickets once when the server starts
df = pd.read_csv("tagged_export.csv")
logger.info(f"Loaded {len(df)} tickets from tagged_export.csv")

app = FastAPI(title="Support Ticket Analytics API")

# ---------- OBSERVABILITY: log every request + timing ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response

API_KEY = "manoj-secret-key-123"

def verify_api_key(x_api_key: str = Header(default=None)):
    if x_api_key != API_KEY:
        logger.warning("Rejected request: invalid or missing API key")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key

@app.get("/")
def home():
    return {"message": "Support Ticket Analytics API is running", "total_tickets": len(df)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/stats/categories")
def category_stats(auth: str = Depends(verify_api_key)):
    return {"total": len(df), "by_category": df["category"].value_counts().to_dict()}

@app.get("/stats/urgency")
def urgency_stats(auth: str = Depends(verify_api_key)):
    return {"total": len(df), "by_urgency": df["urgency"].value_counts().to_dict()}

@app.get("/stats/sentiment")
def sentiment_stats(auth: str = Depends(verify_api_key)):
    return {"total": len(df), "by_sentiment": df["sentiment"].value_counts().to_dict()}

@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, auth: str = Depends(verify_api_key)):
    match = df[df["ticket_id"] == ticket_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return match.iloc[0].to_dict()

@app.get("/tickets")
def search_tickets(keyword: str = "", category: str = "", limit: int = 10, auth: str = Depends(verify_api_key)):
    result = df
    if keyword:
        mask = (result["subject"].str.contains(keyword, case=False, na=False) | result["body"].str.contains(keyword, case=False, na=False))
        result = result[mask]
    if category:
        result = result[result["category"] == category]
    return {"count": len(result), "results": result.head(limit).to_dict(orient="records")}

# ---------- RAG Q&A ENDPOINT ----------

class Question(BaseModel):
    question: str

def retrieve_relevant_tickets(question: str, top_k: int = 8):
    """RETRIEVAL step: find tickets whose text overlaps most with the question."""
    q_words = set(question.lower().split())
    def score(row):
        text = (str(row["subject"]) + " " + str(row["body"])).lower()
        return sum(1 for w in q_words if w in text)
    scored = df.copy()
    scored["_score"] = scored.apply(score, axis=1)
    top = scored.sort_values("_score", ascending=False).head(top_k)
    return top[top["_score"] > 0]

@app.post("/ask")
def ask(payload: Question, auth: str = Depends(verify_api_key)):
    question = payload.question
    logger.info(f"RAG question received: {question}")

    # 1. RETRIEVE relevant tickets
    relevant = retrieve_relevant_tickets(question)
    if relevant.empty:
        logger.info("No relevant tickets found for question")
        return {"question": question, "answer": "No relevant tickets found.", "sources": []}

    # 2. AUGMENT: build context from retrieved tickets
    context_lines = []
    for _, r in relevant.iterrows():
        context_lines.append(f"- [{r['ticket_id']}] ({r['category']}, {r['urgency']}, {r['sentiment']}) {r['subject']}: {r['body']}")
    context = "\n".join(context_lines)

    # 3. GENERATE: ask Gemini to answer using ONLY the retrieved context
    prompt = (
        "You are a support analytics assistant. Answer the question using ONLY the "
        "support tickets provided below. Be concise and specific. If the tickets don't "
        "contain the answer, say so.\n\n"
        f"TICKETS:\n{context}\n\n"
        f"QUESTION: {question}\n\nANSWER:"
    )
    response = gemini_client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt,
    )
    logger.info(f"RAG answered using {len(relevant)} source tickets")

    return {
        "question": question,
        "answer": response.text,
        "sources": relevant["ticket_id"].tolist(),
    }