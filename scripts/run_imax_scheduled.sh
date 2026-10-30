#!/usr/bin/env bash
# Entry point for Windows Task Scheduler. Keep the task command simple so WSL
# can start this job even when the distribution was stopped at trigger time.
set -uo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="${project_dir}/logs"
mkdir -p "${log_dir}"

# Local machine settings (including the private Healthchecks URL) stay out of Git.
if [[ -f "${project_dir}/.imax-scheduler.env" ]]; then
  source "${project_dir}/.imax-scheduler.env"
fi

ping_healthcheck() {
  [[ -z "${IMAX_HEALTHCHECK_URL:-}" ]] && return 0
  curl --fail --silent --show-error --connect-timeout 10 --max-time 30 \
    --retry 2 "${IMAX_HEALTHCHECK_URL%/}${1}" >> "${log_dir}/imax_refresh.log" 2>&1
}

exec 9>"${log_dir}/imax_refresh.lock"
if ! flock -n 9; then
  printf '[%s] IMAX refresh skipped: another run is active\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
  exit 0
fi

# Both the daily trigger and Windows sign-in use this entry point. A sign-in
# catches up a missed run without publishing repeatedly throughout the day.
if [[ "${1:-}" == "--if-due" ]]; then
  due=$(date -d 'today 03:15' +%s)
  if (( $(date +%s) < due )); then
    due=$(date -d 'yesterday 03:15' +%s)
  fi
  last_success=0
  if [[ -f "${log_dir}/last_success" ]]; then
    read -r last_success < "${log_dir}/last_success"
  fi
  if [[ "${last_success}" =~ ^[0-9]+$ ]] && (( last_success >= due )); then
    exit 0
  fi
fi

printf '[%s] IMAX refresh started\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
ping_healthcheck /start || true
if "${project_dir}/scripts/refresh_imax.sh" --publish >> "${log_dir}/imax_refresh.log" 2>&1; then
  if ! ping_healthcheck ''; then
    printf '[%s] Healthchecks success ping failed\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
    exit 1
  fi
  date +%s > "${log_dir}/last_success"
  printf '[%s] IMAX refresh succeeded\n' "$(date -Is)" >> "${log_dir}/imax_refresh.log"
  exit 0
else
  status=$?
  ping_healthcheck /fail || true
  printf '[%s] IMAX refresh failed (exit %s)\n' "$(date -Is)" "${status}" >> "${log_dir}/imax_refresh.log"
  exit "${status}"
fi
