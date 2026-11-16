#!/usr/bin/env bash
# Fetch pull request and issue records for the configured organisations.
#
# Pages through every public repository with the GitHub GraphQL API, so the
# 1000-result search cap does not apply. Writes .cache/prs.json and
# .cache/issues.json. Needs gh, jq and GH_TOKEN (or a logged-in gh).
set -euo pipefail

for cmd in gh jq; do
  command -v "$cmd" >/dev/null || { echo "$cmd is required but not installed" >&2; exit 1; }
done

ORGS=(eggzec pydoe)
cache="$(cd "$(dirname "$0")/../.." && pwd)/.cache"
mkdir -p "$cache"

# $1 = connection name (pullRequests | issues)
query() {
  cat <<GQL
query(\$owner: String!, \$name: String!, \$endCursor: String) {
  repository(owner: \$owner, name: \$name) {
    $1(first: 100, after: \$endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { state authorAssociation author { __typename login } }
    }
  }
}
GQL
}

repos=()
for org in "${ORGS[@]}"; do
  while IFS= read -r r; do repos+=("$r"); done < <(
    gh repo list "$org" --visibility public --limit 1000 --json nameWithOwner --jq '.[].nameWithOwner')
done

(( ${#repos[@]} > 0 )) || { echo "no repositories found" >&2; exit 1; }

# One background job per repository and connection, each writing its own file,
# merged afterwards. At most JOBS run at once to stay clear of secondary rate limits.
JOBS=8
fail=0
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for pair in pullRequests:prs issues:issues; do
  field=${pair%%:*}; out=${pair##*:}
  for repo in "${repos[@]}"; do
    while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n || fail=1; done
    gh api graphql --paginate \
      -f query="$(query "$field")" -F owner="${repo%%/*}" -F name="${repo##*/}" \
      --jq ".data.repository.$field.nodes[] | .state |= ascii_downcase | .repository = \"$repo\"" \
      > "$tmp/$out.${repo//\//_}.jsonl" &
  done
done
while (( $(jobs -rp | wc -l) > 0 )); do wait -n || fail=1; done
(( fail == 0 )) || { echo "fetch failed for at least one repository" >&2; exit 1; }

for out in prs issues; do
  jq -s '.' "$tmp/$out".*.jsonl > "$cache/$out.json"
  echo "$out: $(jq length "$cache/$out.json") from ${#repos[@]} repositories"
done
