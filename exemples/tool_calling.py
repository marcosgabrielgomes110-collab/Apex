"""Tool calling com Pyram — API simplificada.

Uso:
    python exemples/tool_calling.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from Pyram.llm import DeepSeek
from Pyram import tools

load_dotenv()

# ── 1. definir ferramentas ────────────────────────────────────

@tools.tool(info="Obtém a temperatura atual de uma cidade")
def get_weather(city: str):
    dados = {
        "São Paulo": {"temp": 28, "cond": "ensolarado"},
        "Rio de Janeiro": {"temp": 32, "cond": "parcialmente nublado"},
        "Brasília": {"temp": 26, "cond": "seco"},
    }
    return {"cidade": city, **dados.get(city, {"temp": 25, "cond": "desconhecida"})}


@tools.tool(info="Calcula a soma de dois números")
def somar(a: int, b: int):
    return {"resultado": a + b}


# ── 2. iniciar cliente ────────────────────────────────────────

client = DeepSeek(
    model="deepseek-v4-flash",
    api_key=os.getenv("dpsk"),
    temperature=0.3,
    max_tokens=500,
    thinking=False,
)

# ── 3. ciclo completo com nomes curtos ────────────────────────

print("=== Tool calling ===")

resp = client.completetion(
    "Qual a temperatura em São Paulo e em Brasília?",
    tools=tools.sch(),                                  # sch() em vez de schemas()
    tool_choice="auto",
)

if resp.tool_calls:
    for t in resp.tool_calls:
        print(f"  tool: {t.name}({t.arguments})")

    # exec() em vez de execute_tool_calls()
    resultados = tools.exec(resp)                       # exec() direto do response
    for r in resultados:
        print(f"  -> {r['content']}")

    # monta histórico e faz segunda chamada
    from Pyram.llm import ToolResult
    historico = [
        {"role": "user", "content": "Qual a temperatura em São Paulo e em Brasília?"},
    ]
    if len(resp.tool_calls) == 1:
        historico.append(resp.tool_calls[0].to_openai_message())
    else:
        historico.append({
            "role": "assistant", "content": None,
            "tool_calls": [t.to_openai_message()["tool_calls"][0] for t in resp.tool_calls],
        })
    for r in resultados:
        historico.append(ToolResult(r["tool_call_id"], r["name"], r["content"]).to_openai_message())

    resp2 = client.completetion(messages=historico, tools=tools.sch())
    print(f"resposta: {resp2.text()}")
else:
    print(resp.text())

# ── 4. cache ──────────────────────────────────────────────────

print("\n=== Cache ===")

resp = client.completetion(
    "quanto é 5+3?",
    tools=tools.sch(),
    tool_choice="auto",
)

if resp.tool_calls:
    # primeira execução — salva no cache
    r1 = tools.exec_tc(resp.tool_calls, use_cache=True)
    print(f"1ª: {r1[0]['name']} -> {r1[0]['content']}")

    # segunda execução com mesmos args — vem do cache
    r2 = tools.exec_tc(resp.tool_calls, use_cache=True)
    print(f"2ª (cache): {r2[0]['name']} -> {r2[0]['content']}")

# ── 5. listar ferramentas ─────────────────────────────────────

print(f"\nferramentas registradas: {tools.listar()}")

tools.clear()
