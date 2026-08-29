#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  prepare-diff.sh --repo-root PATH --output FILE --base REF --head REF
  prepare-diff.sh --repo-root PATH --output FILE --range RANGE
  prepare-diff.sh --repo-root PATH --output FILE --working-tree

Creates a read-only canonical Git diff and FILE.meta. Working-tree mode includes
staged, unstaged, and untracked files. The script never fetches, checks out,
stages, stashes, cleans, or edits repository files.
EOF
}

repo_root=""
output=""
base_ref=""
head_ref=""
diff_range=""
working_tree=0

while (($#)); do
  case "$1" in
    --repo-root)
      repo_root="${2:-}"
      shift 2
      ;;
    --output)
      output="${2:-}"
      shift 2
      ;;
    --base)
      base_ref="${2:-}"
      shift 2
      ;;
    --head)
      head_ref="${2:-}"
      shift 2
      ;;
    --range)
      diff_range="${2:-}"
      shift 2
      ;;
    --working-tree)
      working_tree=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$repo_root" || -z "$output" ]]; then
  printf '%s\n' '--repo-root and --output are required' >&2
  exit 2
fi

repo_root="$(cd "$repo_root" && pwd -P)"
git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null

mode_count=0
if [[ -n "$base_ref" || -n "$head_ref" ]]; then
  if [[ -z "$base_ref" || -z "$head_ref" ]]; then
    printf '%s\n' '--base and --head must be provided together' >&2
    exit 2
  fi
  mode_count=$((mode_count + 1))
fi
if [[ -n "$diff_range" ]]; then
  mode_count=$((mode_count + 1))
fi
if ((working_tree)); then
  mode_count=$((mode_count + 1))
fi
if ((mode_count != 1)); then
  printf '%s\n' 'choose exactly one mode: --base/--head, --range, or --working-tree' >&2
  exit 2
fi

mkdir -p "$(dirname "$output")"
output_dir="$(cd "$(dirname "$output")" && pwd -P)"
output="${output_dir}/$(basename "$output")"
case "$output" in
  "$repo_root"|"$repo_root"/*)
    printf '%s\n' '--output must be outside the reviewed repository' >&2
    exit 2
    ;;
esac

tmp_diff="$(mktemp "${TMPDIR:-/tmp}/review-guard-diff.XXXXXX")"
tmp_meta="$(mktemp "${TMPDIR:-/tmp}/review-guard-meta.XXXXXX")"
trap 'rm -f "$tmp_diff" "$tmp_meta"' EXIT

mode=""
base_sha=""
head_sha=""
merge_base=""
untracked_count=0

if ((working_tree)); then
  mode="working-tree"
  head_sha="$(git -C "$repo_root" rev-parse --verify 'HEAD^{commit}')"
  git -C "$repo_root" diff --no-ext-diff --find-renames --binary HEAD -- >"$tmp_diff"

  while IFS= read -r -d '' path; do
    untracked_count=$((untracked_count + 1))
    set +e
    git -C "$repo_root" diff --no-index --no-ext-diff --binary -- /dev/null "$path" >>"$tmp_diff"
    status=$?
    set -e
    if ((status > 1)); then
      printf 'failed to diff untracked file: %s\n' "$path" >&2
      exit "$status"
    fi
  done < <(git -C "$repo_root" ls-files --others --exclude-standard -z)
elif [[ -n "$diff_range" ]]; then
  if [[ "$diff_range" == -* ]]; then
    printf '%s\n' '--range must not begin with a dash' >&2
    exit 2
  fi
  mode="range"
  git -C "$repo_root" diff --no-ext-diff --find-renames --binary "$diff_range" -- >"$tmp_diff"
else
  mode="merge-base"
  base_sha="$(git -C "$repo_root" rev-parse --verify "${base_ref}^{commit}")"
  head_sha="$(git -C "$repo_root" rev-parse --verify "${head_ref}^{commit}")"
  merge_base="$(git -C "$repo_root" merge-base "$base_sha" "$head_sha")"
  git -C "$repo_root" diff --no-ext-diff --find-renames --binary "${merge_base}..${head_sha}" -- >"$tmp_diff"
fi

{
  printf 'mode=%s\n' "$mode"
  printf 'repo_root=%s\n' "$repo_root"
  printf 'base_ref=%s\n' "$base_ref"
  printf 'base_sha=%s\n' "$base_sha"
  printf 'head_ref=%s\n' "$head_ref"
  printf 'head_sha=%s\n' "$head_sha"
  printf 'merge_base=%s\n' "$merge_base"
  printf 'range=%s\n' "$diff_range"
  printf 'untracked_count=%s\n' "$untracked_count"
  printf 'diff_bytes=%s\n' "$(wc -c <"$tmp_diff" | tr -d ' ')"
} >"$tmp_meta"

cp "$tmp_diff" "$output"
cp "$tmp_meta" "${output}.meta"

printf 'diff=%s\nmetadata=%s\n' "$output" "${output}.meta"
