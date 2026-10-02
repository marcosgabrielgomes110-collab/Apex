"""Regressões: cada teste aqui cobre um bug corrigido.

Todos falhavam antes das correções — servem de rede de segurança para que
subflows, paralelismo e control-flow não quebrem de novo em silêncio.
"""
from __future__ import annotations

import time
import warnings

import pytest

from apex.graph import (
    FlowConditionError,
    FlowTaskError,
    FlowTimeoutError,
    flow,
    parallel,
    state,
    task,
)
from apex.graph._state import State


# ── subflows ────────────────────────────────────────────────


class TestSubflow:
    def test_parent_state_survives_subflow(self):
        @flow
        def interno():
            state.do_interno = True

        def antes():
            state.do_pai = "importante"

        @flow
        def externo():
            antes()
            interno()

        r = externo.run()
        assert r.do_pai == "importante"
        assert r.do_interno is True

    def test_subflow_does_not_self_reference(self):
        @flow
        def sub():
            state.x = 1

        @flow
        def pai():
            sub()

        r = pai.run()
        assert r.to_dict() == {"x": 1}
        assert "sub" not in r.to_dict()

    def test_conditional_after_subflow(self):
        @flow
        def sub():
            state.valor = 1

        def ramo_true():
            state.ramo = "then"

        @flow
        def com_if():
            sub()
            if state.valor == 1:
                ramo_true()

        assert com_if.run().ramo == "then"

    def test_subflow_sees_parent_state(self):
        @flow
        def interno():
            state.lido = state.origem

        def antes():
            state.origem = "pai"

        @flow
        def externo():
            antes()
            interno()

        assert externo.run().lido == "pai"

    def test_subflow_with_args_is_rejected(self):
        @flow
        def interno():
            pass

        @flow
        def externo():
            interno(1)

        with pytest.raises(TypeError, match="não aceita argumentos"):
            externo.run()

    def test_nested_subflows_share_state(self):
        @flow
        def n1():
            state.a = 1

        @flow
        def n2():
            n1()
            state.b = state.a + 1

        @flow
        def n3():
            n2()
            state.c = state.b + 1

        assert n3.run().c == 3


# ── control flow dentro de paralelismo ──────────────────────


class TestControlFlowInsideParallel:
    def test_conditional_is_honored(self):
        log = []

        def a():
            log.append("a")

        def b():
            log.append("b")

        @flow
        def f():
            with parallel():
                if False:
                    a()
                b()

        f.run()
        assert log == ["b"]

    def test_loop_is_honored(self):
        log = []

        def a():
            log.append("a")

        def b():
            log.append("b")

        @flow
        def f():
            with parallel():
                while state.i < 3:
                    state.i += 1
                    a()
                b()

        r = f.run(state={"i": 0})
        assert (log, r.i) == (["a", "a", "a", "b"], 3)

    def test_nested_parallel(self):
        log = []

        def a():
            log.append("a")

        def b():
            log.append("b")

        @flow
        def f():
            with parallel():
                with parallel():
                    a()
                    b()

        f.run()
        assert sorted(log) == ["a", "b"]


class TestCombinacoes:
    """Os padrões que a documentação anuncia, combinados."""

    @staticmethod
    def _agentes():
        @flow
        def agente_a():
            state.res_a = "a"

        @flow
        def agente_b():
            state.res_b = "b"

        return agente_a, agente_b

    def test_subflows_inside_parallel(self):
        agente_a, agente_b = self._agentes()

        @flow
        def supervisor():
            with parallel():
                agente_a()
                agente_b()

        r = supervisor.run()
        assert (r.res_a, r.res_b) == ("a", "b")

    def test_parallel_inside_loop(self):
        def drena():
            state.total += 1

        @flow
        def f():
            while state.i < 3:
                with parallel():
                    drena()
                state.i += 1

        r = f.run(state={"i": 0, "total": 0})
        assert (r.i, r.total) == (3, 3)

    def test_parallel_inside_conditional(self):
        agente_a, agente_b = self._agentes()

        @flow
        def f():
            if state.ativo:
                with parallel():
                    agente_a()
                    agente_b()

        r_on = f.run(state={"ativo": True})
        assert (r_on.res_a, r_on.res_b) == ("a", "b")

        r_off = f.run(state={"ativo": False})
        assert r_off.get("res_a") is None

    def test_loop_conditional_and_parallel_together(self):
        agente_a, agente_b = self._agentes()

        @flow
        def f():
            while state.n < 2:
                if state.n == 0:
                    with parallel():
                        agente_a()
                else:
                    with parallel():
                        agente_b()
                state.n += 1

        r = f.run(state={"n": 0})
        assert (r.res_a, r.res_b) == ("a", "b")

    def test_plain_with_still_inlines(self):
        class Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def marca():
            state.marcado = True

        @flow
        def f():
            with Ctx():
                marca()

        assert f.run().marcado is True


