#!/bin/bash
# Runs start/stop_standalone_services.sh with docker and docker-compose stubbed: once from a release bundle with a
# separate site folder, once from the checkout. Run: bash deploy/test_standalone_scripts.sh
set -u
CHECKOUT=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v python3 || command -v python)
T=$(mktemp -d)
mkdir -p "$T/bin" "$T/site"
for cmd in docker docker-compose; do
  printf '#!/bin/bash\necho "%s [$(pwd)] $*" >> "%s/calls.log"\n[ "$1" = image ] && exit 0\nexit 0\n' "$cmd" "$T" > "$T/bin/$cmd"
  chmod +x "$T/bin/$cmd"
done
export PATH="$T/bin:$PATH"
fail=0
check() { if eval "$2"; then echo "  ok: $1"; else echo "  FAIL: $1"; fail=1; fi; }

echo "== bundle mode"
"$PY" -I "$CHECKOUT/deploy/make_bundle.py" demo "$T/bundle" > /dev/null
cp "$T/bundle/STANDALONE-SERVICES/standalone-services.env" "$T/env.before"
printf 'DATASET_STORE_USER=u\nDATASET_STORE_PASSWORD=p\nDATASET_STORE_DIR=/tmp/store\n' > "$T/site/.env"
CONFIG_DIR="$T/site" bash "$T/bundle/start_standalone_services.sh" > "$T/start.out" 2>&1
check "site master.env created with this host's IP" "grep -qE '^IP_ADDRESS=[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' '$T/site/master.env'"
check "bundle's standalone-services.env not edited" "cmp -s '$T/env.before' '$T/bundle/STANDALONE-SERVICES/standalone-services.env'"
check "Kafka and Milvus get the site master.env last" "[ \$(grep -c -- 'up -d' '$T/calls.log') -ge 3 ] && grep 'Confluent-Kafka' '$T/calls.log' | grep -q -- \"--env-file $T/site/master.env up\""
check "dataset store gets the site .env" "grep 'Dataset-Store' '$T/calls.log' | grep -q -- \"--env-file $T/site/.env up\""
check "models folder in the site, with models.json" "[ -f '$T/site/insightface-models/models.json' ]"
check "InsightFace runs the bundle's pinned digest, models from the site" "grep 'docker \[.*\] run ' '$T/calls.log' | grep -q 'insightface-rest@sha256:' && grep 'docker \[.*\] run ' '$T/calls.log' | grep -q 'insightface-models:/models'"
check "no models folder created inside the bundle" "[ ! -d '$T/bundle/STANDALONE-SERVICES/InsightFace-REST/models/onnx' ] && [ \$(ls '$T/bundle/STANDALONE-SERVICES/InsightFace-REST/models' | wc -l) -eq 1 ]"
: > "$T/calls.log"
CONFIG_DIR="$T/site" bash "$T/bundle/stop_standalone_services.sh" > /dev/null 2>&1
check "stop: dataset store gets the site .env" "grep 'Dataset-Store' '$T/calls.log' | grep -q -- \"--env-file $T/site/.env down\""

echo "== checkout mode (default)"
: > "$T/calls.log"
before=$(git -C "$CHECKOUT" status --porcelain --untracked-files=no)
(cd /tmp && bash "$CHECKOUT/start_standalone_services.sh" > "$T/start2.out" 2>&1)
check "runs from any folder; Kafka gets the checkout's master.env" "grep 'Confluent-Kafka' '$T/calls.log' | grep -q -- '--env-file .*master.env up'"
check "no tracked file changed" "[ \"\$(git -C '$CHECKOUT' status --porcelain --untracked-files=no)\" = \"$before\" ]"
check "models stay in the checkout's models folder" "grep 'docker \[.*\] run ' '$T/calls.log' | grep -q 'InsightFace-REST/models:/models'"

[ $fail = 0 ] && echo "standalone scripts ok (bundle + site folder, and checkout)" || { echo "--- start output"; tail -20 "$T/start.out"; echo "--- calls"; cat "$T/calls.log"; }
rm -rf "$T"
exit $fail
