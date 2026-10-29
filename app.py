import datetime
from collections import deque
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------- TOKENS y ER
TOKENS = [
    ("REG_SANITARIO", r"(NOC|EN|NSO|RD)[0-9]{5}-[0-9]{2}PE"),
    ("LOTE", r"LOT20[2-9][0-9]-[A-Z0-9]{3,6}"),
    ("FECHA_EXP", r"EXP:20(2[6-9]|3[0-9])-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"),
    ("TIPO_PRODUCTO", r"(FARMA|COSMETICO|MEDICO|DIETA)"),
    ("ESTADO", r"(VIGENTE|OBSERVADO|VENCIDO|CANCELADO)"),
    ("DELIMITADOR", r";"),
]
PREFIJO_TIPO = {"NOC": {"FARMA", "MEDICO"}, "EN": {"FARMA", "MEDICO"},
                "NSO": {"COSMETICO"}, "RD": {"DIETA"}}


# ------------------------------------------------- ER -> AST (parser de ER)
class ER:
    def __init__(s, t):
        s.t, s.i = t, 0

    def peek(s):
        return s.t[s.i] if s.i < len(s.t) else None

    def eat(s):
        s.i += 1
        return s.t[s.i - 1]

    def alt(s):
        xs = [s.cat()]
        while s.peek() == "|":
            s.eat()
            xs.append(s.cat())
        return xs[0] if len(xs) == 1 else ("alt", xs)

    def cat(s):
        xs = []
        while s.peek() not in (None, "|", ")"):
            xs.append(s.rep())
        return ("cat", xs)

    def rep(s):
        a = s.atom()
        while s.peek() in ("*", "+", "?", "{"):
            c = s.eat()
            if c == "*":
                a = ("star", a)
            elif c == "+":
                a = ("cat", [a, ("star", a)])
            elif c == "?":
                a = ("opt", a)
            else:
                j = s.t.index("}", s.i)
                body, s.i = s.t[s.i:j], j + 1
                lo, _, hi = body.partition(",")
                lo = int(lo)
                hi = (int(hi) if hi else None) if "," in body else lo
                tail = [("star", a)] if hi is None else [("opt", a)] * (hi - lo)
                a = ("cat", [a] * lo + tail)
        return a

    def atom(s):
        c = s.eat()
        if c == "(":
            r = s.alt()
            s.eat()
            return r
        if c == "[":
            j = s.t.index("]", s.i)
            body, s.i = s.t[s.i:j], j + 1
            chars, k = set(), 0
            while k < len(body):
                if k + 2 < len(body) and body[k + 1] == "-":
                    chars |= {chr(x) for x in range(ord(body[k]), ord(body[k + 2]) + 1)}
                    k += 3
                else:
                    chars.add(body[k])
                    k += 1
            return ("set", frozenset(chars))
        return ("set", frozenset(c))


def nombre(cs):
    cs = sorted(cs)
    if len(cs) == 1:
        return cs[0]
    out, i = [], 0
    while i < len(cs):
        j = i
        while j + 1 < len(cs) and ord(cs[j + 1]) == ord(cs[j]) + 1:
            j += 1
        out.append(cs[i] if i == j else cs[i] + cs[j] if j == i + 1 else cs[i] + "-" + cs[j])
        i = j + 1
    return "[" + "".join(out) + "]"


# ------------------------------------------------------------------- AFND
class AFND:
    def __init__(s, er):
        s.n, s.e = 0, []
        s.ini, s.fin = s.build(ER(er).alt())
        s.renumerar()

    def new(s):
        s.n += 1
        return s.n - 1

    def build(s, nd):
        k = nd[0]
        if k == "set":
            a, b = s.new(), s.new()
            s.e.append((a, nd[1], b))
            return a, b
        if k == "cat":
            a = s.new()
            cur = a
            for x in nd[1]:
                i, o = s.build(x)
                s.e = [(cur if p == i else p, l, q) for p, l, q in s.e]  # fusiona inicio
                cur = cur if o == i else o
            return a, cur
        a, b = s.new(), s.new()
        if k == "alt":
            for x in nd[1]:
                i, o = s.build(x)
                s.e += [(a, None, i), (o, None, b)]
        else:  # star / opt
            i, o = s.build(nd[1])
            s.e += [(a, None, i), (o, None, b), (a, None, b)]
            if k == "star":
                s.e.append((o, None, i))
        return a, b

    def renumerar(s):
        orden, cola = {s.ini: 0}, deque([s.ini])
        while cola:
            x = cola.popleft()
            for p, _, q in s.e:
                if p == x and q not in orden:
                    orden[q] = len(orden)
                    cola.append(q)
        s.e = [(orden[p], l, orden[q]) for p, l, q in s.e if p in orden]
        s.ini, s.fin, s.n = 0, orden[s.fin], len(orden)

    def cierre(s, S):
        S, pila = set(S), list(S)
        while pila:
            x = pila.pop()
            for p, l, q in s.e:
                if p == x and l is None and q not in S:
                    S.add(q)
                    pila.append(q)
        return frozenset(S)

    def json(s):
        return {"estados": list(range(s.n)), "inicial": 0, "finales": [s.fin],
                "aristas": [{"de": p, "a": q, "et": "ε" if l is None else nombre(l)}
                            for p, l, q in s.e]}


