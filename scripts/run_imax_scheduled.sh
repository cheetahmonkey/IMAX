#!/usr/bin/env bash
# Entry point for Windows Task Scheduler. Keep the task command simple so WSL
# can start this job even when the distribution was stopped at trigger time.
set -uo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="${project_dir}/logs"
mkdir -p "${log_dir}"

exec 9>"${log_dir}/imax_refresh.lock"
if ! flock -n 9; then
  printf '[%s] IMAX refresh skipped: another run is active\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
  exit 0
fi

printf '[%s] IMAX refresh started\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
if "${project_dir}/scripts/refresh_imax.sh" --publish >> "${log_dir}/imax_refresh.log" 2>&1; then
  printf '[%s] IMAX refresh succeeded\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
  exit 0
else
  status=$?
  printf '[%s] IMAX refresh failed (exit %s)\n' "$(date -Is)" "${status}" >> "${log_dir}/imax_refresh.log"
  exit "${status}"
fi
