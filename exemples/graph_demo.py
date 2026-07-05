"""Demonstração do Apex.graph — motor de workflows.

Uso:
    python exemples/graph_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apex.graph import flow, task, state, parallel


# ── 1. sequencial simples ────────────────────────────────────

def classify():
    state.intent = "compra"
    print(f"  [classify] intent={state.intent}")

def search():
    state.results = ["notebook A", "notebook B"]
    print(f"  [search] results={state.results}")

def answer():
    print(f"  [answer] recomendando: {state.results[0]}")

@flow
def chatbot():
    classify()
    search()
    answer()

print("=== 1. Sequencial simples ===")
chatbot.run()
print(chatbot.viz())


# ── 2. condicional ───────────────────────────────────────────

def products():
    print("  [products] mostrando catálogo")

def support():
    print("  [support] abrindo chat de suporte")

@flow
def router():
    classify()
    if state.intent == "compra":
        products()
    else:
        support()

print("\n=== 2. Condicional ===")
router.run()
print(router.viz())


# ── 3. loop ──────────────────────────────────────────────────

def think():
    print("  [think] pensando...")

def act():
    state.count += 1
    print(f"  [act] ação {state.count}")
    if state.count >= 3:
        state.finished = True

@flow
def agent_loop():
    while not state.finished:
        think()
        act()

print("\n=== 3. Loop ===")
result = agent_loop.run(state={"finished": False, "count": 0})
print(f"  resultado: count={result.count}")
print(agent_loop.viz())


# ── 4. sequencial com dependências ───────────────────────────

def check_payment():
    state.payment_ok = True
    print("  [payment] verificado")

def check_stock():
    state.stock_ok = True
    print("  [stock] verificado")

def ship():
    print(f"  [ship] payment={state.payment_ok} stock={state.stock_ok}")

@flow
def order():
    check_payment()
    check_stock()
    ship()

print("\n=== 4. Sequencial com dependências ===")
order.run()
print(order.viz())


# ── 5. @task com retry ───────────────────────────────────────

_counter = 0

@task(retry=3)
def flaky():
    global _counter
    _counter += 1
    if _counter < 3:
        raise RuntimeError(f"falha #{_counter}")
    state.ok = True
    print(f"  [flaky] tentativa {_counter} — sucesso")

def done():
    print(f"  [done] ok={state.ok}")

@flow
def resilient():
    flaky()
    done()

print("\n=== 5. @task(retry=3) ===")
resilient.run()
print(resilient.viz())


# ── 6. visualização ──────────────────────────────────────────

print("\n=== 6. Visualização chatbot ===")
print(chatbot.viz())

try:
    chatbot.viz_svg("pyram_chatbot.svg")
    print("SVG exportado: pyram_chatbot.svg")
except Exception as e:
    print(f"(SVG skip: {e})")
