"""
Vergi/tutulma formulaları üçün MƏHDUDLAŞDIRILMIŞ (sandboxed) skript mühərriki.

Bu, `eval()`/`exec()`-in AÇIQ verilənlər bazası girişindən (istifadəçinin
"Vergi formulaları" səhifəsindən yazdığı skriptdən) BİRBAŞA çağırılması ilə
bağlı TƏHLÜKƏSİZLİK RİSKİNƏ görə yazılıb: adi Python `exec()` istənilən
kodu (fayl sistemi, şəbəkə, digər modellər və s. daxil olmaqla) icra edə
bilər. Əvəzində, skript əvvəlcə `ast` ilə təhlil olunur və YALNIZ aşağıda
açıq şəkildə İCAZƏ VERİLƏN node tiplərindən/funksiya adlarından ibarətdirsə
icra olunur — əks halda `FormulaError` qaldırılır. Bu, "hər şeyə icazə,
bəzilərini qadağan et" əvəzinə "heç nəyə icazə yox, YALNIZ ağ siyahını aç"
prinsipi ilə işləyir ki, yeni, gözlənilməz Python konstruksiyaları
(məs. `__import__`, atribut zənciri ilə sandbox-dan çıxma hiylələri və s.)
default olaraq DAİM bloklu qalsın.

Dəstəklənən skript dili (istifadəçiyə göstərilən qeydlərlə eynidir):
  - Dəyişən: `gross` (giriş, GROSS məbləği) HƏMİŞƏ mövcuddur.
  - Skript NƏTİCƏNİ `result` dəyişəninə YAZMALIDIR.
  - `if` / `elif` / `else` şərtləri.
  - `for x in range(...)` dövrləri (YALNIZ `range()` üzərində, iterasiya
    sayı MAX_LOOP_ITERATIONS ilə məhdudlaşdırılıb — sonsuz dövr riski
    olmasın deyə `while` İCAZƏ VERİLMİR).
  - Adi riyazi/müqayisə/məntiqi əməliyyatlar (+ - * / // % ** və s.).
  - Funksiyalar: round, min, max, abs, int, float, range — bundan
    artığına (o cümlədən atribut girişinə, `__`-lə başlayan hər şeyə,
    import-a, lambda-ya, funksiya/sinif tərifinə) İCAZƏ VERİLMİR.
"""

import ast


class FormulaError(Exception):
    """Skriptdə sintaksis/qadağan olunmuş konstruksiya/icra xətası."""


MAX_LOOP_ITERATIONS = 100_000

ALLOWED_CALL_NAMES = {"round", "min", "max", "abs", "int", "float", "range"}

# Ağ siyahı: skriptdə RASTLAŞA BİLƏN hər node tipi burada olmalıdır —
# olmayan bir tip görünərsə (məs. Import, Attribute, Lambda, FunctionDef,
# While, ListComp) `FormulaError` qaldırılır.
ALLOWED_NODE_TYPES = (
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.If,
    ast.IfExp,
    ast.For,
    ast.Pass,
    ast.Break,
    ast.Continue,
    ast.Compare,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Call,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UAdd,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def _validate(script):
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as e:
        raise FormulaError(f"Sintaksis xətası: {e.msg} (sətir {e.lineno})")

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODE_TYPES):
            raise FormulaError(
                f"İcazə verilməyən konstruksiya: {type(node).__name__}. "
                "Yalnız dəyişənlər, riyazi/şərt ifadələri, `if/elif/else` "
                "və `for x in range(...)` dövrləri istifadə edin."
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_CALL_NAMES:
                raise FormulaError(
                    "Yalnız bu funksiyalara icazə verilir: "
                    + ", ".join(sorted(ALLOWED_CALL_NAMES))
                )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise FormulaError("'__' ilə başlayan adlara icazə verilmir.")
        if isinstance(node, ast.For):
            # `for x in <iter>` — <iter> mütləq `range(...)` çağırışı olmalıdır
            # (sonsuz/nəzarətsiz dövr riskini aradan qaldırmaq üçün).
            it = node.iter
            if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"):
                raise FormulaError("`for` dövrü yalnız `for x in range(...)` formasında ola bilər.")

    return tree


def _guarded_range(*args):
    r = range(*args)
    if len(r) > MAX_LOOP_ITERATIONS:
        raise FormulaError(f"`range()` {MAX_LOOP_ITERATIONS}-dan çox təkrara icazə vermir.")
    return r


def validate_formula(script):
    """Skripti YALNIZ təhlil edir (icra ETMİR) — "Yadda saxla" zamanı
    doğrulama üçün. Problem varsa FormulaError qaldırır."""
    _validate(script)


def evaluate_formula(script, gross):
    """Skripti verilmiş `gross` dəyəri ilə TƏHLÜKƏSİZ mühitdə icra edib
    `result` dəyişəninin son qiymətini (float) qaytarır."""
    tree = _validate(script)
    try:
        code = compile(tree, "<tax_formula>", "exec")
    except Exception as e:  # pragma: no cover - _validate normally catches this
        raise FormulaError(f"Kompilyasiya xətası: {e}")

    safe_builtins = {
        "round": round,
        "min": min,
        "max": max,
        "abs": abs,
        "int": int,
        "float": float,
        "range": _guarded_range,
    }
    sandbox_globals = {"__builtins__": safe_builtins}
    sandbox_locals = {"gross": float(gross)}

    try:
        exec(code, sandbox_globals, sandbox_locals)
    except FormulaError:
        raise
    except Exception as e:
        raise FormulaError(f"İcra xətası: {e}")

    if "result" not in sandbox_locals:
        raise FormulaError("Skript 'result' dəyişənini təyin etməlidir.")

    try:
        return float(sandbox_locals["result"])
    except (TypeError, ValueError):
        raise FormulaError("'result' ədədə çevrilə bilmədi.")
