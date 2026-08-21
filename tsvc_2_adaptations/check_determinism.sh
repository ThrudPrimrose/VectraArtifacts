#!/usr/bin/env bash
# Runs the same compile N times and checks whether the vectorizer's verdict
# is deterministic, i.e. whether the same "missed:" line shows up (or
# doesn't) on every single run. Nothing is written to disk beyond a
# scratch report file that gets overwritten each iteration -- only the
# summary goes to the terminal.
#
# Usage:
#   ./check_determinism.sh [N] [scripts.sh|scripts_clang.sh]
#
# Defaults to 50 runs of scripts.sh (GCC), since that's the script that
# produced the "missed: not vectorized: unsupported use in stmt." message
# in the first place.

set -uo pipefail

RUNS="${1:-50}"
COMPILE_SCRIPT="${2:-scripts.sh}"
NEEDLE='missed: not vectorized: unsupported use in stmt.'
SCRATCH_DIR="$(mktemp -d)"
trap 'rm -rf "$SCRATCH_DIR"' EXIT

# scripts.sh / scripts_clang.sh always write their report to a fixed
# filename in the current directory (vec_remarks_manual.rpt /
# vec_remarks_manual_clang.rpt) -- figure out which, so we know what to
# read back after each run.
case "$COMPILE_SCRIPT" in
  scripts.sh)        REPORT_FILE="vec_remarks_manual.rpt" ;;
  scripts_clang.sh)  REPORT_FILE="vec_remarks_manual_clang.rpt" ;;
  *) echo "Unknown compile script: $COMPILE_SCRIPT" >&2; exit 1 ;;
esac

hits=0            # number of runs where the needle appeared at least once
misses=0          # number of runs where it did not appear at all
total_occurrences=0
declare -A line_locations   # distinct "file:line:col" prefixes the needle showed up at, across all runs

echo "Running '$COMPILE_SCRIPT' $RUNS times, checking for:"
echo "  \"$NEEDLE\""
echo

for ((i = 1; i <= RUNS; i++)); do
  rm -f "$REPORT_FILE"

  if ! bash "$COMPILE_SCRIPT" > "$SCRATCH_DIR/stdout.$i" 2>&1; then
    echo "run $i: compile itself FAILED (see $SCRATCH_DIR/stdout.$i)" >&2
  fi

  if [[ ! -f "$REPORT_FILE" ]]; then
    echo "run $i: no report file produced ($REPORT_FILE) -- skipping" >&2
    continue
  fi

  count=$(grep -Fc "$NEEDLE" "$REPORT_FILE")

  if (( count > 0 )); then
    hits=$((hits + 1))
    total_occurrences=$((total_occurrences + count))
    while IFS= read -r loc; do
      line_locations["$loc"]=$(( ${line_locations["$loc"]:-0} + 1 ))
    done < <(grep -F "$NEEDLE" "$REPORT_FILE" | cut -d: -f1-3)
    printf 'run %3d: PRESENT (%dx)\n' "$i" "$count"
  else
    misses=$((misses + 1))
    printf 'run %3d: absent\n' "$i"
  fi
done

echo
echo "===== summary over $RUNS runs ($COMPILE_SCRIPT) ====="
echo "runs with the message present : $hits"
echo "runs with the message absent  : $misses"
echo "total occurrences across runs : $total_occurrences"
if (( hits > 0 && misses > 0 )); then
  echo "=> NON-DETERMINISTIC: the message appears on some runs but not others."
elif (( hits == RUNS )); then
  echo "=> deterministic: present on every run."
elif (( misses == RUNS )); then
  echo "=> deterministic: absent on every run."
fi

if (( ${#line_locations[@]} > 0 )); then
  echo
  echo "distinct locations the message was reported at:"
  for loc in "${!line_locations[@]}"; do
    printf '  %-90s seen in %d run(s)\n' "$loc" "${line_locations[$loc]}"
  done
fi