# ── merge de estado no paralelismo ──────────────────────────


class TestParallelStateMerge:
    def test_updates_existing_key(self):
        def p1():
            state.count = "P1"

        def p2():
            state.novo = "P2"

        @flow
        def f():
            with parallel():
                p1()
                p2()

        r = f.run(state={"count": "inicial"})
        assert r.count == "P1"
        assert r.novo == "P2"

    def test_conflicting_writes_warn(self):
        def c1():
            state.x = 1

        def c2():
            state.x = 2

        @flow
        def f():
            with parallel():
                c1()
                c2()

        with pytest.warns(UserWarning, match="mesmas chaves"):
            r = f.run()
        # last-write-wins na ordem do corpo: determinístico
        assert r.x == 2

    def test_no_warning_without_conflict(self):
        def c1():
            state.x = 1

        def c2():
            state.y = 2

        @flow
        def f():
            with parallel():
                c1()
                c2()

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            r = f.run()
        assert (r.x, r.y) == (1, 2)


# ── timeout ─────────────────────────────────────────────────


class TestTimeout:
    def test_timeout_does_not_block(self):
        @task(timeout=1)
        def lenta():
            time.sleep(30)
            state.nunca = True

        @flow
        def f():
            lenta()

        inicio = time.time()
        with pytest.raises(TimeoutError):
            f.run()
        assert time.time() - inicio < 5

    def test_timeout_error_is_flow_error(self):
        @task(timeout=1)
        def lenta():
            time.sleep(30)

        @flow
        def f():
            lenta()

        with pytest.raises(FlowTimeoutError):
            f.run()

    def test_partial_writes_are_discarded_on_timeout(self):
        @task(timeout=1)
        def lenta():
            state.parcial = "vazou"
            time.sleep(30)

        def depois():
            state.seguiu = True

        @flow
        def f():
            lenta()
            depois()

        with pytest.raises(TimeoutError):
            f.run()

        # o estado da execução que estourou não vaza para o próximo run
        @flow
        def proximo():
            state.novo = True

        assert "parcial" not in proximo.run().to_dict()

    def test_writes_are_applied_on_success(self):
        @task(timeout=5)
        def rapida():
            state.ok = 42

        @flow
        def f():
            rapida()

        assert f.run().ok == 42


# ── resolução de chamadas ───────────────────────────────────


class TestCallResolution:
    def test_builtin_call_in_flow_body(self):
        registro = []

        def coleta():
            registro.append("coleta")

        @flow
        def f():
            print("saida inline")
            coleta()

        f.run()
        assert registro == ["coleta"]

    def test_method_call_in_flow_body(self):
        class Servico:
            def __init__(self):
                self.chamadas = 0

            def executar(self):
                self.chamadas += 1

        svc = Servico()

        @flow
        def f():
            svc.executar()

        f.run()
        assert svc.chamadas == 1

    def test_task_receives_arguments(self):
        recebidos = []

        def soma(a, b):
            recebidos.append(a + b)

        @flow
        def f():
            soma(2, 3)

        f.run()
        assert recebidos == [5]

    def test_task_receives_state_arguments(self):
        recebidos = []

        def guarda(valor):
            recebidos.append(valor)

        @flow
        def f():
            guarda(state.entrada * 2)

        f.run(state={"entrada": 21})
        assert recebidos == [42]

    def test_nested_def_in_flow_body(self):
        @flow
        def f():
            def passo():
                state.v = 7

            passo()

        assert f.run().v == 7

    def test_assignment_of_call_result(self):
        def produz():
            return 99

        @flow
        def f():
            x = produz()  # noqa: F841 - o alvo vira state.x

        assert f.run().x == 99

    def test_assignment_of_plain_value(self):
        @flow
        def f():
            total = 2 + 3  # noqa: F841 - o alvo vira state.total

        assert f.run().total == 5

    def test_state_augmented_assignment_in_flow_body(self):
        @flow
        def f():
            state.n += 1
            state.n += 1

        assert f.run(state={"n": 0}).n == 2

    def test_unknown_name_still_raises(self):
        @flow
        def f():
            funcao_que_nao_existe()  # noqa: F821

        with pytest.raises(NameError, match="not found in scope"):
            f.run()


