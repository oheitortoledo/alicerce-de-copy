#!/usr/bin/env python3
"""contar_mencoes.py — Deep Persona Research v5

Conta menções de termos (com sinônimos) em um corpus de pesquisa, aplicando
a regra "1 fonte distinta = 1 menção" do v5 (mesma fonte repetindo NÃO infla).

Classifica automaticamente pelos thresholds do template:
  Dominante     ≥30 fontes
  Secundária    15-29
  Terciária      6-14
  Pontual        2-5
  Insuficiente   1

Input do arquivo de termos (JSON):

  {
    "esgotamento por falta de tempo": ["sem tempo", "vivo correndo", "acordo cansado"],
    "vergonha de pedir ajuda": ["tenho vergonha", "não consigo pedir"],
    "medo de envelhecer pobre": ["envelhecer pobre", "velhice sem dinheiro"]
  }

A chave é o "rótulo do cluster" (o que vai aparecer na coluna Elemento).
A lista são as variantes/sinônimos buscados como string. Busca case-insensitive,
com normalização de acento (matches "vergonha" em "vergônha", "vergonha,", etc).

Uso:
  python contar_mencoes.py /caminho/pasta --termos termos.json
  python contar_mencoes.py /caminho/pasta --termos termos.json --formato json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


THRESHOLDS = [
    (30, "Dominante"),
    (15, "Secundária"),
    (6,  "Terciária"),
    (2,  "Pontual"),
    (1,  "Insuficiente"),
    (0,  "Ausente"),
]


def classificar(freq: int) -> str:
    for limite, rotulo in THRESHOLDS:
        if freq >= limite:
            return rotulo
    return "Ausente"


def normalizar(texto: str) -> str:
    """Remove acentos e força lowercase pra match resiliente."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def carregar_corpus(pasta: Path, extensoes: list[str]) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for arquivo in sorted(pasta.rglob("*")):
        if not arquivo.is_file():
            continue
        if extensoes and arquivo.suffix.lower() not in extensoes:
            continue
        try:
            corpus[arquivo.relative_to(pasta).as_posix()] = arquivo.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            corpus[arquivo.relative_to(pasta).as_posix()] = arquivo.read_text(encoding="latin-1", errors="ignore")
    return corpus


def contar(corpus: dict[str, str], termos: dict[str, list[str]]) -> list[dict]:
    """Para cada cluster, conta em quantas fontes distintas aparece pelo menos 1 variante."""
    corpus_normalizado = {nome: normalizar(texto) for nome, texto in corpus.items()}
    resultados = []

    for rotulo, variantes in termos.items():
        variantes_norm = [normalizar(v) for v in variantes if v.strip()]
        if not variantes_norm:
            continue

        fontes_hit = []
        for nome_fonte, texto_norm in corpus_normalizado.items():
            if any(re.search(rf"\b{re.escape(v)}\b", texto_norm) for v in variantes_norm):
                fontes_hit.append(nome_fonte)

        freq = len(fontes_hit)
        resultados.append({
            "cluster": rotulo,
            "variantes": variantes,
            "frequencia": freq,
            "classificacao": classificar(freq),
            "fontes": fontes_hit,
        })

    resultados.sort(key=lambda x: x["frequencia"], reverse=True)
    return resultados


def renderizar_markdown(resultados: list[dict], total_fontes: int) -> str:
    linhas = [
        f"# Contagem de menções — Deep Persona Research v5",
        "",
        f"**Total de fontes no corpus:** {total_fontes}",
        "",
        "Regra: 1 fonte distinta = 1 menção. Repetições no mesmo material não inflam.",
        "",
        "| Cluster | Frequência | Classificação | Fontes onde apareceu |",
        "|---|---:|---|---|",
    ]
    for r in resultados:
        fontes_str = ", ".join(r["fontes"][:8])
        if len(r["fontes"]) > 8:
            fontes_str += f", ... (+{len(r['fontes']) - 8})"
        if not fontes_str:
            fontes_str = "—"
        linhas.append(f"| {r['cluster']} | {r['frequencia']}/{total_fontes} | **{r['classificacao']}** | {fontes_str} |")

    linhas.extend([
        "",
        "> **Atenção:** estes números refletem **string match com sinônimos** (case e acento insensitive). "
        "Sarcasmo, negação e contexto figurativo passam batido — revisar manualmente em clusters com freq baixa "
        "ou em fontes ambíguas antes de usar como evidência final no alicerce.",
    ])
    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Conta menções de termos no corpus pra Deep Persona Research v5")
    parser.add_argument("pasta", type=Path, help="Pasta com o corpus")
    parser.add_argument("--termos", type=Path, required=True, help="Arquivo JSON com clusters → [variantes]")
    parser.add_argument("--extensoes", nargs="*", default=[".txt", ".md", ".vtt", ".srt"], help="Extensões a considerar")
    parser.add_argument("--formato", choices=["markdown", "json"], default="markdown", help="Formato de saída")
    args = parser.parse_args()

    if not args.pasta.is_dir():
        print(f"Erro: {args.pasta} não é um diretório.", file=sys.stderr)
        return 1
    if not args.termos.is_file():
        print(f"Erro: {args.termos} não encontrado.", file=sys.stderr)
        return 1

    try:
        termos = json.loads(args.termos.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Erro ao ler JSON {args.termos}: {e}", file=sys.stderr)
        return 1

    if not isinstance(termos, dict):
        print("Erro: arquivo de termos deve ser um objeto JSON {cluster: [variantes]}", file=sys.stderr)
        return 1

    extensoes = [e if e.startswith(".") else f".{e}" for e in args.extensoes]
    corpus = carregar_corpus(args.pasta, extensoes)

    if not corpus:
        print(f"Erro: nenhum arquivo lido em {args.pasta} com extensões {extensoes}.", file=sys.stderr)
        return 1

    resultados = contar(corpus, termos)

    if args.formato == "json":
        print(json.dumps({"total_fontes": len(corpus), "resultados": resultados}, ensure_ascii=False, indent=2))
    else:
        print(renderizar_markdown(resultados, len(corpus)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
