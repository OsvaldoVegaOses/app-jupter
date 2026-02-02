import asyncio


def test_nucleus_light_endpoint_direct_call(monkeypatch):
    # Stubbed report returned by the nucleus_report used by the router
    stub_report = {
        "llm_summary": "legacy summary",
        "storyline_graphrag": {
            "answer": "storyline ans",
            "is_grounded": True,
            "mode": "grounded",
            "evidence": [],
        },
        "summary_metrics": {"metrics": {"coverage": 0.8}, "checks": []},
    }

    import backend.routers.nucleus as nucleus_router_module


    def fake_nucleus_report(clients, settings, categoria, prompt, project, persist=False):
        return stub_report


    monkeypatch.setattr(nucleus_router_module, "nucleus_report", fake_nucleus_report)

    # Call the router function directly to avoid FastAPI dependency resolution
    result = asyncio.run(nucleus_router_module.nucleus_light("default", "X", clients=None, settings=None))

    assert "storyline" in result
    assert result["storyline"]["answer"] == "storyline ans"
    assert result["audit_summary"] == stub_report["summary_metrics"]
    assert result["llm_summary"] == "legacy summary"