# -------------------------------------------------------------------- AFD
class AFD:
    def __init__(s, nfa):
        sets = list({l for _, l, _ in nfa.e if l})
        grupos = {}
        for ch in sorted(set().union(*sets)):
            grupos.setdefault(tuple(ch in x for x in sets), []).append(ch)
        s.clases = sorted((frozenset(g) for g in grupos.values()), key=min)
        s.cls = {ch: nombre(c) for c in s.clases for ch in c}
        s.nombres = [nombre(c) for c in s.clases]
        ini = nfa.cierre({nfa.ini})
        ids, cola, s.delta = {ini: 0}, deque([ini]), {}
        while cola:
            S = cola.popleft()
            for c in s.clases:
                rep = min(c)
                T = nfa.cierre({q for p, l, q in nfa.e if p in S and l and rep in l})
                if not T:
                    continue
                if T not in ids:
                    ids[T] = len(ids)
                    cola.append(T)
                s.delta[(ids[S], nombre(c))] = ids[T]
        s.n = len(ids)
        s.fin = {i for S, i in ids.items() if nfa.fin in S}

    def paso(s, st, ch):
        c = s.cls.get(ch)
        return s.delta.get((st, c)) if c else None

    def prefijo(s, txt, i):
        """Longest match desde i. Devuelve fin del lexema o -1."""
        st, ult = 0, -1
        for j in range(i, len(txt)):
            st = s.paso(st, txt[j])
            if st is None:
                break
            if st in s.fin:
                ult = j + 1
        return ult

    def json(s):
        tabla = {str(i): {c: s.delta[(i, c)] for c in s.nombres if (i, c) in s.delta}
                 for i in range(s.n)}
        aristas = [{"de": p, "a": q, "et": c} for (p, c), q in s.delta.items()]
        alfabeto = nombre(set(s.cls))
        delta = [f"δ(q{p}, {c}) = q{q}" for (p, c), q in sorted(s.delta.items())]
        return {"estados": list(range(s.n)), "inicial": 0, "finales": sorted(s.fin),
                "clases": s.nombres, "tabla": tabla, "aristas": aristas,
                "quintupla": {"Q": [f"q{i}" for i in range(s.n)], "Sigma": alfabeto,
                              "delta": delta, "q0": "q0", "F": [f"q{i}" for i in sorted(s.fin)]}}


AUT = {}
for _nom, _er in TOKENS:
    _n = AFND(_er)
    AUT[_nom] = {"er": _er, "afnd": _n, "afd": AFD(_n)}


# ------------------------------------------------------------- LEXER (usa AFD)
def lexer(linea):
    toks, i = [], 0
    while i < len(linea):
        if linea[i].isspace():
            i += 1
            continue
        mejor = (-1, None)
        for nom, _ in TOKENS:
            f = AUT[nom]["afd"].prefijo(linea, i)
            if f > mejor[0]:
                mejor = (f, nom)
        if mejor[0] > i:
            toks.append((mejor[1], linea[i:mejor[0]]))
            i = mejor[0]
        else:
            j = i
            while j < len(linea) and not linea[j].isspace() and linea[j] != ";":
                j += 1
            toks.append(("ERROR", linea[i:max(j, i + 1)]))
            i = max(j, i + 1)
    return toks


# ------------------------------------------------------- PARSER (GLC) + AST
# S -> REGISTRO ; REGISTRO -> REG ; LOTE ; FECHA OPCIONAL
# OPCIONAL -> ; TIPO ; ESTADO | ε
def parser(toks):
    patron = ["REG_SANITARIO", "DELIMITADOR", "LOTE", "DELIMITADOR", "FECHA_EXP"]
    if len(toks) > 5:
        patron += ["DELIMITADOR", "TIPO_PRODUCTO", "DELIMITADOR", "ESTADO"]
    for k, esp in enumerate(patron):
        if k >= len(toks):
            return None, f"Falta {esp} al final de la línea"
        if toks[k][0] != esp:
            return None, f"Se esperaba {esp} y se encontró {toks[k][0]} «{toks[k][1]}»"
    if len(toks) > len(patron):
        return None, f"Símbolos sobrantes desde «{toks[len(patron)][1]}»"
    ast = ["S", "  REGISTRO", "    CABECERA", f"      REG_SANITARIO: {toks[0][1]}",
           f"      DELIMITADOR: ;", "    DETALLE", "      BLOQUE_LOTE",
           f"        LOTE: {toks[2][1]}", "        DELIMITADOR: ;",
           f"        FECHA_EXP: {toks[4][1]}"]
    if len(toks) > 5:
        ast += ["      BLOQUE_TIPO", f"        TIPO_PRODUCTO: {toks[6][1]}",
                "        DELIMITADOR: ;", f"        ESTADO: {toks[8][1]}"]
    return "\n".join(ast), None


