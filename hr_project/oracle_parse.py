"""Oracle 'Insert into ... Values (...)' skript parseri (yalnız INSERT-lər)."""
import re, datetime

def _read_term(s, i):
    """Bir termi oxuyur (sətir, CHR(n), TO_DATE, NULL, ədəd). (dəyər, yeni_i)."""
    n = len(s)
    if s[i] == "'":
        j, buf = i + 1, []
        while True:
            if s[j] == "'":
                if j + 1 < n and s[j + 1] == "'":
                    buf.append("'"); j += 2; continue
                break
            buf.append(s[j]); j += 1
        return ''.join(buf), j + 1
    m = re.compile(r'CHR\(\s*(\d+)\s*\)', re.I).match(s, i)
    if m:
        return chr(int(m.group(1))), m.end()
    m = re.compile(r"TO_DATE\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)", re.I).match(s, i)
    if m:
        txt, fmt = m.group(1), m.group(2).upper()
        if fmt == 'DD/MM/YYYY':
            v = datetime.datetime.strptime(txt, '%d/%m/%Y').date()
        elif fmt == 'DD/MM/YYYY HH24:MI:SS':
            v = datetime.datetime.strptime(txt, '%d/%m/%Y %H:%M:%S')
        else:
            raise ValueError(f'Naməlum tarix formatı: {fmt}')
        return v, m.end()
    m = re.compile(r'[^,\s|]+').match(s, i)
    tok = m.group(0)
    if tok.upper() == 'NULL':
        return None, m.end()
    return (float(tok) if '.' in tok else int(tok)), m.end()


def _tokenize_values(s):
    """s = mötərizə daxilindəki dəyərlər mətni -> Python dəyərləri siyahısı.
    'a'||CHR(13)||CHR(10)||'b' kimi || birləşdirmələri dəstəklənir."""
    vals, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in ' \t\r\n,':
            i += 1
        if i >= n:
            break
        v, i = _read_term(s, i)
        while True:
            k = i
            while k < n and s[k] in ' \t\r\n':
                k += 1
            if s[k:k+2] != '||':
                break
            k += 2
            while k < n and s[k] in ' \t\r\n':
                k += 1
            nxt, i = _read_term(s, k)
            v = ('' if v is None else str(v)) + ('' if nxt is None else str(nxt))
        vals.append(v)
    return vals

_INS = re.compile(
    r'Insert\s+into\s+([\w\.]+)\s*\((.*?)\)\s*Values\s*\((.*?)\)\s*;\s*(?=\r?\n|\Z)',
    re.I | re.S)

def parse_inserts(text):
    """[(TABLE_ADI, {COL: value}), ...] — fayldakı sıra ilə."""
    out = []
    for m in _INS.finditer(text):
        table = m.group(1).split('.')[-1].upper()
        cols = [c.strip().upper() for c in m.group(2).replace('\r', '').split(',')]
        vals = _tokenize_values(m.group(3))
        if len(cols) != len(vals):
            raise ValueError(f'{table}: {len(cols)} sütun, {len(vals)} dəyər -> {m.group(0)[:200]}')
        out.append((table, dict(zip(cols, vals))))
    return out
