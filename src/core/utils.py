"""
Lab 11 — Helper Utilities
"""
import openai

try:
    from deepeval.tracing import observe
except ImportError:
    # Fallback keeps runtime stable if deepeval isn't installed yet.
    def observe(*args, **kwargs):
        def _decorator(func):
            return func

        return _decorator


@observe(
    name="chat_with_agent",
    type="agent",
    model="gpt-4o-mini",
    input=lambda agent, runner, user_message, session_id=None: {
        "agent_name": getattr(agent, "name", "unknown_agent"),
        "runner_app": getattr(runner, "app_name", "unknown_runner"),
        "user_message": user_message,
        "session_id": session_id,
    },
    output=lambda result: {"response": result[0], "session": result[1]},
    capture_input=False,
    capture_output=False,
)
async def chat_with_agent(agent, runner, user_message: str, session_id=None):
    """Send a message to the agent and get the response."""
    active_user_message = user_message

    # Input guardrails (pre-LLM)
    for plugin in getattr(agent, "plugins", []):
        if hasattr(plugin, "on_user_message_callback"):
            replacement = await plugin.on_user_message_callback(
                user_message=active_user_message
            )
            if replacement is not None:
                return replacement, {"session_id": session_id}

    client = openai.OpenAI()
    response = client.responses.create(
        model=agent.model,
        input=[
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": active_user_message},
        ],
    )
    final_response = response.output_text or ""

    # Output guardrails (post-LLM)
    for plugin in getattr(agent, "plugins", []):
        if hasattr(plugin, "after_model_callback"):
            final_response = await plugin.after_model_callback(
                llm_response=final_response
            )

    return final_response, {"session_id": session_id}
