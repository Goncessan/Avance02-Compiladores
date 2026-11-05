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
    ("FIN", r"\n"),
]
EJEMPLOS = {"REG_SANITARIO": "NOC12345-21PE", "LOTE": "LOT2026-X09", "FECHA_EXP": "EXP:2028-12-31",
            "TIPO_PRODUCTO": "FARMA", "ESTADO": "VIGENTE", "DELIMITADOR": ";", "FIN": "\\n"}
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
        if c == "\\":
            c = {"n": "\n"}.get(s.t[s.i], s.t[s.i])
            s.i += 1
            return ("set", frozenset(c))
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
        return "\\n" if cs[0] == "\n" else cs[0]
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
        s.minimizar()

    def minimizar(s):
        nm = s.nombres
        grp = {i: int(i in s.fin) for i in range(s.n)}
        while True:
            ids = {}
            nuevo = {i: ids.setdefault((grp[i], tuple(grp.get(s.delta.get((i, c)), -1) for c in nm)), len(ids))
                     for i in range(s.n)}
            if len(ids) == len(set(grp.values())):
                break
            grp = nuevo
        gd = {(nuevo[i], c): nuevo[j] for (i, c), j in s.delta.items()}
        orden, cola = {nuevo[0]: 0}, deque([nuevo[0]])
        while cola:
            g = cola.popleft()
            for c in nm:
                t = gd.get((g, c))
                if t is not None and t not in orden:
                    orden[t] = len(orden)
                    cola.append(t)
        s.delta = {(orden[g], c): orden[t] for (g, c), t in gd.items()}
        s.fin = {orden[nuevo[i]] for i in s.fin}
        s.n = len(orden)

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
    return toks + [("FIN", "\\n")]


# ------------------------------------------- PARSER (GLC del documento) + AST
PAR = {"LOTE": "FECHA_EXP", "TIPO_PRODUCTO": "ESTADO"}
DL = "TOKEN_DELIMITADOR"


def parser(toks):
    T = lambda i: toks[i][0] if i < len(toks) else "EOF"

    def falla(i, esp):
        extra = f" «{toks[i][1]}»" if i < len(toks) and T(i) != "FIN" else ""
        return None, f"Se esperaba {esp} y se encontró {T(i)}{extra}"

    if T(0) != "REG_SANITARIO":
        return falla(0, "TOKEN_REG_SANITARIO")
    if T(1) != "DELIMITADOR":
        return falla(1, DL)
    i, bl = 2, []
    while True:
        a = T(i)
        if a not in PAR:
            return falla(i, "TOKEN_LOTE o TOKEN_TIPO_PRODUCTO")
        if T(i + 1) != "DELIMITADOR":
            return falla(i + 1, DL)
        if T(i + 2) != PAR[a]:
            return falla(i + 2, "TOKEN_" + PAR[a])
        bl.append((a, toks[i][1], PAR[a], toks[i + 2][1]))
        i += 3
        if T(i) != "DELIMITADOR":
            break
        i += 1
    if T(i) != "FIN":
        return falla(i, "FIN")
    ast = ["S", "  REGISTRO_SANITARIO_COMPLETO", "    CABECERA", f"      TOKEN_REG_SANITARIO: {toks[0][1]}",
           "      TOKEN_DELIMITADOR: ;", "    DETALLE"]
    R, ind = "TOKEN_REG_SANITARIO", 3
    formas = [["S"], ["REGISTRO_SANITARIO_COMPLETO"], ["CABECERA", "DETALLE", "FIN"], [R, DL, "DETALLE", "FIN"]]
    pre = [R, DL]
    for k, (a, x, b, y) in enumerate(bl):
        p, bt = "  " * ind, [f"TOKEN_{a}", DL, f"TOKEN_{b}"]
        ast += [p + "BLOQUE_LOTE", p + f"  TOKEN_{a}: {x}", p + "  TOKEN_DELIMITADOR: ;", p + f"  TOKEN_{b}: {y}"]
        if k < len(bl) - 1:
            ast += [p + "TOKEN_DELIMITADOR: ;", p + "DETALLE"]
            ind += 1
            formas += [pre + ["BLOQUE_LOTE", DL, "DETALLE", "FIN"], pre + bt + [DL, "DETALLE", "FIN"]]
            pre = pre + bt + [DL]
        else:
            formas += [pre + ["BLOQUE_LOTE", "FIN"], pre + bt + ["FIN"]]
    ast.append("    FIN: \\n")
    return (bl, "\n".join(ast), [" ".join(f) for f in formas]), None


# ------------------------------------------------------------ SEMÁNTICO
def semantico(reg, bl, tabla, n, hoy):
    d = {}
    for a, x, b, y in bl:
        if a in d:
            return "RECHAZADO", f"Bloque {a} repetido", None
        d[a], d[b] = x, y
    if "LOTE" not in d:
        return "RECHAZADO", "Falta el bloque LOTE ; FECHA_EXP", None
    lote, fec, tipo, estado = d["LOTE"], d["FECHA_EXP"][4:], d.get("TIPO_PRODUCTO"), d.get("ESTADO")
    try:
        f = datetime.date.fromisoformat(fec)
    except ValueError:
        return "RECHAZADO", f"Fecha inexistente: {fec}", None
    if f.year < int(lote[3:7]):
        return "RECHAZADO", "La fecha de vencimiento es anterior al año del lote", None
    pref = reg[:3] if reg[:3] in ("NOC", "NSO") else reg[:2]
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
             "ast": "", "deriv": [], "estado": "RECHAZADO", "fase": "", "msg": ""}
        err = next((x for t, x in toks if t == "ERROR"), None)
        if err:
            r.update(fase="Léxico", msg=f"Lexema no reconocido: «{err}»")
        else:
            res, e = parser(toks)
            if e:
                r.update(fase="Sintáctico", msg=e)
            else:
                bl, ast, formas = res
                est, msg, fila = semantico(toks[0][1], bl, tabla, n, hoy)
                r.update(fase="Semántico", estado=est, msg=msg, ast=ast, deriv=formas)
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
    return jsonify([{"token": n, "er": a["er"], "ejemplo": EJEMPLOS[n], "afnd": a["afnd"].json(), "afd": a["afd"].json()}
                    for n, a in AUT.items()])


@app.route("/api/compilar", methods=["POST"])
def api_compilar():
    return jsonify(compilar((request.get_json() or {}).get("texto", "")))


@app.route("/api/simular", methods=["POST"])
def api_simular():
    d = request.get_json() or {}
    afd, cad = AUT[d["token"]]["afd"], d.get("cadena", "").replace("\\n", "\n")
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
