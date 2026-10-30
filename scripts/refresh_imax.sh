#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_dir}"

"${project_dir}/.venv/bin/python" "${project_dir}/check_imax.py" --delay-seconds 1

if [[ "${1:-}" == "--publish" ]]; then
  artifacts=(
    docs/index.html docs/dune_three.html docs/current_feature.html
    output/dune_three_availability.csv output/dune_three_available.md output/dune_three_all.md
    output/current_feature_availability.csv output/current_feature_available.md output/current_feature_all.md
    current_feature.json
  )
  git add -- "${artifacts[@]}"
  if ! git diff --cached --quiet -- "${artifacts[@]}"; then
    git commit --only -m "Refresh IMAX availability $(date '+%Y-%m-%d %H:%M %Z')" -- "${artifacts[@]}"
  fi
  # A previous attempt may have committed successfully but failed to push.
  git push origin main
fi
