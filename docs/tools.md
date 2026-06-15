<p align="center">
  <picture>
    <img src="../images/PyramLogo.png" alt="Pyram Logo" width="120"/>
  </picture>
  <br>
  <strong>Pyram.tools</strong> — Ferramentas IA com schema automático e cache
</p>

---

## 📋 API Reference

```python
from Pyram.tools import (
    tool,              # decorator: @tool(info="...")
    sch, sch_ant, sch_gem,  # schemas por provedor
    schemas, schemas_anthropic, schemas_gemini,  # aliases legíveis
    exec, exec_tc,     # execução de tool_calls
    execute, execute_tool_calls,  # aliases legíveis
    listar,            # lista ferramentas registradas
    clear,             # limpa registro
    cache_clear,       # limpa cache
    all,               # alias para sch()
)
```

---

## 🎯 Decorator `@tool`

Registra uma função como ferramenta com **schema JSON gerado automaticamente** — incluindo tipos, parâmetros obrigatórios/opcionais e docstring.

```python
from Pyram.tools import tool

# Schema gerado:
# {
#   "name": "buscar_voos",
#   "description": "Busca voos disponíveis",
#   "parameters": {
#     "type": "object",
#     "properties": {
#       "origem":  {"type": "string", "description": "Código do aeroporto de origem"},
#       "destino": {"type": "string", "description": "Código do aeroporto de destino"},
#       "max_preco": {"type": "number", "description": "buscar_voos"}
#     },
#     "required": ["origem", "destino"]
#   }
# }
@tool(info="Busca voos disponíveis")
def buscar_voos(origem: str, destino: str, max_preco: float = 1000) -> list[dict]:
    """Retorna lista de voos entre dois aeroportos."""
    return [
        {"cia": "LATAM", "preco": 890},
        {"cia": "GOL", "preco": 750},
    ]
```

### Como funciona

1. **Nome** → `function.__name__`
2. **Descrição** → `info` parameter (fallback: primeira linha da docstring, fallback: nome da função)
3. **Parâmetros** → `inspect.signature()` + `get_type_hints()`
4. **Tipos** → Mapeamento automático: `str→string`, `int→integer`, `float→number`, `bool→boolean`, `list→array`, `dict→object`
5. **Obrigatoriedade** → Parâmetros sem default são `required`
6. **Retorno** → Serializado como JSON automaticamente

### Múltiplas tools

```python
@tool(info="Previsão do tempo para uma cidade")
def previsao_tempo(cidade: str, dias: int = 5) -> dict:
    return {"cidade": cidade, "temp": 28, "umidade": 65}

@tool(info="Calculadora de IMC")
def calcular_imc(peso: float, altura: float) -> float:
    return peso / (altura ** 2)
```

---

## 📐 Schemas

### OpenAI / DeepSeek / Groq

```python
from Pyram.tools import sch, schemas

sch() == schemas()  # True (alias)
# → [{"type": "function", "function": {"name": ..., "parameters": ...}}]
```

### Anthropic

```python
from Pyram.tools import sch_ant, schemas_anthropic

sch_ant() == schemas_anthropic()  # True
# → [{"name": ..., "description": ..., "input_schema": ...}]
```

### Gemini

```python
from Pyram.tools import sch_gem, schemas_gemini

sch_gem() == schemas_gemini()  # True
# → [{"functionDeclarations": [{"name": ..., "parameters": ...}]}]
```

---

## ⚡ Execução

### `exec(response, use_cache=False)`

Executa tool_calls a partir de um `CompletionResponse`:

```python
from Pyram.tools import exec

resp = ia.completetion("Quanto é 2+3?", tools=sch())
resultados = exec(resp, use_cache=True)

for r in resultados:
    print(r["tool_call_id"], r["name"], r["content"])
```

### `exec_tc(tool_calls, use_cache=False)`

Executa tool_calls a partir de uma lista de `ToolCall`:

```python
from Pyram.tools import exec_tc
from Pyram.llm import ToolCall

tc = ToolCall(id="1", name="calcular_imc", arguments='{"peso": 70, "altura": 1.75}')
resultados = exec_tc([tc])
```

### `execute` / `execute_tool_calls`

Aliases legíveis:

```python
from Pyram.tools import execute, execute_tool_calls

execute(response) == exec(response)              # True
execute_tool_calls(tcs) == exec_tc(tcs)          # True
```

---

## 💾 Cache

```python
from Pyram.tools import cache_clear

# Cache automático por (nome_da_tool + argumentos_hash)
resp = ia.completetion("Preço do dólar?", tools=sch())
exec(resp, use_cache=True)   # primeira execução → salva
exec(resp, use_cache=True)   # segunda → cache hit

cache_clear()  # limpa todo o cache de tools
```

### Estrutura do cache

```
.PyramCache/tools/
├── add:a1b2c3d4e5f6...    # hash de {"a": 2, "b": 3}
├── buscar_voos:f9e8d7c6...  # hash de {"origem": "GRU", "destino": "CGH"}
└── ...
```

---

## 🧹 Utilitários

```python
from Pyram.tools import listar, clear, erro

listar()  # → ["buscar_voos", "previsao_tempo", "calcular_imc"]

clear()   # remove todas as tools do registro

# erro() é usado internamente para tool calls mal-sucedidas
```

---

## 🎯 Exemplo completo

```python
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec, listar

# 1. Registrar ferramentas
@tool(info="Busca produtos em estoque")
def estoque(categoria: str) -> list[dict]:
    return [{"nome": "Notebook", "qtd": 15}]

@tool(info="Calcula frete por CEP")
def frete(cep: str, peso: float) -> float:
    return 25.90 if "013" in cep else 45.00

print("Tools:", listar())

# 2. Chamar LLM com schemas
ia = DeepSeek(api_key="sk-...", use_cache=True)
resp = ia.completetion(
    "Tem notebook em estoque? Qual o frete para CEP 01310-000?",
    tools=sch(),
    tool_choice="auto",
)

# 3. Executar ferramentas chamadas
resultados = exec(resp, use_cache=True)
for r in resultados:
    print(f"⚡ {r['name']}: {r['content']}")
```
