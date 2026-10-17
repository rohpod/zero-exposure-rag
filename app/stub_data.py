"""
Canned values used when STUB_MODE is on, so the pipeline and downstream
consumers (red-team harness, dashboard) can be built and tested before
the real retriever, LLM and guards are integrated.
"""

STUB_ANSWER = "This is a stubbed answer. Real generation is not yet connected."
STUB_SOURCES = ["doc_0001"]
STUB_GUARDS = {
    "input": {"label": "safe", "score": 0.01},
    "output": {"redactions": 0},
}
STUB_LATENCY_MS = {
    "input_guard": 1,
    "retrieval": 1,
    "llm": 1,
    "output_guard": 1,
}
