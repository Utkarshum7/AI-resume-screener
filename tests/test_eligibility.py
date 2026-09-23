import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.eligibility import evaluate_eligibility

config = Config()


def test_python_and_ai_present_is_eligible():
    text = "Built a RAG pipeline using LangChain and Python for retrieval-augmented generation."
    result = evaluate_eligibility(text, config)
    assert result.eligible is True
    assert result.rejection_reasons == []


def test_python_only_is_rejected():
    text = "Experienced Python developer. Built REST APIs with Django and PostgreSQL."
    result = evaluate_eligibility(text, config)
    assert result.eligible is False
    assert "No AI/agentic project evidence" in result.rejection_reasons
    assert "No evidence of Python stack" not in result.rejection_reasons


def test_ai_only_without_python_is_rejected():
    text = "Built chatbots using LangChain and OpenAI GPT models with Node.js and Express."
    result = evaluate_eligibility(text, config)
    assert result.eligible is False
    assert "No evidence of Python stack" in result.rejection_reasons


def test_neither_python_nor_ai_is_rejected_with_both_reasons():
    text = "Frontend developer skilled in React, Next.js, TypeScript, and Spring Boot."
    result = evaluate_eligibility(text, config)
    assert result.eligible is False
    assert "No evidence of Python stack" in result.rejection_reasons
    assert "No AI/agentic project evidence" in result.rejection_reasons


def test_js_and_react_alongside_python_and_ai_remains_eligible():
    text = (
        "Full-stack engineer. Frontend built with React and Next.js and TypeScript. "
        "Backend built with Python and FastAPI. Implemented a multi-agent RAG system "
        "using LangGraph and vector embeddings for retrieval."
    )
    result = evaluate_eligibility(text, config)
    assert result.eligible is True
