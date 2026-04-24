import os


def analyze_with_crewai(product, persona_outcomes, scenario_facts):
    """Use CrewAI when available; otherwise return None for deterministic fallback."""
    use_llm = os.getenv("CREWAI_USE_LLM", "false").lower() == "true"
    if not use_llm or not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from crewai import Agent, Crew, Process, Task
    except Exception:
        return None

    facts = {
        "product": product,
        "persona_outcomes": persona_outcomes,
        "scenario_facts": scenario_facts,
    }

    analyst = Agent(
        role="Shell Select Locality Demand Analyst",
        goal="Decide whether the tested product should be stocked using only the provided simulation facts.",
        backstory=(
            "You specialize in convenience retail, locality behavior, and route-grounded demand. "
            "You never invent distances, timings, stores, or persona claims."
        ),
        verbose=False,
    )

    task = Task(
        description=(
            "Analyze this Shell Select product test. Use only these facts: "
            f"{facts}. Return a concise product recommendation, likely buyer segments, "
            "non-buyer reasons, and 3 route-grounded persona quotes."
        ),
        expected_output="A concise JSON-like markdown report with recommendation, reasons, quotes, and risks.",
        agent=analyst,
    )

    crew = Crew(
        agents=[analyst],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff(inputs={"facts": facts})
    return str(result)

