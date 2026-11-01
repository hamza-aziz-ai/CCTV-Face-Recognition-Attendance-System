"""Fail on duplicate keys in YAML files, which GitHub Actions and Compose reject but yaml.safe_load accepts silently."""
import sys
import yaml

class Strict(yaml.SafeLoader):
    pass

def mapping(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise yaml.constructor.ConstructorError(None, None, f"duplicate keys {sorted(map(str, dup))}", node.start_mark)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)

Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
bad = 0
for path in sys.argv[1:]:
    try:
        yaml.load(open(path, encoding="utf-8"), Strict)
    except yaml.YAMLError as e:
        bad += 1
        print(f"{path}: {str(e).splitlines()[0]} {getattr(e, 'problem_mark', '') or ''}".strip())
print(f"{len(sys.argv) - 1 - bad} ok, {bad} with duplicate keys or errors")
sys.exit(1 if bad else 0)
