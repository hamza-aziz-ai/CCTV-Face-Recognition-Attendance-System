"""Compiles the app code with Nuitka for the dedicated tier's -rt images (D-033 step 4): a copy of src/ and
Custom-ROI-Provisioning/ in which every first-party module is a native extension module and no readable Python is left.

Each module is compiled on its own, in module mode, and named at run time (--module-name-choice=runtime), because the
code imports the same file under more than one name (util.x and x). Tests are dropped. A module run as a script keeps a
two-line stub at its old path that imports the compiled module and calls its main block, so every command, compose file
and CI step that runs `python3 src/x.py` works unchanged: Python imports an extension module before a .py file of the
same name. The main block is moved into a function at build time only, with every name it binds declared global, so the
module behaves as before; the repository's source is never changed.

Run in the builder stage of compile.Dockerfile: python3 deploy/compile_tree.py OUT_DIR
Check a result: python3 deploy/compile_tree.py --check DIR (fails on any first-party source left)"""
import ast
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("src", "Custom-ROI-Provisioning")
ENTRY = "__cctv_main__"
STUB = f'if __name__ == "__main__":\n    import importlib, os\n    getattr(importlib.import_module(os.path.basename(__file__)[:-3]), "{ENTRY}")()\n'


def is_main_block(node):
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__" and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value == "__main__")


def bound_names(body):
    """The names a block of module-level statements binds, not counting those inside the functions or classes it defines."""
    names = set()

    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            return
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            names.add(node.target.id)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in body:
        visit(statement)
    return names


class Unannotate(ast.NodeTransformer):
    """`x: T = v` becomes `x = v` outside functions and classes: an annotated name cannot be declared global."""

    def visit_FunctionDef(self, node):
        return node

    visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

    def visit_AnnAssign(self, node):
        return ast.Assign(targets=[node.target], value=node.value) if node.value else ast.Pass()


def unannotate(statement):
    return Unannotate().visit(statement)


def split_main(source):
    """The source with its top-level `if __name__ == "__main__":` blocks moved into one function, or None if it has none."""
    tree = ast.parse(source)
    blocks = [node for node in tree.body if is_main_block(node)]
    if not blocks:
        return None
    body = [unannotate(statement) for block in blocks for statement in block.body]
    names = sorted(bound_names(body))
    function = ast.FunctionDef(name=ENTRY, args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                               body=([ast.Global(names=names)] if names else []) + body, decorator_list=[], returns=None,
                               type_params=[])
    call = ast.parse(f'if __name__ == "__main__":\n    {ENTRY}()').body[0]
    tree.body = [node for node in tree.body if not is_main_block(node)] + [function, call]
    return ast.unparse(ast.fix_missing_locations(tree))


def compile_module(path):
    """Compiles one module next to itself, deletes its source and leaves a stub if it is run as a script."""
    source = path.read_text(encoding="utf-8")
    main = split_main(source)
    if main is not None:
        path.write_text(main, encoding="utf-8")
    build = path.with_suffix(".build-dir")
    result = subprocess.run([sys.executable, "-m", "nuitka", "--mode=module", "--module-name-choice=runtime",
                             "--nofollow-imports", "--no-pyi-file", "--remove-output", "--quiet",
                             f"--output-dir={path.parent}", str(path)], capture_output=True, text=True)
    shutil.rmtree(build, ignore_errors=True)
    if result.returncode or not list(path.parent.glob(f"{path.stem}.*.so")):
        raise SystemExit(f"{path}: Nuitka failed\n{result.stdout}\n{result.stderr}")
    path.unlink()
    if main is not None:
        path.write_text(STUB, encoding="utf-8")
    return path


def leftovers(out):
    """First-party source in a compiled tree: any .py other than an empty file or the stub, any .pyc or .c."""
    found = []
    for tree in TREES:
        for path in (out / tree).rglob("*"):
            if path.suffix in (".pyc", ".c", ".pyi") or (path.suffix == ".py" and path.read_text(encoding="utf-8").strip() not in ("", STUB.strip())):
                found.append(path)
    return found


def build(out):
    if out.exists():
        shutil.rmtree(out)
    for tree in TREES:
        shutil.copytree(ROOT / tree, out / tree, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*", "node_modules"))
    shutil.copy2(ROOT / "requirements.txt", out / "requirements.txt")
    modules = [path for tree in TREES for path in (out / tree).rglob("*.py") if path.read_text(encoding="utf-8").strip()]
    with ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        for path in pool.map(compile_module, modules):
            print(f"compiled {path.relative_to(out)}", flush=True)
    left = leftovers(out)
    if left:
        raise SystemExit("source left in the compiled tree: " + ", ".join(map(str, left)))
    print(f"compiled {len(modules)} modules into {out}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--check"]:
        left = leftovers(Path(sys.argv[2]))
        print("no first-party source" if not left else "source left: " + ", ".join(map(str, left)))
        sys.exit(1 if left else 0)
    build(Path(sys.argv[1]).resolve())
