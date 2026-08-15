"""Dev-facing CLI. `rag ask "<question>"` — the W5 exit test runs this for 10 test queries.

Retrieval only (no generation — W6 scope). `python3 -m rag.cli ask "..."` also works, in case
the installed console-script isn't on PATH yet.
"""

import argparse

from rag import config
from rag import retrieve as retrieve_mod


def cmd_ask(question: str, top_k: int) -> None:
    chunks, epoch = retrieve_mod.retrieve(question, top_k=top_k)
    print(f'Q: "{question}"  (dataset_epoch={epoch})')
    if not chunks:
        print("  (no results)")
        return
    for i, c in enumerate(chunks, 1):
        snippet = c.text.replace("\n", " ")[:160]
        print(f'  {i}. {c.chunk_id}   score={c.score:.4f}   "{snippet}"')


def main() -> None:
    parser = argparse.ArgumentParser(prog="rag")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Retrieve top-k chunks for a question")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, default=config.TOP_K)

    args = parser.parse_args()
    if args.command == "ask":
        cmd_ask(args.question, args.top_k)


if __name__ == "__main__":
    main()