# ── condições ───────────────────────────────────────────────


class TestConditions:
    def test_missing_key_raises(self):
        def ramo():
            state.ramo = "a"

        @flow
        def f():
            if state.nao_existe:
                ramo()

        with pytest.raises(FlowConditionError, match="nao_existe"):
            f.run()

    def test_undefined_name_raises(self):
        @flow
        def f():
            if variavel_solta > 1:  # noqa: F821
                pass

        with pytest.raises(FlowConditionError):
            f.run()

    def test_subscript_condition(self):
        def ramo_ok():
            state.ramo = "ok"

        @flow
        def f():
            if state.config["modo"] == "a":
                ramo_ok()

        assert f.run(config={"modo": "a"}).ramo == "ok"

    def test_get_with_default_in_condition(self):
        def outro():
            state.ramo = "outro"

        @flow
        def f():
            if state.get("ausente", {}).get("status") == "ok":
                pass
            else:
                outro()

        assert f.run().ramo == "outro"


# ── ramos e loops ───────────────────────────────────────────


class TestBranches:
    def test_if_elif_else_chain_runs_single_branch(self):
        log = []

        def r1():
            log.append("um")

        def r2():
            log.append("dois")

        def r3():
            log.append("tres")

        @flow
        def f():
            if state.n == 1:
                r1()
            elif state.n == 2:
                r2()
            else:
                r3()

        assert f.run(state={"n": 1}).to_dict() is not None
        assert log == ["um"]

        log.clear()
        f.run(state={"n": 2})
        assert log == ["dois"]

        log.clear()
        f.run(state={"n": 9})
        assert log == ["tres"]

    def test_branch_switches_between_loop_iterations(self):
        log = []

        def t():
            log.append("t")

        def e():
            log.append("e")

        @flow
        def f():
            while state.n < 3:
                if state.n == 1:
                    t()
                else:
                    e()
                state.n += 1

        f.run(state={"n": 0})
        assert log == ["e", "t", "e"]

    def test_loop_body_reruns_tasks(self):
        contador = []

        def passo():
            contador.append(1)

        @flow
        def f():
            while state.i < 3:
                passo()
                state.i += 1

        f.run(state={"i": 0})
        assert len(contador) == 3


# ── estado ──────────────────────────────────────────────────


class TestStateBehaviour:
    def test_empty_nested_dict_is_mutated_in_place(self):
        s = State({"nested": {}})
        s.nested["chave"] = 1
        assert s.to_dict() == {"nested": {"chave": 1}}

    def test_mutation_inside_task_on_empty_nested(self):
        def grava():
            state.resultados["etapa"] = {"status": "ok"}

        @flow
        def f():
            grava()

        r = f.run(state={"resultados": {}})
        assert r.resultados["etapa"]["status"] == "ok"

    def test_state_does_not_leak_after_run(self):
        def grava():
            state.segredo = 1

        @flow
        def f():
            grava()

        f.run()
        with pytest.raises(AttributeError):
            _ = state.segredo

    def test_run_returns_own_state(self):
        def grava():
            state.valor = "a"

        def outro():
            state.valor = "b"

        @flow
        def f1():
            grava()

        @flow
        def f2():
            outro()

        assert f1.run().valor == "a"
        assert f2.run().valor == "b"


# ── erros ───────────────────────────────────────────────────


class TestErrors:
    def test_task_error_wraps_original(self):
        def falha():
            raise ValueError("boom")

        @flow
        def f():
            falha()

        with pytest.raises(FlowTaskError) as exc:
            f.run()
        assert "ValueError: boom" in str(exc.value)


# ── viz ─────────────────────────────────────────────────────


class TestVizKinds:
    def test_parallel_block_is_fork_not_chain(self):
        def a():
            pass

        def b():
            pass

        @flow
        def f():
            with parallel():
                a()
                b()

        dag = f.map()
        assert ("a", "b") not in [(e.source, e.target) for e in dag.edges]
        par = next(n for n in dag.nodes.values() if n.kind == "parallel")
        assert set(par.body_roots) == {"a", "b"}

    def test_inline_nodes_are_rendered(self):
        def a():
            pass

        @flow
        def f():
            a()
            print("oi")

        assert "inline" in [n.kind for n in f.map().nodes.values()]
        assert "print" in f.viz("mermaid")