# ------------------------------------------------------------ SEMÁNTICO
def semantico(toks, tabla, n, hoy):
    reg, lote, fec = toks[0][1], toks[2][1], toks[4][1][4:]
    tipo = toks[6][1] if len(toks) > 5 else None
    estado = toks[8][1] if len(toks) > 5 else None
    try:
        f = datetime.date.fromisoformat(fec)
    except ValueError:
        return "RECHAZADO", f"Fecha inexistente: {fec}", None
    if f.year < int(lote[3:7]):
        return "RECHAZADO", "La fecha de vencimiento es anterior al año del lote", None
    pref = reg[:3] if reg[:3] == "NOC" or reg[:3] == "NSO" else reg[:2]
    if tipo and tipo not in PREFIJO_TIPO[pref]:
        return "RECHAZADO", f"Prefijo {pref} incompatible con {tipo}", None
    if (reg, lote) in tabla:
        return "RECHAZADO", f"Duplicado de la línea {tabla[(reg, lote)]['linea']}", None
    fila = {"registro": reg, "lote": lote, "vence": fec, "tipo": tipo or "-",
            "estado": estado or "-", "linea": n}
    if f < hoy:
        return "OBSERVADO", "Producto vencido", fila
    if (f - hoy).days <= 90:
        return "OBSERVADO", f"Vence en {(f - hoy).days} días", fila
    if estado in ("VENCIDO", "CANCELADO"):
        return "OBSERVADO", f"Registro {estado}", fila
    return "CONFORME", "Cumple las reglas", fila


def compilar(texto):
    hoy, tabla, lineas, grupos = datetime.date.today(), {}, [], {}
    for n, raw in enumerate(texto.splitlines(), 1):
        l = raw.strip()
        if not l or l.startswith("#"):
            continue
        toks = lexer(l)
        for t, lex in toks:
            if t != "ERROR":
                grupos.setdefault(t, [])
                if lex not in grupos[t]:
                    grupos[t].append(lex)
        r = {"n": n, "texto": l, "tokens": [{"tok": t, "lex": x} for t, x in toks],
             "ast": "", "estado": "RECHAZADO", "fase": "", "msg": ""}
        err = next((x for t, x in toks if t == "ERROR"), None)
        if err:
            r.update(fase="Léxico", msg=f"Lexema no reconocido: «{err}»")
        else:
            ast, e = parser(toks)
            if e:
                r.update(fase="Sintáctico", msg=e)
            else:
                est, msg, fila = semantico(toks, tabla, n, hoy)
                r.update(fase="Semántico", estado=est, msg=msg, ast=ast)
                if fila:
                    tabla[(fila["registro"], fila["lote"])] = fila
        lineas.append(r)
    cuenta = lambda e: sum(1 for x in lineas if x["estado"] == e)
    return {"lineas": lineas, "grupos": grupos, "simbolos": list(tabla.values()),
            "stats": {"total": len(lineas), "conforme": cuenta("CONFORME"),
                      "observado": cuenta("OBSERVADO"), "rechazado": cuenta("RECHAZADO")}}


# ----------------------------------------------------------------- RUTAS
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/automatas")
def automatas():
    return jsonify([{"token": n, "er": a["er"], "afnd": a["afnd"].json(), "afd": a["afd"].json()}
                    for n, a in AUT.items()])


@app.route("/api/compilar", methods=["POST"])
def api_compilar():
    return jsonify(compilar((request.get_json() or {}).get("texto", "")))


@app.route("/api/simular", methods=["POST"])
def api_simular():
    d = request.get_json() or {}
    afd, cad = AUT[d["token"]]["afd"], d.get("cadena", "")
    st, ruta = 0, [{"estado": 0, "simbolo": ""}]
    for ch in cad:
        nx = afd.paso(st, ch)
        if nx is None:
            return jsonify({"ok": False, "ruta": ruta, "falla": ch})
        st = nx
        ruta.append({"estado": st, "simbolo": ch})
    return jsonify({"ok": st in afd.fin, "ruta": ruta, "falla": None})


if __name__ == "__main__":
    app.run(debug=True)
