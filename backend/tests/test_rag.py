import pytest
from sqlalchemy import update

from app.core.errors import AIServiceError
from app.models import Chunk
from app.services import documents, rag
from app.services.gemini import ChatTurn
from app.services.ingestion import ExtractedDoc, Section
from app.services.rag import FALLBACK_ANSWER, answer_question, classify_smalltalk, is_fallback

LATE_QUESTION = "What is the late submission policy?"


def test_fallback_text_is_exact():
    assert FALLBACK_ANSWER == (
        "I couldn't find that in the knowledge base. "
        "Could you rephrase, or ask about a topic it covers?"
    )


def test_in_scope_question_grounded_with_sources(db, seeded_kb, fake_gemini):
    answer = answer_question(db, LATE_QUESTION, [])
    assert answer.kind == "answer"
    assert answer.grounded is True
    assert answer.answer == fake_gemini.answer
    assert [s.title for s in answer.sources] == ["Course Handbook"]
    assert answer.sources[0].url is None


def test_query_embedded_as_retrieval_query(db, seeded_kb, fake_gemini):
    answer_question(db, LATE_QUESTION, [])
    assert fake_gemini.embed_calls[-1] == ([LATE_QUESTION], "RETRIEVAL_QUERY")


def test_out_of_scope_fallback_no_generate(db, seeded_kb, fake_gemini):
    answer = answer_question(db, "What is the capital of Australia?", [])
    assert answer.answer == FALLBACK_ANSWER
    assert answer.grounded is False
    assert answer.kind == "fallback"
    assert answer.sources == []
    assert fake_gemini.generate_calls == []


def test_empty_kb_fallback_no_gemini_calls(db, fake_gemini):
    answer = answer_question(db, LATE_QUESTION, [])
    assert answer.answer == FALLBACK_ANSWER
    assert answer.grounded is False
    assert fake_gemini.embed_calls == []
    assert fake_gemini.generate_calls == []


@pytest.mark.parametrize("message", ["hi", "Hello!", "  hey there ", "thank you", "Thanks."])
def test_smalltalk_friendly_not_fallback(db, seeded_kb, fake_gemini, message):
    calls_before = len(fake_gemini.embed_calls)
    answer = answer_question(db, message, [])
    assert answer.kind == "greeting"
    assert answer.grounded is False
    assert answer.answer != FALLBACK_ANSWER
    assert answer.sources == []
    assert len(fake_gemini.embed_calls) == calls_before
    assert fake_gemini.generate_calls == []


def test_greeting_works_with_empty_kb(db, fake_gemini):
    assert answer_question(db, "hello", []).kind == "greeting"


def test_classify_smalltalk():
    assert classify_smalltalk("Good morning!") == "greeting"
    assert classify_smalltalk("thx") == "thanks"
    assert classify_smalltalk("hi, what is the late policy?") is None
    assert classify_smalltalk("history of hiking") is None


def test_greeting_with_question_goes_to_rag(db, seeded_kb, fake_gemini):
    answer = answer_question(db, "hi, what is the late submission policy?", [])
    assert answer.kind == "answer"
    assert answer.grounded is True


def test_follow_up_rewrites_with_history(db, seeded_kb, fake_gemini):
    history = [ChatTurn("user", "Tell me about office hours"), ChatTurn("model", "Tuesdays.")]
    fake_gemini.rewrite_answer = "What is the late submission penalty?"
    answer_question(db, "and the penalty for late work?", history)
    assert fake_gemini.rewrite_calls[0][:2] == history
    assert fake_gemini.rewrite_calls[0][-1].text == "and the penalty for late work?"
    assert fake_gemini.embed_calls[-1][0] == ["What is the late submission penalty?"]


def test_no_rewrite_without_history(db, seeded_kb, fake_gemini):
    answer_question(db, LATE_QUESTION, [])
    assert fake_gemini.rewrite_calls == []


def test_rewrite_failure_falls_back_to_original(db, seeded_kb, fake_gemini):
    fake_gemini.fail_rewrite = True
    history = [ChatTurn("user", "hello"), ChatTurn("model", "Hi!")]
    answer = answer_question(db, LATE_QUESTION, history)
    assert answer.kind == "answer"
    assert fake_gemini.embed_calls[-1][0] == [LATE_QUESTION]


def test_history_passed_to_generate(db, seeded_kb, fake_gemini):
    history = [ChatTurn("user", "hello"), ChatTurn("model", "Hi!")]
    answer_question(db, LATE_QUESTION, history)
    turns = fake_gemini.generate_calls[0][1]
    assert turns[:2] == history
    assert turns[-1].role == "user"


@pytest.mark.parametrize(
    "reply",
    [
        FALLBACK_ANSWER,
        "Sorry — I couldn’t find that in the knowledge base.",
        "I COULDN'T FIND THAT IN THE KNOWLEDGE BASE. Could you rephrase?",
    ],
)
def test_model_fallback_paraphrase_detected(db, seeded_kb, fake_gemini, reply):
    fake_gemini.answer = reply
    answer = answer_question(db, LATE_QUESTION, [])
    assert answer.grounded is False
    assert answer.kind == "fallback"
    assert answer.sources == []
    assert answer.answer == FALLBACK_ANSWER


def test_is_fallback_ignores_normal_answers():
    assert not is_fallback("The policy deducts ten percent per day.")


def test_sources_deduplicated(db, fake_gemini):
    doc = ExtractedDoc(
        "Policies",
        "text",
        "policies.md",
        [
            Section("Late submission policy part one.", None),
            Section("Late submission policy part two.", None),
        ],
    )
    documents.ingest(db, doc, user_id=None)
    answer = answer_question(db, "late submission policy", [])
    assert len(answer.sources) == 1
    assert answer.sources[0].title == "Policies"


def test_url_sources_include_url(db, fake_gemini):
    doc = ExtractedDoc(
        "Web page",
        "url",
        "https://example.com/late",
        [Section("Late submission policy online.", None)],
    )
    documents.ingest(db, doc, user_id=None)
    answer = answer_question(db, "late submission policy", [])
    assert answer.sources[0].url == "https://example.com/late"


def test_context_delimited_and_question_appended(db, seeded_kb, fake_gemini):
    answer_question(db, LATE_QUESTION, [])
    system, turns = fake_gemini.generate_calls[0]
    assert system == rag.SYSTEM_PROMPT
    prompt = turns[-1].text
    assert prompt.startswith("<context>\n[1] Course Handbook\n")
    assert "</context>" in prompt
    assert prompt.endswith(f"Question: {LATE_QUESTION}")


def test_stale_model_chunks_ignored(db, seeded_kb, fake_gemini):
    db.execute(update(Chunk).values(embedding_model="old-model"))
    db.commit()
    answer = answer_question(db, LATE_QUESTION, [])
    assert answer.answer == FALLBACK_ANSWER
    assert fake_gemini.embed_calls[-1][1] == "RETRIEVAL_DOCUMENT"  # only the seeding call


def test_gemini_error_propagates(db, seeded_kb, fake_gemini):
    fake_gemini.fail_with = AIServiceError("quota")
    with pytest.raises(AIServiceError):
        answer_question(db, LATE_QUESTION, [])


def test_cli_search_prints_scores(db, seeded_kb, capsys):
    from app import cli

    assert cli.main(["search", LATE_QUESTION]) == 0
    output = capsys.readouterr().out
    assert "Course Handbook" in output
    assert "RAG_MIN_SCORE" in output
