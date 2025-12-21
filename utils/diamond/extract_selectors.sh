#!/usr/bin/env bash
set -euo pipefail

# Config: source directories to scan
contracts_dirs=(
  "src/challenge/features"
  "src/platform/facets"
  "src/abstract-diamond/core"
)

output_root="selectors"

# ---- globals (macOS-safe, no nameref) ----
TARGETS=()

# ---- helpers ----
log_info() { echo "[INFO] $1"; }
log_error() { echo "[ERROR] $1" >&2; }

clean_output_root() {
  if [[ -d "$output_root" ]]; then
    rm -rf "$output_root"
    log_info "Cleaned existing output directory"
  fi
}

# e.g. src/challenge/features/Foo.sol -> selectors/challenge
compute_dest_dir_for_file() {
  local file="$1"
  local parent_dir domain_dir
  parent_dir="$(dirname "$file")"
  domain_dir="$(basename "$(dirname "$parent_dir")")"
  echo "$output_root/$domain_dir"
}

process_contract() {
  local file="$1"

  local out_dir base_name output_file
  out_dir="$(compute_dest_dir_for_file "$file")"
  mkdir -p "$out_dir"

  base_name="$(basename "$file" .sol)"
  output_file="$out_dir/$base_name.json"

  log_info "Processing contract: $base_name -> $output_file"

  local output
  if ! output="$(forge selectors list "$base_name" 2>&1)"; then
    log_info "Skipping $base_name - unable to extract selectors"
    return 0
  fi

  if ! echo "$output" | grep -q '\|'; then
    log_info "No selectors found for $base_name"
    return 0
  fi

  # At least one non-Error row with a 0x selector?
  if ! echo "$output" | awk -F '|' '/\|/ && /0x/ && $0 !~ /Error/ {found=1} END {exit (found?0:1)}'; then
    log_info "No function selectors for $base_name (only errors/none)."
    return 0
  fi

  # Extract selectors from non-Error rows
  if echo "$output" \
    | awk -F '|' '/\|/ && /0x/ && $0 !~ /Error/ {gsub(/ /,"",$4); if (length($4)<=10) print $4}' \
    | jq -R -s 'split("\n") | map(select(. != "")) | {selectors: .}' >"$output_file"; then

    if [[ "$(jq '.selectors | length' "$output_file")" -gt 0 ]]; then
      log_info "Wrote selectors: $output_file"
    else
      log_info "No valid selectors for $base_name"
      rm -f "$output_file"
    fi
  else
    log_error "Failed to write selectors for $base_name"
    return 1
  fi
}

# Resolve targets when --file/-f is provided (fills global TARGETS)
resolve_files_from_arg() {
  local arg="$1"

  if [[ -f "$arg" ]]; then
    TARGETS+=("$arg")
    return 0
  fi

  local name="${arg%.sol}"
  local found=0
  local dir candidate
  for dir in "${contracts_dirs[@]}"; do
    candidate="$dir/$name.sol"
    if [[ -f "$candidate" ]]; then
      TARGETS+=("$candidate")
      found=1
    fi
  done

  if [[ $found -eq 0 ]]; then
    log_error "No file found for '$arg'. Provide a valid path or a contract name present in configured directories."
    return 1
  fi
}

process_all() {
  clean_output_root
  mkdir -p "$output_root"
  log_info "Created output root: $output_root"

  shopt -s nullglob
  local contracts_dir domain_dir dest_dir file
  for contracts_dir in "${contracts_dirs[@]}"; do
    if [[ ! -d "$contracts_dir" ]]; then
      log_error "Directory does not exist: $contracts_dir"
      continue
    fi

    domain_dir="$(basename "$(dirname "$contracts_dir")")"
    dest_dir="$output_root/$domain_dir"
    mkdir -p "$dest_dir"
    log_info "Processing: $contracts_dir -> $dest_dir"

    local files=( "$contracts_dir"/*.sol )
    if [[ ${#files[@]} -eq 0 ]]; then
      log_info "No Solidity files found in $contracts_dir"
      continue
    fi

    for file in "${files[@]}"; do
      if ! process_contract "$file"; then
        log_error "Failed to process $file"
        exit 1
      fi
    done
  done

  log_info "All contracts processed successfully"
}

process_selected() {
  local file_arg="$1"
  mkdir -p "$output_root"

  TARGETS=()
  if ! resolve_files_from_arg "$file_arg"; then
    exit 1
  fi

  if [[ ${#TARGETS[@]} -eq 0 ]]; then
    log_error "No targets resolved for '$file_arg'"
    exit 1
  fi

  local file
  for file in "${TARGETS[@]}"; do
    mkdir -p "$(compute_dest_dir_for_file "$file")"
    if ! process_contract "$file"; then
      log_error "Failed to process $file"
      exit 1
    fi
  done

  log_info "Selected contract(s) processed successfully"
}

main() {
  local file_arg=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --file|-f)
        file_arg="${2:-}"
        if [[ -z "$file_arg" ]]; then
          log_error "--file requires an argument"
          exit 1
        fi
        shift 2
        ;;
      *)
        log_error "Unknown arg: $1"
        exit 1
        ;;
    esac
  done

  if [[ -z "$file_arg" ]]; then
    process_all
  else
    process_selected "$file_arg"
  fi
}

main "$@"
